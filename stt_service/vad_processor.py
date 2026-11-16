"""
Silero VAD 流式处理器
实时检测语音活动（speech/silence），输出语音段边界事件。
"""

import logging
import os
import threading
from enum import Enum
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# 本模块所在目录（stt_service/），用于定位随包分发的 VAD 模型
_HERE = os.path.dirname(os.path.abspath(__file__))


class VADState(Enum):
    SILENCE = "silence"
    SPEECH = "speech"


# ══════════════════════════════════════════════════════════════
# Silero VAD 的输入约束
# ══════════════════════════════════════════════════════════════
#
# Silero 的 ONNX 模型对单次调用的样本数有**硬性要求**：
#   8kHz  → 256 样本
#   16kHz → 512 样本
# 而本模块的帧长是 100ms（16kHz 下 1600 样本），直接喂进去会抛
# ValueError: Provided number of samples is 1600 (Supported values: ...)。
#
# 早期实现把这次异常吞掉并当成 speech_prob=0，结果**永远检测不到语音**，
# speech_end 一次都不会触发，转写自然永远是空的。
# 正确做法是把一帧切成 512 样本的小块，逐块推理后取最大概率。
VAD_WINDOW_SAMPLES = {8000: 256, 16000: 512}

# ══════════════════════════════════════════════════════════════
# Silero VAD —— 直接走 onnxruntime，不依赖 torch
# ══════════════════════════════════════════════════════════════
#
# 背景（为什么不用 torch.hub.load）：
#   此前用 torch.hub.load(..., onnx=True) 拿模型。它实际返回的也只是
#   silero_vad.utils_vad.OnnxWrapper —— 内部照样是 onnxruntime 推理，
#   torch 在这里**只承担「下载 + 解包 + 传参包装」**，一次矩阵运算都不做。
#   代价却是整个 torch（本机 2.5.1+cu121，2~3GB），且首次加载要走
#   GitHub 拉仓库（实测约 15 秒，国内不稳），还发生在服务启动路径上。
#
#   现在改为直接加载本地 .onnx + onnxruntime，行为与 OnnxWrapper
#   **逐位一致**（已验证 max|Δ| = 0.0）。
#
# ⚠️ 两个必须照抄的细节，漏掉任何一个都会让 VAD 静默失准：
#
#   1) context 前置：每次推理前要把**上一次输入的末尾 64 个样本**拼到
#      当前 512 样本前面，一起送进模型（输入因此是 576 样本）。
#      这是 Silero 官方 wrapper 的做法，不是可选项 —— 少了它，
#      同一段音频算出的概率完全不同（实测 0.102 → 0.0006）。
#
#   2) state 跨调用累积：模型是**有状态 RNN**，每帧返回的 stateN 必须
#      喂给下一帧。早期注释写「模型本身无状态，可安全共享」是错的。
#
# 因此共享的是 session（无状态、线程安全），state/context 必须
# **每个 VADProcessor 各持一份** —— 见 SileroVadSession。
_hub_lock = threading.Lock()
_silero_cache: dict = {}


def _find_vad_model() -> str:
    """定位 Silero VAD 的 .onnx 文件。

    查找顺序（先本地、后缓存，避免任何联网行为）：
      1) 环境变量 SILERO_VAD_ONNX 显式指定
      2) 项目内 stt_service/models/silero_vad.onnx（随仓库分发）
      3) torch.hub 的历史缓存（老用户机器上已经有了，直接复用不必重下）

    找不到时抛 FileNotFoundError，并把「怎么办」写进错误信息 ——
    静默返回 None 只会让 VAD 永远检测不到语音，且日志里看不出原因。
    """
    candidates: list[str] = []

    env_path = os.getenv("SILERO_VAD_ONNX", "").strip()
    if env_path:
        candidates.append(env_path)

    candidates.append(os.path.join(_HERE, "models", "silero_vad.onnx"))

    # torch.hub 缓存：老机器上已存在，顺带兼容，省一次下载
    hub_root = os.getenv("TORCH_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache", "torch"
    )
    candidates.append(
        os.path.join(
            hub_root, "hub", "snakers4_silero-vad_master",
            "src", "silero_vad", "data", "silero_vad.onnx",
        )
    )

    for path in candidates:
        if path and os.path.isfile(path):
            return path

    raise FileNotFoundError(
        "找不到 Silero VAD 模型文件 silero_vad.onnx。已查找："
        + "、".join(p for p in candidates if p)
        + "。请将 silero_vad.onnx 放到 "
        + os.path.join(_HERE, "models")
        + " 下，或用环境变量 SILERO_VAD_ONNX 指定路径。"
    )


def _get_shared_silero_session():
    """取（或首次创建）进程级共享的 onnxruntime InferenceSession。

    只共享 session：它是无状态的，且 onnxruntime 的 run() 可重入。
    每帧变化的 state / context 由调用方各持一份（见 SileroVadSession）。
    """
    with _hub_lock:
        if "session" in _silero_cache:
            return _silero_cache["session"]

        import onnxruntime

        path = _find_vad_model()

        # 与官方 OnnxWrapper 一致：单线程算子，避免与主服务的线程池争抢。
        # 顺带规避 onnxruntime 在小张量上多线程反而更慢的问题。
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1

        # 默认 CPU：VAD 每次只算 576 样本，模型仅 2MB，
        # 放 GPU 的拷贝开销大于收益，还会与 Whisper 争显存。
        #
        # 注意取值写法：默认值必须是 "true" 而不是 "1" ——
        # 这里比较的是字符串，写 "1" 会让 `"1".lower() == "true"`
        # 恒为 False，于是默认反而落到「用全部 provider」的分支，
        # 实际选中 AzureExecutionProvider（需联网、引入额外延迟）。
        force_cpu = os.getenv("SILERO_VAD_FORCE_CPU", "true").strip().lower()
        if force_cpu in ("1", "true", "yes", "on"):
            # 显式只给 CPU，避免本机 get_available_providers() 返回的
            # AzureExecutionProvider 被排到第一位。
            chosen = ["CPUExecutionProvider"]
        else:
            chosen = onnxruntime.get_available_providers()

        logger.info("首次加载 Silero VAD（onnxruntime, %s）: %s", chosen[0], path)
        session = onnxruntime.InferenceSession(
            path, sess_options=opts, providers=chosen
        )

        _silero_cache["session"] = session
        logger.info("Silero VAD 已加载并缓存，后续连接直接复用")
        return session


class SileroVadSession:
    """Silero VAD 的一次「会话」—— 持有 state 与 context。

    为什么必须独立于共享 session：
        VADProcessor 是**每个 WebSocket 连接一个**（main.py 里每个连接
        新建 StreamingTranscriber），而 InferenceSession 是进程级共享的。
        如果把 state 存在 model 上（torch 版 OnnxWrapper 就是如此），
        两个连接会互相污染对方的状态，表现为转写串音、丢字。

    接口与原 torch 版保持兼容：可调用对象，接收 (chunk, sample_rate)，
    返回单元素数组（调用方取 .item()），从而 _speech_probability 无需改动。
    """

    # 16kHz 与 8kHz 的窗口/上下文长度（与官方 wrapper 一致）
    _WINDOW = {8000: 256, 16000: 512}
    _CONTEXT = {8000: 32, 16000: 64}

    def __init__(self, session, sample_rate: int = 16000):
        self._session = session
        self.sample_rate = sample_rate
        self._batch_size = 1
        self._context_size = self._CONTEXT[sample_rate]
        self.reset_states()

    def reset_states(self) -> None:
        """清空状态。**必须**在新的音频流开始时调用。

        不重置的后果：上一段音频的 RNN 状态会污染下一段，
        且 context 里残留旧样本，概率值随之偏移。
        """
        self._state = np.zeros((2, self._batch_size, 128), dtype=np.float32)
        self._context = np.zeros((self._batch_size, self._context_size), dtype=np.float32)

    def __call__(self, chunk: np.ndarray, sample_rate: int = 16000):
        """推理一个窗口，返回 shape (1,1) 的概率数组。

        chunk 长度必须等于 _WINDOW[sample_rate]（16k→512），
        否则 onnxruntime 会因为形状不符而报错 —— 这里提前校验并
        给出可读的错误，避免上层只看到 ORT 的晦涩提示。
        """
        expected = self._WINDOW.get(sample_rate)
        if expected is None:
            raise ValueError(f"Silero VAD 不支持的采样率: {sample_rate}")

        x = np.asarray(chunk, dtype=np.float32).reshape(1, -1)
        if x.shape[1] != expected:
            raise ValueError(
                f"Silero VAD 输入样本数应为 {expected}（{sample_rate}Hz），"
                f"实际收到 {x.shape[1]}"
            )

        # 关键细节 1：拼上上一帧末尾的 context（512 → 576）
        x = np.concatenate([self._context, x], axis=1)

        # 关键细节 2：state 跨帧传递，输出回写
        out, state = self._session.run(
            None,
            {
                "input": x,
                "state": self._state,
                "sr": np.array(sample_rate, dtype=np.int64),
            },
        )
        self._state = state
        self._context = x[..., -self._context_size:]
        return out


def _get_shared_silero():
    """取共享 session 并包出一份**独立的**会话状态。

    返回 (SileroVadSession, None)。第二个元素保留是为了兼容既有调用方
    的解包写法（原先返回 (model, get_speech_timestamps)，而后者在本
    项目中从未被使用 —— 状态机是 VADProcessor 自己实现的）。
    """
    session = _get_shared_silero_session()
    return SileroVadSession(session, sample_rate=16000), None


class VADProcessor:
    """Silero VAD 流式处理器 —— **只做语音活动检测，不做分块决策**

    职责边界（方案 C 的核心）：
        本类只回答「此刻有没有人在说话」，并给出**语音区间**的边界事件；
        「什么时候把音频切一块送去 Whisper」由上层 chunker 决定
        （见 streaming_transcriber._ChunkBuffer）。

    为什么要把这件事拆出来：
        早期实现里 VAD 自己带一个 max_speech_duration=30s，到点就
        **强制 speech_end 并把音频交出去**。这带来两个问题：
          1. 切点落在任意位置（一段连续语流每 30 秒被剁一刀），
             很可能把一个词劈成两半；
          2. 强制切分只挪动计时器、不保留跨切点的音频，
             切点附近的字直接丢掉。
        一段 150 秒、中途无长停顿的自我介绍因此被切成 6 段碎片，
        语义接不上且缺字。VAD 不该有「切多长」的意见。

    参数（均可通过环境变量覆盖）：
    - speech_threshold: 语音概率 > 此值判定为语音（默认 0.5）
    - silence_timeout: 连续静默多少秒触发 speech_end（默认 1.0s）
    - min_speech_duration: 最短语音段（默认 0.3s，短于此忽略）
    - pause_hint: 静默到什么程度就发 speech_pause 软事件（默认 0.4s）。
      它只是**建议**：上层可据此在自然停顿处收块，但缓冲不动、音频不丢。
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        speech_threshold: float = 0.5,
        silence_timeout: float = 1.0,
        min_speech_duration: float = 0.3,
        max_speech_duration: float = 30.0,
        preroll_seconds: float = 0.3,
        pause_hint: float = 0.4,
    ):
        self.sample_rate = sample_rate
        self.speech_threshold = speech_threshold
        self.silence_timeout = silence_timeout
        self.min_speech_duration = min_speech_duration
        # 仅保留为兼容字段：真正的分块上限已交给上层 chunker。
        # 留在这里是为了让调用方传参不会报错，且便于日志对比。
        self.max_speech_duration = max_speech_duration
        # 软停顿提示阈值：严格小于 silence_timeout，否则会与断句同时触发。
        self.pause_hint = min(max(0.0, pause_hint), max(0.0, silence_timeout))
        # 语音起点前保留的音频长度：VAD 需要几帧才能确认「开始说话」，
        # 不留前置缓冲会把第一个字吃掉（听感上就是「断头」）。
        self.preroll_seconds = max(0.0, preroll_seconds)

        # Silero VAD 模型（懒加载）
        self._model = None
        self._get_speech_timestamps = None

        # 状态机
        self._state: VADState = VADState.SILENCE
        self._speech_start_time: Optional[float] = None
        self._silence_start_time: Optional[float] = None
        self._current_time: float = 0.0
        # 本次静默是否已发过 speech_pause 软提示（避免每帧重复通知）
        self._pause_notified: bool = False

        # 正在累积的语音段音频
        self._buffer: list[np.ndarray] = []
        # 语音开始前的滑动窗口（只保留最近 preroll_seconds 的帧）
        self._preroll: list[np.ndarray] = []
        self._preroll_samples = int(self.preroll_seconds * sample_rate)

    # ── 懒加载模型 ──

    def _ensure_model(self):
        """确保 Silero VAD 模型可用（复用进程级共享 session）

        与 Whisper 同理：模型加载慢，每个连接各加载一份会白白浪费
        时间与显存。session 本身无状态，可安全共享；
        每帧变化的 state/context 由本实例独享（见 SileroVadSession）。
        """
        if self._model is not None:
            return
        self._model, self._get_speech_timestamps = _get_shared_silero()
        # 新连接是一段全新的音频流：必须清空 RNN 状态，
        # 否则会继承上一个连接的残留状态与 context。
        self._model.reset_states()

    # ── 核心：逐帧处理 ──

    def _speech_probability(self, audio_frame: np.ndarray) -> float:
        """算一帧的语音概率。

        Silero 只接受固定长度的输入（16kHz → 512 样本），因此把整帧切成
        若干 512 样本的窗口逐块推理，取**最大**概率：
        只要帧内有任意一段像语音，就认为这一帧在说话（宁可多检测，
        也不要漏掉说话，漏检会导致整句不转录）。

        尾部不足一个窗口的样本直接丢弃：它们会在下一帧里重新出现，
        不会造成信息丢失。
        """
        window = VAD_WINDOW_SAMPLES.get(self.sample_rate)
        if window is None:
            # 非常规采样率：不猜，直接按「非语音」处理并提示
            logger.warning("Silero VAD 不支持 %d Hz，语音检测已跳过", self.sample_rate)
            return 0.0

        audio = np.asarray(audio_frame, dtype=np.float32).reshape(-1)
        if audio.size < window:
            return 0.0

        best = 0.0
        for start in range(0, audio.size - window + 1, window):
            chunk = audio[start:start + window]
            try:
                # 不再需要 torch.from_numpy：onnxruntime 直接吃 numpy。
                # 这是每帧都在跑的热路径，省掉一次张量包装。
                prob = float(self._model(chunk, self.sample_rate).item())
            except Exception as exc:
                # 这里不再静默吞掉：早期版本把 ValueError 当成 prob=0，
                # 导致语音永远检测不到，且完全没有日志可查。
                logger.warning("Silero VAD 推理失败: %s", exc)
                return 0.0
            if prob > best:
                best = prob
                if best >= 0.99:
                    break
        return best

    def process_frame(
        self,
        audio_frame: np.ndarray,
        timestamp: Optional[float] = None,
    ) -> list[dict]:
        """
        处理一帧音频，返回触发的事件列表。

        Args:
            audio_frame: float32 numpy array, shape (n_samples,), 16kHz mono
            timestamp: 此帧对应的时间戳（秒），None 则自动推算

        Returns:
            list[dict]: 事件列表，每个事件格式:
                {"type": "speech_start", "ts": float}
                {"type": "speech_end", "ts": float}
        """
        self._ensure_model()

        # 更新时间
        frame_duration = len(audio_frame) / self.sample_rate
        if timestamp is not None:
            self._current_time = timestamp
        ts = self._current_time

        # VAD 检测：使用 Silero 模型判断当前帧是否为语音
        speech_prob = self._speech_probability(audio_frame)
        is_speech = speech_prob > self.speech_threshold

        # 累积 buffer 的策略决定了转录质量与速度：
        #
        # 早期实现把**每一帧**都塞进 buffer，静音也不例外。后果：
        #   - 用户说完一句话后，前面的几十秒静音也一起送去转录，
        #     Whisper 在静音上白跑（实测出现过 44s / 77s 的片段），
        #     既慢又容易产生与内容无关的幻觉文本；
        #   - 两次说话之间只要没触发断句，就会被并成一大段。
        #
        # 现在改为：
        #   - 静默状态：帧进**滑动窗口** _preroll，只保留最近
        #     preroll_seconds 秒（用于接住被 VAD 判定延迟的起头字）；
        #   - 一旦判定开始说话：把窗口里的帧作为前置缓冲并入 buffer，
        #     之后只累积说话期间的帧。
        # 顺序很关键：从静默切到语音的**那一帧**必须先让前置窗口入 buffer，
        # 再把自己追加进去。早期实现是先 _append_frame（当前帧进 buffer）、
        # 之后才 _promote_preroll（把更早的帧 extend 到它后面），于是开头
        # 变成「最新一帧 + 之前的 0.3 秒」，等于把起头那个字倒着重放了一遍。
        # Whisper 上只表现为开头含糊，Qwen3-ASR 会直接把它听成「你你」。
        if self._state == VADState.SILENCE and is_speech:
            self._promote_preroll()
        self._append_frame(audio_frame, is_speech)

        events = []

        if self._state == VADState.SILENCE:
            if is_speech:
                # 静默 → 语音：记录开始时间，但并不立即触发 speech_start
                # 等积累到 min_speech_duration 后才正式触发
                self._state = VADState.SPEECH
                self._speech_start_time = ts
                self._silence_start_time = None
                self._pause_notified = False
        else:  # SPEECH
            # 注意：不能写 `self._speech_start_time or ts` —— 语音从第 0 秒
            # 就开始时，_speech_start_time 是 0.0（falsy），会被错误地替换成
            # ts，算出 speech_duration=0，从而走进「语音太短，忽略」分支，
            # 整段语音被丢弃且不报错。
            start = self._speech_start_time
            # 时长只算到「静默开始」为止：ts 在静默期间仍在推进，
            # 若用 ts 计算，一声 0.1 秒的咳嗽也会因为后面 1 秒静默
            # 被算成 1.1 秒，min_speech_duration 形同失效。
            end = self._silence_start_time if self._silence_start_time is not None else ts
            speech_duration = end - (start if start is not None else end)
            if not is_speech:
                # 可能开始静默
                if self._silence_start_time is None:
                    self._silence_start_time = ts
                silence_duration = ts - self._silence_start_time

                # ── 软停顿提示（方案 C）──
                # 停顿达到 pause_hint 就先告诉上层「这里是个自然停顿」，
                # 让它有机会在语义完整处收块，而不必等到整句结束。
                #
                # 关键：这里**不动 buffer、不改状态**，纯通知。
                # 早期实现在这一步就把音频切走（强制 speech_end），
                # 于是 30 秒一到就把连续语流剁成碎片并丢掉切点附近的字。
                if (
                    not self._pause_notified
                    and self.pause_hint > 0
                    and silence_duration >= self.pause_hint
                    and speech_duration >= self.min_speech_duration
                ):
                    self._pause_notified = True
                    events.append({"type": "speech_pause", "ts": ts,
                                   "pending": speech_duration})

                # 静默超时 → 触发 speech_end
                if silence_duration >= self.silence_timeout:
                    if speech_duration >= self.min_speech_duration:
                        events.append({"type": "speech_end", "ts": ts,
                                       "duration": speech_duration})
                        # 关键：保留 buffer，调用方要取走这段音频去转录
                        self._reset(keep_buffer=True)
                    else:
                        # 语音太短，忽略（这段音频没有价值，直接丢弃）
                        logger.debug(
                            "Speech too short (%.2fs), ignored", speech_duration
                        )
                        self._reset()
            else:
                # 仍在说话，清除静默计时
                # 停顿后重新开口：告知上层「语音继续」，便于 chunker
                # 决定是接在同一块里还是另起一块。
                if self._silence_start_time is not None:
                    self._pause_notified = False
                    events.append({"type": "speech_resume", "ts": ts})
                self._silence_start_time = None

                # 注意：这里**不再**做 max_speech_duration 强制切分。
                # 到什么长度该切块是上层 chunker 的事（它会带 overlap
                # 与跨块上下文），VAD 只负责报告语音仍在持续。

        self._current_time += frame_duration
        return events

    def get_buffer_and_reset(self) -> np.ndarray:
        """获取累积的音频 buffer 并清空"""
        if not self._buffer:
            return np.array([], dtype=np.float32)
        audio = np.concatenate(self._buffer)
        self._buffer = []
        return audio

    def is_speech(self) -> bool:
        """当前是否在语音中"""
        return self._state == VADState.SPEECH

    @property
    def state(self) -> VADState:
        return self._state

    @property
    def speech_duration(self) -> float:
        """当前语音段已持续秒数"""
        if self._speech_start_time is None:
            return 0.0
        return self._current_time - self._speech_start_time

    # ── 内部 ──

    def _append_frame(self, frame: np.ndarray, is_speech: bool) -> None:
        """按当前状态决定这一帧进哪里。

        - 正在说话：进正式 buffer
        - 静默（包括「说话后等待断句」的那段静音，以及说话前）：进滑动窗口

        注意不能简单用 `state == SPEECH` 判断：断句要等 silence_timeout
        秒静默才触发，期间 state 仍是 SPEECH，若无条件写入，
        每段尾巴都会拖上 1 秒静音，长录音里累积起来很可观。
        """
        in_speech = is_speech and self._silence_start_time is None
        if in_speech:
            self._buffer.append(frame)
        else:
            self._preroll.append(frame)
            self._trim_preroll()

    def _trim_preroll(self) -> None:
        """把前置窗口裁剪到 preroll_seconds 以内"""
        if self._preroll_samples <= 0:
            self._preroll = []
            return

        total = sum(len(f) for f in self._preroll)
        while len(self._preroll) > 1 and total - len(self._preroll[0]) >= self._preroll_samples:
            total -= len(self._preroll.pop(0))

    def _promote_preroll(self) -> None:
        """开始说话时，把前置窗口的帧并入 buffer（接住起头字）"""
        if self._preroll:
            self._buffer.extend(self._preroll)
            self._preroll = []

    def _reset(self, *, keep_buffer: bool = False):
        """重置状态机。

        keep_buffer=True 时保留音频缓冲 —— 触发 speech_end 后必须保留，
        调用方要拿这段音频去转录（get_buffer_and_reset 会取走并清空）。
        早期实现无条件清空 buffer，导致 speech_end 之后取到的是空音频，
        转录结果永远是空的。
        """
        self._state = VADState.SILENCE
        self._speech_start_time = None
        self._silence_start_time = None
        self._pause_notified = False
        # 前置窗口每次都清：新的一段语音应有自己的起头缓冲，
        # 留着上一段的尾巴会把两句话粘在一起。
        self._preroll = []
        if not keep_buffer:
            self._buffer = []

    # ── 供上层 chunker 使用的区间信息 ──

    def buffered_duration(self) -> float:
        """当前缓冲里累积的音频秒数（未取走的）"""
        if not self._buffer:
            return 0.0
        return sum(len(f) for f in self._buffer) / self.sample_rate

    def peek_buffer(self) -> np.ndarray:
        """查看当前缓冲（**不取走、不清空**）。

        chunker 需要在硬上限处「先看后切」：既要取出该出块的音频，
        又要保留一段 overlap 在缓冲里给下一块用。
        get_buffer_and_reset 是一次性取走语义，做不到这件事。
        """
        if not self._buffer:
            return np.array([], dtype=np.float32)
        return np.concatenate(self._buffer)

    def drop_consumed_prefix(self, n_samples: int) -> None:
        """从缓冲头部丢弃已消费的 n_samples（用于只取走一部分）。"""
        if n_samples <= 0 or not self._buffer:
            return
        remaining = n_samples
        while self._buffer and remaining > 0:
            head = self._buffer[0]
            if len(head) <= remaining:
                remaining -= len(head)
                self._buffer.pop(0)
            else:
                self._buffer[0] = head[remaining:]
                remaining = 0

    def seed_buffer(self, audio: np.ndarray) -> None:
        """把一段音频放回缓冲头部（用于硬切后保留 overlap）"""
        if audio is None or len(audio) == 0:
            return
        self._buffer.insert(0, np.asarray(audio, dtype=np.float32))
