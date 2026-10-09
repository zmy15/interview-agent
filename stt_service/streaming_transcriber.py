"""
流式转录器 — VAD 分段 → faster-whisper 异步转录
边说边出字：前一段 final 文本累积 + 当前段 partial 输出
"""

import asyncio
import logging
import threading
from typing import Callable, Optional

import numpy as np

from vad_processor import VADProcessor
from zh_convert import to_simplified

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# 进程级模型单例
# ══════════════════════════════════════════════════════════════
#
# Whisper 与 Silero VAD 的加载都很慢（实测 Whisper 在 CUDA 上约 11 秒，
# Silero 约 15 秒，因为要 torch.hub 下载/解包）。早期实现里
# **每个 WebSocket 连接都 new 一个 StreamingTranscriber 并各自加载**，
# 于是：
#   - 每次点开监听都要等十几秒才 ready；
#   - 日志里出现成串的「Whisper model loaded」「Silero VAD model loaded」；
#   - 前端重挂载一次就再加载一遍，白白占用显存与时间。
#
# 模型是**只读共享**的（transcribe 本身是纯推理，不持有会话状态），
# 因此做成进程级单例；每个连接只持有自己的会话状态
# （VAD 状态机、音频缓冲、回调）。
_model_cache: dict = {}
_model_lock = threading.Lock()


def get_shared_whisper(model_size: str, device: str, compute_type: str):
    """取（或首次加载）进程级共享的 Whisper 模型"""
    key = (model_size, device, compute_type)
    with _model_lock:
        if key in _model_cache:
            return _model_cache[key]

        from faster_whisper import WhisperModel

        logger.info(
            "首次加载 Whisper 模型（size=%s device=%s compute=%s）…",
            model_size, device, compute_type,
        )
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        _model_cache[key] = model
        logger.info("Whisper 模型已加载并缓存，后续连接直接复用")
        return model


def preload_shared_models(model_size: str, device: str, compute_type: str) -> bool:
    """预热共享模型（供启动时调用，让首个连接也无需等待）。

    返回**是否全部成功**。调用方必须据此判断状态：
    早期实现内部吞掉异常、调用方无条件认为成功，导致
    Whisper 下载失败时 /health 仍报 ok，前端以为可用，
    实际首个连接才去下载并可能再次失败。
    """
    ok = True

    try:
        get_shared_whisper(model_size, device, compute_type)
    except Exception as exc:
        ok = False
        logger.error("预热 Whisper 失败（首个连接时会重试）: %s", exc)

    try:
        VADProcessor(sample_rate=16000)._ensure_model()
    except Exception as exc:
        ok = False
        logger.error("预热 Silero VAD 失败（首个连接时会重试）: %s", exc)

    return ok


class StreamingTranscriber:
    """流式转录器

    工作流程：
    1. 接收 PCM 音频帧 → 送入 VAD 检测语音边界
    2. VAD 检测到 speech_end → 取该段音频 → 异步调用 whisper 转录
    3. 转录结果通过回调输出：partial（本段已识别）+ final（本段完整句）
    """

    # Whisper 的 initial_prompt：用于唤回短片段上的中文标点。
    #
    # 为什么需要：VAD 把音频切成 1~2 秒的碎片，Whisper 在缺乏上下文的
    # 碎片上**完全不输出标点**（实测 1.5s 碎片仅 1/9 段有标点，
    # 加长到 3~12 秒仍不稳定，只有整段才有完整标点）。
    # 给一段「要求带标点」的中文提示即可恢复。这段文字本身不会被输出，
    # 但在静音片段上可能被误当成内容 —— 由 _has_speech_energy 与
    # _strip_prompt_leak 两道防线处理。
    INITIAL_PROMPT = "以下是普通话的句子，请使用简体中文并加上标点符号。"

    # 低于此 RMS 的片段视为静音，直接跳过转录。
    # 0.002 ≈ -54dBFS：正常说话约 0.02 以上，这里只挡「接近纯静音」。
    SILENCE_RMS_FLOOR = 0.002

    # Whisper 在静音/低信噪比片段上的**训练集幻觉**。
    #
    # 它的语料主要来自带字幕的视频，于是会复读那些字幕套话。
    # 实测 large-v3-turbo 比 base 更容易触发，且内容与面试完全无关。
    # 整段匹配用 HALLUCINATION_PATTERNS，句内剔除用 HALLUCINATION_SPANS。
    HALLUCINATION_PATTERNS = (
        "请不吝点赞 订阅 转发 打赏支持明镜与点点栏目",
        "请不吝点赞订阅转发打赏支持明镜与点点栏目",
        "字幕由 amara.org 社区提供",
        "字幕志愿者 李宗盛",
        "字幕志愿者",
        "MING PAO CANADA",
        "由 amara.org 社区提供",
        "谢谢大家观看",
        "感谢观看",
    )

    # 句内出现这些子串时，从该处截断（后面的内容都是幻觉）。
    # 注意要包含完整的引导语：只写 "amara.org" 会留下前面的
    # "字幕由" 三个字（实测），反而制造出半截垃圾文本。
    HALLUCINATION_SPANS = (
        "请不吝点赞",
        "订阅 转发",
        "打赏支持",
        "明镜与点点",
        "字幕由 amara.org",
        "amara.org",
        "字幕志愿者",
        "MING PAO",
        "谢谢大家观看",
        "感谢观看",
    )

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        sample_rate: int = 16000,
        silence_timeout: float = 1.0,
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[str], None]] = None,
        on_vad: Optional[Callable[[str], None]] = None,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.sample_rate = sample_rate

        # 提示词的紧凑形式（去掉空格），用于识别泄漏结果
        self._prompt_compact = self.INITIAL_PROMPT.replace(" ", "").replace("，", "")

        # 回调
        self.on_partial = on_partial
        self.on_final = on_final
        self.on_vad = on_vad

        # VAD 处理器
        self.vad = VADProcessor(
            sample_rate=sample_rate,
            silence_timeout=silence_timeout,
        )

        # Whisper 模型（懒加载）
        self._model = None

        # 累积的全部转录文本
        self._full_text: str = ""

        # 后台转录任务
        self._pending_tasks: list[asyncio.Task] = []

    # ── 懒加载 Whisper ──

    def _ensure_model(self):
        """确保 Whisper 模型可用（复用进程级共享实例）

        模型加载很慢（CUDA 上约 11 秒），因此**不**在每次连接时重新加载。
        共享实例只做纯推理，不持有任何会话状态。
        """
        if self._model is not None:
            return
        self._model = get_shared_whisper(
            self.model_size, self.device, self.compute_type
        )

    # ── 核心：逐帧处理 ──

    async def process_frame(self, audio_frame: np.ndarray) -> None:
        """
        处理一帧音频。

        Args:
            audio_frame: float32 numpy array, 16kHz mono
        """
        # 送入 VAD
        vad_events = self.vad.process_frame(audio_frame)

        for event in vad_events:
            etype = event["type"]
            ts = event.get("ts", 0.0)

            if etype == "speech_end":
                # 取该段音频 → 异步转录
                audio_segment = self.vad.get_buffer_and_reset()
                if len(audio_segment) > 0:
                    # final=True：断句完成即视为一个完整句子，要立刻推给客户端。
                    # 早期实现用默认的 final=False，导致 on_final 从不触发，
                    # 转写结果只进不出，客户端永远收不到 final。
                    task = asyncio.create_task(
                        self._transcribe_segment(audio_segment, ts, final=True)
                    )
                    self._pending_tasks.append(task)

                if self.on_vad:
                    self.on_vad("speech_end")

    async def flush(self) -> Optional[str]:
        """
        强制转录当前 buffer（用于手动停止录音时）。
        返回最终完整文本。
        """
        audio_segment = self.vad.get_buffer_and_reset()
        if len(audio_segment) > 0:
            await self._transcribe_segment(audio_segment, final=True)

        # 等待所有后台任务
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
            self._pending_tasks.clear()

        return self._full_text.strip() if self._full_text else ""

    # ── 转录逻辑 ──

    async def _transcribe_segment(
        self, audio: np.ndarray, timestamp: float = 0.0, final: bool = False
    ):
        """异步转录一段音频"""
        self._ensure_model()

        try:
            # 能量门限：明显是静音/极低电平的片段直接丢弃，不送 Whisper。
            #
            # 为什么必须挡：
            #   Whisper 在纯静音上会产生**幻觉**（实测无提示词时输出
            #   「我认识你我认识你我认识你」），既污染对话又浪费时间。
            #   VAD 已经做过一次筛选，但偶尔仍会因底噪误判出片段。
            if not self._has_speech_energy(audio):
                logger.debug("片段电平过低（%.4f），跳过转录", self._rms(audio))
                return

            # faster-whisper 需要 float32 输入
            audio_float32 = audio.astype(np.float32)

            # Whisper 推理是**同步阻塞**的（CPU 上 base 模型一段几秒音频要
            # 几百毫秒到数秒）。直接在事件循环里跑会卡住整个 WebSocket，
            # 后续音频帧全部堆积。丢到线程池执行。
            #
            # initial_prompt 是**标点的关键**：
            #   VAD 把音频切成 1~2 秒的短片段，Whisper 在缺乏上下文的
            #   碎片上会**完全不输出标点**。实测数据：
            #       1.5s 碎片  -> 1/9 段含标点
            #       3.0s 碎片  -> 2/5
            #       8.0s 碎片  -> 0/2
            #       整段音频   -> 有完整标点
            #   即「靠加长片段」无法解决（试到 12 秒仍不稳定），
            #   只有 initial_prompt 能把它唤回来：
            #       碎片 + prompt -> '人测过很多了。' / '游戏本里见过没。'
            #
            # 副作用与对策：静音片段上 Whisper 会把 prompt 本身吐出来
            #   （实测输出 '。。。。。。。。' 或 '请使用简体中文并加上标'）。
            #   上面的能量门限负责挡住静音，_strip_prompt_leak 再兜一层。
            segments, info = await asyncio.to_thread(
                self._model.transcribe,
                audio_float32,
                language="zh",
                beam_size=5,
                vad_filter=False,
                initial_prompt=self.INITIAL_PROMPT,
                # 每段是独立音频块，没有前文可参考；开着它反而会让
                # 上一段的用词漂移到下一段。
                condition_on_previous_text=False,
            )

            segment_texts = []
            for segment in segments:
                # Whisper 中文默认输出繁体，这里先转简体。
                segment_texts.append(to_simplified(segment.text))

            # 先过滤（提示词泄漏 + 训练集幻觉），再推送 partial。
            # 顺序很重要：早期实现先推 partial 后过滤，
            # 幻觉与泄漏会抢先出现在前端，再也收不回来。
            new_text = self._strip_prompt_leak(
                self._strip_hallucination_spans("".join(segment_texts).strip())
            )
            if new_text and self.on_partial:
                self.on_partial(new_text)

            # 本段最终文本。
            #
            # 关键：final 只推**本段**，不再推跨段累积的全文。
            # 早期实现把 _full_text（跨断句不断累积）当 final 推送，
            # 于是第二句话的 final = "第一句话 + 第二句话"，
            # 前端表现为「第二次的内容和第一次连在一起且重复」。
            if new_text:
                # _full_text 仅用于 flush 时取回整场文本，不参与推送
                self._full_text += new_text
                if final:
                    if self.on_final:
                        self.on_final(new_text)

            logger.info(
                "转写片段: %.1fs 音频 → '%s' (lang=%s)",
                len(audio) / self.sample_rate,
                new_text[:80],
                info.language,
            )

        except Exception as e:
            logger.error("Transcription failed: %s", e)

    # ── 片段质量把关 ──

    def _rms(self, audio: np.ndarray) -> float:
        """片段的均方根电平"""
        if audio.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(audio.astype(np.float32)))))

    def _has_speech_energy(self, audio: np.ndarray) -> bool:
        """片段是否含有足够的语音能量。

        阈值取得很低（0.002 ≈ -54dBFS）：正常说话的人声 RMS 通常在
        0.02 以上，这里只用于挡掉「接近纯静音」的片段，
        宁可比 VAD 宽松也不要误杀正常说话的轻声句尾。
        """
        return self._rms(audio) >= self.SILENCE_RMS_FLOOR

    def _strip_prompt_leak(self, text: str) -> str:
        """过滤两类「非用户语音」的输出：提示词泄漏 + Whisper 幻觉。

        一、提示词泄漏
            静音片段上 Whisper 会把 initial_prompt 当内容输出
            （实测 '。。。。。。。。' 或 '请使用简体中文并加上标'）。

        二、训练集幻觉
            Whisper 的语料主要来自带字幕的视频，在静音/低信噪比片段上
            会吐出固定的套话。实测 large-v3-turbo 比 base **更容易**触发：
                请不吝点赞 订阅 转发 打赏支持明镜与点点栏目
                字幕由 amara.org 社区提供
            这类内容与面试毫无关系，必须丢掉，否则会污染对话。

        注意这里只做「整段匹配」判断：若幻觉混在正常句子中间
        （如 '那天选者，请不吝点赞 订阅 转发...'），
        整段不等于幻觉模板，需由 _strip_hallucination_spans 处理。
        """
        if not text:
            return text

        # 全是标点符号 —— 典型的 prompt 泄漏形态
        if not any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in text):
            if len(text) <= 12:
                logger.debug("丢弃纯标点结果（疑似提示词泄漏）: %r", text)
                return ""

        compact = text.replace(" ", "")

        # 结果落在提示词的任意片段里 → 判定为泄漏
        if len(compact) >= 4 and compact in self._prompt_compact:
            logger.debug("丢弃提示词泄漏: %r", text)
            return ""

        # 整段就是某个幻觉模板
        for pattern in self.HALLUCINATION_PATTERNS:
            if compact == pattern.replace(" ", ""):
                logger.debug("丢弃幻觉文本: %r", text)
                return ""

        return text

    def _strip_hallucination_spans(self, text: str) -> str:
        """从句子中间剔除幻觉片段。

        实测 large-v3-turbo 会把它接在正常内容后面：
            '那天选者，请不吝点赞 订阅 转发 打赏支持明镜与点点栏目'
        整段不等于模板，但其中有明确的幻觉子串，截掉即可。

        注意结尾处理：截断后常留下一个悬空的逗号（'那天选者，'），
        要把**连接性标点**去掉；但句号/问号是正常的句末标点
        （'鼠标的天选我们。'），不能一起 strip 掉，否则会把
        正常的句号吃掉。
        """
        if not text:
            return text

        cleaned = text
        for pattern in self.HALLUCINATION_SPANS:
            idx = cleaned.find(pattern)
            if idx >= 0:
                logger.debug("剔除句内幻觉片段 %r（原文 %r）", pattern, cleaned)
                cleaned = cleaned[:idx]

        # 只去连接性标点，保留句末标点
        return cleaned.strip().rstrip("，,、；;：: ")

    def reset(self):
        """重置会话（新录音开始前调用）"""
        self._full_text = ""
        self._pending_tasks.clear()
        self.vad._reset()
