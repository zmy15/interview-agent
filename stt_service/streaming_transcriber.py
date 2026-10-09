"""
流式转录器 — VAD 分段 → faster-whisper 异步转录
边说边出字：前一段 final 文本累积 + 当前段 partial 输出
"""

import asyncio
import logging
import os
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


def _cache_roots() -> list[str]:
    """列出所有可能存放 HF 模型的缓存根目录（按优先级）。

    为什么需要"多个"根目录：
        本项目 config.py 在导入时会把 HF_HOME 设成**项目内**的 hf_cache
        （见 config.py 顶部），而模型通常是先前用别的方式下载到**用户目录**
        的 HF 缓存（%USERPROFILE%\\.cache\\huggingface\\hub）。

        两个目录可能只有一个是完整的：实测项目内 hf_cache 里的
        large-v3-turbo 只剩 refs/main，snapshots/blobs 都缺失
        （一个残骸），真实权重在用户目录里。
        只查当前 HF_HUB_CACHE 就会"看得见目录名、找不到权重"，
        然后回退联网并失败。

    顺序：当前生效的 HF_HUB_CACHE 优先，其后是用户默认缓存。
    """
    roots: list[str] = []

    def _add(path: str) -> None:
        if path and path not in roots:
            roots.append(path)

    try:
        from huggingface_hub import constants as hf_constants
        _add(getattr(hf_constants, "HF_HUB_CACHE", "") or "")
        # 默认缓存：HF_HOME/hub，或 ~/.cache/huggingface/hub
        default_home = (
            os.getenv("HF_HOME")
            or os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
        )
        _add(os.path.join(default_home, "hub"))
    except Exception:
        pass

    # 环境变量兜底（constants 导入失败时仍能工作）
    _add(os.getenv("HF_HUB_CACHE", ""))
    _add(os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub"))

    return roots


def _snapshot_in(hub_root: str, repo_id: str) -> Optional[str]:
    """在指定缓存根里查找某个 repo 可用的 snapshot 目录（无则 None）"""
    hub_dir = os.path.join(hub_root, "models--" + repo_id.replace("/", "--"))
    snapshots = os.path.join(hub_dir, "snapshots")
    if not os.path.isdir(snapshots):
        return None

    candidates: list[str] = []

    # 1) refs/main 指向的 revision 优先
    ref_file = os.path.join(hub_dir, "refs", "main")
    if os.path.isfile(ref_file):
        try:
            with open(ref_file, "r", encoding="utf-8") as fh:
                revision = fh.read().strip()
            if revision:
                path = os.path.join(snapshots, revision)
                if os.path.isdir(path):
                    candidates.append(path)
        except OSError:
            pass

    # 2) 其余 snapshot（最新修改的排前面）
    try:
        others = [
            os.path.join(snapshots, d)
            for d in os.listdir(snapshots)
            if os.path.isdir(os.path.join(snapshots, d))
        ]
        others.sort(key=os.path.getmtime, reverse=True)
        candidates.extend(p for p in others if p not in candidates)
    except OSError:
        pass

    # 只接受**真的带权重**的目录，否则等于没找到
    for path in candidates:
        if os.path.isfile(os.path.join(path, "model.bin")):
            return path
    return None


def _cached_model_dir(model_size: str) -> Optional[str]:
    """若模型已在本地 HF 缓存中，返回其 snapshot 目录，否则返回 None。

    为什么需要这个：
        faster-whisper 默认把 model_size 交给 huggingface_hub 解析。即使
        模型**已经完整下载**，hub 仍会先联网做一次 revision 校验。
        国内走 hf-mirror 时这一步很容易失败，报：
            An error happened while trying to locate the file on the Hub
            and we cannot find the requested files in the local cache.
        结果就是「模型明明在本地，却加载不了、语音识别一直连不上」。

        实测：把已存在的 snapshot 目录直接传给 WhisperModel 就能完全离线
        加载（1.5GB 的 large-v3-turbo 约 5 秒加载完成）。

    缓存布局（huggingface_hub 标准结构）：
        <hub>/models--<org>--<name>/snapshots/<revision>/...
    """
    try:
        from faster_whisper.utils import _MODELS
    except Exception as exc:
        logger.warning("查找本地缓存失败（导入 faster_whisper 异常）: %s", exc)
        return None

    repo_id = _MODELS.get(model_size)
    if not repo_id:
        # 用户直接给了 repo id 或本地路径：交给 faster-whisper 自己处理
        return None

    searched: list[str] = []
    for root in _cache_roots():
        if not root or not os.path.isdir(root):
            continue
        searched.append(root)
        found = _snapshot_in(root, repo_id)
        if found:
            return found

    logger.info(
        "本地缓存中没有可用的 %s（已查找 %s），将联网解析",
        model_size, "、".join(searched) or "（无可用的缓存目录）",
    )
    return None


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

        # 已缓存则直接用本地目录，绕开 hub 的联网校验（见 _cached_model_dir）
        local_dir = _cached_model_dir(model_size)
        source = local_dir or model_size
        if local_dir:
            logger.info("使用本地缓存模型目录（跳过联网校验）: %s", local_dir)

        try:
            model = WhisperModel(source, device=device, compute_type=compute_type)
        except Exception:
            if not local_dir:
                raise
            # 本地目录加载失败（缓存损坏等）：退回默认行为，让 hub 去修
            logger.warning("本地缓存加载失败，回退到在线解析: %s", model_size, exc_info=True)
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
        # ── 分块参数（方案 C）──
        chunk_max_seconds: float = 25.0,
        chunk_overlap_seconds: float = 0.5,
        chunk_context_chars: int = 120,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.sample_rate = sample_rate

        # 分块上限：语音连续不停时，最多攒这么久就切一块送 Whisper。
        # 这是**兜底**，不是主要切分依据 —— 正常应在自然停顿处收块。
        self.chunk_max_seconds = max(5.0, float(chunk_max_seconds))
        # 硬切时前后块的重叠长度：保证切点附近的字不会被劈掉。
        self.chunk_overlap_seconds = max(0.0, float(chunk_overlap_seconds))
        # 跨块上下文长度：把上一块尾部这么多字符作为下一块的
        # initial_prompt 附加内容，让 Whisper 有前文可参考。
        self.chunk_context_chars = max(0, int(chunk_context_chars))

        # 提示词的紧凑形式（去掉空格），用于识别泄漏结果
        self._prompt_compact = self.INITIAL_PROMPT.replace(" ", "").replace("，", "")

        # 回调
        self.on_partial = on_partial
        self.on_final = on_final
        self.on_vad = on_vad

        # VAD 处理器（只做语音活动检测，不做分块）
        self.vad = VADProcessor(
            sample_rate=sample_rate,
            silence_timeout=silence_timeout,
        )

        # Whisper 模型（懒加载）
        self._model = None

        # 累积的全部转录文本
        self._full_text: str = ""

        # 上一块的尾部文本，作为下一块的上下文提示
        self._context_tail: str = ""

        # ── 并发转录下的上下文串联 ──
        #
        # 各块是并发转录的（每块一个 task），第 2 块可能在 1 块之前完成，
        # 因此不能简单地「完成后滚动更新 _context_tail」——
        # 更常见的情形是：同一轮事件循环里连续切出好几块，
        # 此时 _full_text 还是空的，于是**所有**块都拿不到上文
        # （实测 6 块全是空的 prompt，跨块上下文形同虚设）。
        #
        # 正确做法：给每块分配递增序号，并记录「该块的上文应由哪一块提供」。
        # 每块完成后按序号把文本存进 _chunk_texts，供**尚未开始**的块取用；
        # 由于块是顺序切出来的，序号为 i 的块在启动时会等 i-1 的结果
        # （见 _await_prev_context），从而得到确定性的上下文链。
        self._chunk_seq: int = 0
        self._chunk_texts: dict[int, str] = {}

        # 本块已消费的样本数（用于硬切时定位重叠边界）
        self._segment_consumed: int = 0

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
        # 送入 VAD（只做语音活动检测）
        vad_events = self.vad.process_frame(audio_frame)

        for event in vad_events:
            etype = event["type"]
            ts = event.get("ts", 0.0)

            if etype == "speech_end":
                # 自然断句（静默超过 silence_timeout）→ 这是最理想的收块点，
                # 语义完整、不会被劈词，直接整块取出送转录。
                audio_segment = self.vad.get_buffer_and_reset()
                self._segment_consumed = 0
                if len(audio_segment) > 0:
                    # final=True：断句完成即视为一个完整句子，要立刻推给客户端。
                    # 早期实现用默认的 final=False，导致 on_final 从不触发，
                    # 转写结果只进不出，客户端永远收不到 final。
                    task = asyncio.create_task(
                        self._transcribe_segment(
                            audio_segment, ts, final=True,
                            chunk_seq=self._next_chunk_seq(),
                        )
                    )
                    self._pending_tasks.append(task)

                if self.on_vad:
                    self.on_vad("speech_end")

            elif etype == "speech_pause":
                # 软停顿：只是「这里可以收块」的建议，音频仍在缓冲里。
                # 若当前块已经够长，就在这个自然停顿处收块 ——
                # 这正是方案 C 想要的「切在语义边界上」。
                await self._maybe_flush_on_pause(ts)

            elif etype == "speech_resume":
                # 停顿后继续说话：无需特殊处理，音频本就连续累积在缓冲里。
                # 这里不发事件，避免前端把一次换气误当成一句结束。
                pass

        # 兜底硬上限：语音长时间不停（没有自然停顿可用）时，
        # 到点必须切，否则块会无限增长（识别越来越慢、内存越吃越多）。
        await self._enforce_chunk_ceiling()

    async def _maybe_flush_on_pause(self, ts: float) -> None:
        """在自然停顿处收块（若已积累到有意义的最小长度）。

        为什么设一个下限：换气停顿可能出现在很短的短语后，
        若每次都收块，会把一句话切得太碎，反而破坏连贯性。
        因此只有「够长」的块才在停顿处收。
        """
        buffered = self.vad.buffered_duration()
        if buffered < self._min_chunk_seconds():
            return

        audio_segment = self.vad.get_buffer_and_reset()
        self._segment_consumed = 0
        if len(audio_segment) == 0:
            return

        # 自然停顿处收块仍算 final：语义边界就是句子边界，
        # 前端/主服务按 final 处理即可（partial 只用于边说边显）。
        task = asyncio.create_task(
            self._transcribe_segment(
                audio_segment, ts, final=True, chunk_seq=self._next_chunk_seq(),
            )
        )
        self._pending_tasks.append(task)

    async def _enforce_chunk_ceiling(self) -> None:
        """兜底：连续语音超过 chunk_max_seconds 就强制切一块。

        与早期实现的本质区别（方案 C 的关键）：
            早期 `max_speech_duration` 由 VAD 执行，切完**只挪计时器**，
            切点附近的音频既不保留也不重叠，于是丢字；
            且每 30 秒一刀，切点落在词中间。
            这里改为：
              1. 切点在**上限处**而不是 VAD 认为的句子边界（VAD 已无此职责）；
              2. 保留 `chunk_overlap_seconds` 的音频**放回缓冲头部**，
                 与下一块重叠，保证跨切点的字至少被识别一次；
              3. 重叠部分的文本在拼接时去重（见 _dedupe_overlap）。
        """
        buffered = self.vad.buffered_duration()
        if buffered < self.chunk_max_seconds:
            return

        audio = self.vad.peek_buffer()
        if len(audio) == 0:
            return

        overlap_samples = int(self.chunk_overlap_seconds * self.sample_rate)
        # 保证切开后仍有进展，避免 overlap 大到死循环
        max_overlap = int(len(audio) * 0.5)
        overlap_samples = min(overlap_samples, max_overlap)

        head = audio[: len(audio) - overlap_samples] if overlap_samples else audio
        tail = audio[len(audio) - overlap_samples:] if overlap_samples else None

        # 取走已消费部分，把重叠段放回缓冲给下一块
        self.vad.get_buffer_and_reset()
        if tail is not None and len(tail) > 0:
            self.vad.seed_buffer(tail)

        self._segment_consumed = 0
        logger.debug(
            "块达上限 %.1fs，强制切分（重叠 %.2fs）",
            len(head) / self.sample_rate,
            len(tail) / self.sample_rate if tail is not None else 0.0,
        )

        # 硬切不是语义边界，因此这里标 final=False：
        # 只推 partial 给前端显示，不当作「一句话说完了」交给 AI。
        task = asyncio.create_task(
            self._transcribe_segment(
                head, self.vad._current_time, final=False,
                chunk_seq=self._next_chunk_seq(),
            )
        )
        self._pending_tasks.append(task)

    def _min_chunk_seconds(self) -> float:
        """停顿收块的最小长度：太短就不切，避免把句子剁碎"""
        return max(2.0, self.vad.silence_timeout)

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
        self, audio: np.ndarray, timestamp: float = 0.0, final: bool = False,
        chunk_seq: Optional[int] = None,
    ):
        """异步转录一段音频。

        Args:
            chunk_seq: 本块的序号（按切出顺序递增）。用于串联跨块上下文：
                块 i 会等块 i-1 的文本产出后再取上文，从而在**并发**转录
                的情况下也能得到确定性的上下文链。
                为 None 时视为独立调用（测试 / 单次转录），直接用当前上下文。
        """
        self._ensure_model()

        # ── 等前一块产出，取得本块的上文 ──
        ctx = ""
        if chunk_seq is not None:
            ctx = await self._await_prev_context(chunk_seq)
        else:
            ctx = self._context_tail

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
            #
            # 跨块上下文（方案 C）：把上一块的尾部文本接在标点提示词后，
            # 让 Whisper 知道「前文在讲什么」。这是解决「分块后语义不连贯」的
            # 关键 —— 早期实现每块完全独立（condition_on_previous_text=False
            # 且无任何上下文），于是每块都像在听一段没头没尾的录音。
            segments, info = await asyncio.to_thread(
                self._model.transcribe,
                audio_float32,
                language="zh",
                beam_size=5,
                vad_filter=False,
                initial_prompt=self._build_prompt(ctx),
                # 仍保持关闭：它会让上一段的**用词**漂移到下一段
                # （把前文词汇硬套到新音频上）。上下文改由我们显式、
                # 有长度上限地注入 prompt，更可控。
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

            # 重叠去重：硬切出的块与上一块有音频重叠，
            # 同一段话会被识别两次，这里去掉本块开头与上文重复的部分。
            if new_text:
                new_text = self._dedupe_overlap(new_text, ctx)

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

            # 把本块文本记入序号表，供**后序**块取作上文。
            # 即便本块文本为空也要占位（记空串），否则后序块会一直等下去。
            if chunk_seq is not None:
                self._chunk_texts[chunk_seq] = new_text
                # 上下文游标只在**本块确有产出**时推进。
                #
                # 为什么不用 new_text 无条件覆盖：硬切出的块若被去重后
                # 变成空串（整块都是与上块的重叠内容），把它当作上文
                # 会让后序块拿不到任何语境（实测第 3 块因此退化成裸提示词）。
                # 保留上一次的 _context_tail 更合理：它就是「最近一次
                # 真实识别出的文本」，语义上仍是有效的后文语境。
                if new_text and self.chunk_context_chars > 0:
                    self._context_tail = self._full_text[-self.chunk_context_chars:]

            logger.info(
                "转写片段: %.1fs 音频 → '%s' (lang=%s)",
                len(audio) / self.sample_rate,
                new_text[:80],
                info.language,
            )

        except Exception as e:
            logger.error("Transcription failed: %s", e)

    # ── 跨块上下文与重叠去重（方案 C） ──

    def _next_chunk_seq(self) -> int:
        """分配下一个块序号（按切出顺序，与完成顺序无关）"""
        seq = self._chunk_seq
        self._chunk_seq += 1
        return seq

    async def _await_prev_context(self, chunk_seq: int) -> str:
        """等前序块的文本产出，返回应作为本块上文的尾部片段。

        为什么要等：
            块是并发切出、并发转录的。若不等，块 i 启动时块 i-1 往往
            还没跑完，_full_text 尚为空 —— 实测全部 6 块的 prompt
            都退化成了裸提示词，跨块上下文完全没生效。
            按序号等待即可得到「前文 → 后文」的确定性链条。

        为什么要回退到更早的块：
            硬切块去重后可能变成空串（整块都是重叠内容）。此时
            块 i-1 提供不了语境，应改用 i-2、i-3…中最近的有内容的块，
            否则后序块会退化成裸提示词。

        等待是**有界**的：前序块转录失败（异常）时不会永久阻塞，
        超时后按「无上文」继续，保证主流程永远能推进。
        """
        if chunk_seq <= 0:
            return self._context_tail

        def _from(prev_seq: int) -> Optional[str]:
            t = self._chunk_texts.get(prev_seq)
            if t is None:
                return None
            if not t:
                return ""  # 该块已产出但为空 → 需要继续往前找
            return t[-self.chunk_context_chars:] if self.chunk_context_chars > 0 else t

        def _resolve() -> Optional[str]:
            """返回 None 表示「还在等」，空串表示「等到了但确无上文」"""
            for prev_seq in range(chunk_seq - 1, -1, -1):
                if prev_seq not in self._chunk_texts:
                    return None  # 该前序块尚未完成
                got = _from(prev_seq)
                if got:
                    return got
            return ""

        got = _resolve()
        if got is not None:
            # got 非空 → 用它；got == "" → 前面确实没有可用文本，退回当前游标
            return got or self._context_tail

        # 前序块还在跑：轮询等待（60s 上限，覆盖慢模型的极端情况）
        deadline = 60.0
        waited = 0.0
        step = 0.02
        while waited < deadline:
            got = _resolve()
            if got is not None:
                return got or self._context_tail
            await asyncio.sleep(step)
            waited += step
            if waited > 2.0:
                step = 0.1  # 长时间等不到就降低轮询频率，别空转 CPU

        logger.debug("块 %d 等待上文超时，按无上文继续", chunk_seq)
        return ""

    def _build_prompt(self, context: Optional[str] = None) -> str:
        """构造本块的 initial_prompt：标点提示词 + 上一块尾部文本。

        为什么把上文拼进 prompt 而不是打开 condition_on_previous_text：
            后者会让模型把上一段的**用词**直接套到新音频上（形似而神不似），
            在两个人对话的场景尤其容易串词。
            显式注入有长度上限的上文，既能给模型语境，又不会失控。

        注意长度：Whisper 的 prompt 有 224 token 上限，这里按字符数
        截断（中文约 1 字 1 token 多一点），120 字符是安全值。
        """
        tail = self._context_tail if context is None else context
        if not tail or self.chunk_context_chars <= 0:
            return self.INITIAL_PROMPT
        # 兜底截断：调用方一般已按 chunk_context_chars 截过，
        # 但 _context_tail 也可能被整体赋值（如 reset 后又累积），
        # 这里再裁一次，避免 prompt 超出 Whisper 的长度上限。
        return f"{self.INITIAL_PROMPT}{tail[-self.chunk_context_chars:]}"

    def _dedupe_overlap(self, text: str, context: Optional[str] = None) -> str:
        """去掉本块开头与上一块结尾重复的部分（硬切重叠导致的重复识别）。

        硬切时前后块有 0.5s 音频重叠，重叠区间的话会被识别两次：
            上一块: '...我觉得这个项目'
            本块  : '这个项目最大的难点是...'
        朴素的字符串去重会误伤正常重复，因此只处理「本块开头是
        上文后缀」这一种形态，并限制在合理长度内（<= 24 字）。
        """
        prev = self._context_tail if context is None else context
        if not prev or not text:
            return text

        # 从长到短找「本块开头 == 上文结尾」的最长匹配
        max_probe = min(len(text), len(prev), 24)
        for n in range(max_probe, 1, -1):
            if prev.endswith(text[:n]):
                stripped = text[n:].lstrip("，,、；;：: ")
                # 全被去掉了说明本块整段都是重叠内容 → 不重复推送
                return stripped
        return text

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
        self._context_tail = ""
        self._segment_consumed = 0
        self._chunk_seq = 0
        self._chunk_texts = {}
        self._pending_tasks.clear()
        self.vad._reset()
