/**
 * useSystemAudioListener — 系统音频监听
 *
 * 设计（第二版，替代早期「绑在组件挂载周期上」的实现）：
 *
 *   监听是**持续状态**，不是「随页面出现/消失的动作」。
 *   早期实现把 start/stop 放进 useEffect 的挂载/清理里，
 *   于是 React StrictMode、路由切换、zustand persist 水合
 *   都会把它拆掉重建，表现为：
 *     - 日志里密集的「捕获已停止 / 已启动」
 *     - 界面显示「等待进入对话页」，实际后端已被停掉
 *     - 每次都丢失已识别的文字
 *
 *   现在改为：
 *     1) start 只在「开关从未开变为开」时调用一次（边沿触发，不是电平触发）；
 *     2) 组件重挂载只负责「接管轮询」，不会去动后端会话；
 *     3) 只有开关真正关闭 / 明确离开对话页时，才停止后端捕获；
 *     4) 轮询游标放在**模块级**（sharedSince），重挂载不会归零 —— 否则
 *        切走再切回会把服务端缓冲里的历史逐条重放一遍；
 *     5) 页面刷新后首次轮询只对齐游标，不回放本次加载之前的历史。
 *
 *   后端 /system-audio/start 也是幂等的：即使前端多调一次，
 *   只要设备没变，它也会复用现有会话而不是重建。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { systemAudioApi } from '@/api/systemAudio'
import { useAppStore } from '@/stores/appStore'

const POLL_INTERVAL = 1000

/**
 * 关闭开关后，延迟多久才真正停掉后端捕获。
 *
 * 给一个缓冲窗口：若期间开关又被打开（或页面重新挂载），
 * 就取消这次停止，避免一次误触发把正在进行的监听打断。
 */
const STOP_GRACE_MS = 1200

/**
 * 已消费到的最大 seq —— 刻意放在**模块级**，而不是组件里的 useRef。
 *
 * 为什么：切到左侧别的标签页会让 ChatPage 卸载，再切回来时组件是全新的，
 * useRef 会重置成 0；而服务端的转写缓冲还在（SYSTEM_AUDIO_TRANSCRIPT_BUFFER
 * 默认 200 条）。于是 `transcript(0)` 把整段历史原样返回，onText 被逐条
 * 调用 —— 用户看到的就是「清空对话 → 切走 → 切回，之前的语音又逐条输出了
 * 一遍」，而且每条都会重新触发一次提问。
 *
 * 放在模块级后：
 *   - 同一次页面会话内，卸载/重挂载都从上次的位置继续，既不重放也不丢；
 *   - 页面刷新时模块状态归零，由第一次轮询向服务端取游标（不回放历史）。
 *
 * null = 本次页面会话尚未同步过。
 */
let sharedSince: number | null = null
/** 是否已有一次「首同步」在飞行中，避免并发轮询重复取基准 */
let seeding = false

export interface ListenerOptions {
  /** 是否处于 AI 对话界面（false 时停止监听） */
  active: boolean
  /** 每识别出一段完整的话就回调（final） */
  onText?: (text: string) => void
  /** 出错时回调 */
  onError?: (message: string) => void
}

export function useSystemAudioListener({ active, onText, onError }: ListenerOptions) {
  const enabled = useAppStore((s) => s.systemAudioEnabled)
  const device = useAppStore((s) => s.systemAudioDevice)

  const [listening, setListening] = useState(false)
  const [sttConnected, setSttConnected] = useState(false)
  const [sttError, setSttError] = useState<string | null>(null)

  // 已消费到的最大 seq（模块级，见 sharedSince 的注释）。
  // 只增不减：后端序号来自进程级计数器，正常只会变大；
  // 只有后端重启（序号从头开始）时才回零，见 poll()。
  const timerRef = useRef<number | null>(null)
  const stopTimerRef = useRef<number | null>(null)
  // 是否已经向后端发起过 start（用于边沿触发判断）
  const startedRef = useRef(false)
  // 停止令牌：用于识别「这次停止是否已被后续的重新开启作废」
  const stopTokenRef = useRef<number>(0)

  // 回调与配置放 ref，避免它们变化导致轮询/启动被反复重建
  const onTextRef = useRef(onText)
  const onErrorRef = useRef(onError)
  const deviceRef = useRef(device)
  onTextRef.current = onText
  onErrorRef.current = onError
  deviceRef.current = device

  /** 拉取增量转写并按需派发 */
  const poll = useCallback(async () => {
    try {
      // ── 本页面会话的第一次轮询：只取游标，不回放历史 ──
      //
      // 服务端缓冲里可能还留着本次页面加载之前识别的内容（比如上一轮
      // 对话的语音）。直接 transcript(0) 会把它们整批当新消息派发出去。
      // 这里把游标对齐到服务端的 latest_seq，历史就「已消费」了。
      if (sharedSince === null) {
        if (seeding) return
        seeding = true
        try {
          const snapshot = await systemAudioApi.transcript(0)
          sharedSince = snapshot.latest_seq
          setSttConnected(snapshot.stt_connected)
          setSttError(snapshot.stt_error ?? null)
          setListening(snapshot.running)
        } catch (err) {
          sharedSince = null // 失败就保持未同步，下次轮询重试
          throw err
        } finally {
          seeding = false
        }
        return
      }

      const res = await systemAudioApi.transcript(sharedSince)

      // 后端重启过：进程级序号计数器从头开始，旧游标（比如 42）会让
      // `seq > since` 恒不成立，表现为「监听开着但一个字都不出」。
      // 此时必须把游标归零，宁可重放一小段也不能永久卡死。
      if (res.latest_seq < sharedSince) {
        sharedSince = 0
      }

      if (res.lines.length > 0) {
        // 取本批最大 seq 推进游标（用 max 而不是直接赋值，
        // 防止后端返回乱序时游标倒退）
        const maxSeq = res.lines.reduce((m, l) => Math.max(m, l.seq), sharedSince)
        sharedSince = maxSeq

        for (const line of res.lines) {
          // 只把「断句完成」的文本交给上层：partial 是边说边变的，
          // 拿去提问会得到半句话。
          if (line.kind === 'final' && line.text.trim()) {
            onTextRef.current?.(line.text.trim())
          }
        }
      }

      setSttConnected(res.stt_connected)
      setSttError(res.stt_error ?? null)
      setListening(res.running)

      if (!res.running) {
        // 后端会话确实没了（被别处停掉 / 服务重启）
        startedRef.current = false
      }
    } catch (err) {
      onErrorRef.current?.((err as Error).message)
    }
  }, [])

  // ── 轮询：只要在监听就拉，与组件挂载解耦 ──
  useEffect(() => {
    if (!listening) {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current)
        timerRef.current = null
      }
      return
    }
    void poll()
    timerRef.current = window.setInterval(() => void poll(), POLL_INTERVAL)
    return () => {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [listening, poll])

  // ── 监听开关：边沿触发 ──
  const shouldRun = enabled && active

  useEffect(() => {
    if (!shouldRun) return

    // 取消上一轮排队中的「停止」：既然又要监听了，就别停
    if (stopTimerRef.current !== null) {
      window.clearTimeout(stopTimerRef.current)
      stopTimerRef.current = null
    }

    // 已经在跑就不再重复 start。
    // 后端 start 虽已幂等，但少发一次请求总归更干净，
    // 也避免「重挂载 → 再 start」在日志上造成误判。
    if (startedRef.current) return

    let cancelled = false

    const begin = async () => {
      try {
        const res = await systemAudioApi.start({
          device_id: deviceRef.current || undefined,
        })
        if (cancelled) return
        startedRef.current = true
        setListening(true)
        setSttConnected(res.stt_connected)
        setSttError(res.stt_error ?? null)
      } catch (err) {
        if (cancelled) return
        startedRef.current = false
        setListening(false)
        onErrorRef.current?.((err as Error).message)
      }
    }

    void begin()

    return () => {
      cancelled = true
      // 注意：这里**不停止**后端捕获。
      //
      // StrictMode 的「挂载 → 卸载 → 再挂载」会走一次 cleanup，
      // 停在这里就会把监听打断（早期 bug 的根源）。
      // 真正的停止只由下面那个「开关关闭」的 effect 负责。
    }
  }, [shouldRun])

  // ── 开关关闭 / 离开对话页：延迟停止 ──
  useEffect(() => {
    if (shouldRun) return
    if (!startedRef.current) return

    const myToken = Date.now()
    stopTokenRef.current = myToken

    stopTimerRef.current = window.setTimeout(() => {
      stopTimerRef.current = null
      // 期间开关又被打开（token 变了）→ 取消这次停止
      if (stopTokenRef.current !== myToken) return
      if (!startedRef.current) return

      startedRef.current = false
      setListening(false)
      void systemAudioApi.stop().catch(() => {})
    }, STOP_GRACE_MS)

    return () => {
      if (stopTimerRef.current !== null) {
        window.clearTimeout(stopTimerRef.current)
        stopTimerRef.current = null
      }
    }
  }, [shouldRun])

  // 组件真正卸载时，清掉待执行的定时器（不发停止请求：
  // 卸载可能只是 StrictMode 往返或路由瞬时切换，
  // 后端会话由开关状态与幂等 start 保证一致）
  useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current)
      if (stopTimerRef.current !== null) window.clearTimeout(stopTimerRef.current)
      timerRef.current = null
      stopTimerRef.current = null
    }
  }, [])

  return { listening, sttConnected, sttError }
}
