/**
 * VoiceInputPanel — 语音输入面板
 *
 * 交互模式：
 * - 按住按钮说话 / 按住空格键说话 → 松手停止 → 自动发送
 * - 支持选择麦克风设备
 */

import React, { useState, useCallback, useRef, useEffect } from 'react'
import { Button, Typography, Tag, App, Select, Tooltip } from 'antd'
import {
  AudioOutlined,
  CloseOutlined,
  LoadingOutlined,
} from '@ant-design/icons'
import { useVoiceRecorder, getAudioDevices, type AudioDevice } from '@/hooks/useVoiceRecorder'
import { useSTTWebSocket } from '@/hooks/useSTTWebSocket'
import { useAppStore } from '@/stores/appStore'
import { transcribeAudio } from '@/api/stt'

const { Text } = Typography

type PanelState = 'idle' | 'speaking' | 'processing'

interface VoiceInputPanelProps {
  onResult: (text: string) => void
  disabled?: boolean
}

const VoiceInputPanel: React.FC<VoiceInputPanelProps> = ({ onResult, disabled }) => {
  const { message } = App.useApp()
  const autoPlayTTS = useAppStore((s) => s.autoPlayTTS)

  const [panelState, setPanelState] = useState<PanelState>('idle')
  const [partialText, setPartialText] = useState('')
  const [speakingDuration, setSpeakingDuration] = useState(0)
  const [devices, setDevices] = useState<AudioDevice[]>([])
  const [selectedDevice, setSelectedDevice] = useState<string>('default')
  const timerRef = useRef<number | null>(null)
  const pendingResultRef = useRef(false)

  // STT WebSocket
  const sttWs = useSTTWebSocket({
    onPartial: (text) => {
      setPartialText(text)
      setPanelState('speaking')
    },
    onFinal: (text) => {
      setPartialText('')
      pendingResultRef.current = true
      onResult(text)
      resetPanel()
    },
    onError: (err) => {
      message.error(`语音识别错误: ${err}`)
      setPanelState('idle')
    },
  })

  // 录音器（传入设备 ID + 回调）
  const recorder = useVoiceRecorder({
    deviceId: selectedDevice,
    onAudioFrame: (frame) => sttWs.sendAudioFrame(frame),
  })

  // 加载麦克风设备列表
  useEffect(() => {
    getAudioDevices().then(setDevices).catch(() => {})
  }, [])

  // 计时器
  useEffect(() => {
    if (panelState === 'speaking') {
      timerRef.current = window.setInterval(() => setSpeakingDuration((p) => p + 0.1), 100)
    } else {
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [panelState])

  const resetPanel = useCallback(() => {
    setPanelState('idle')
    setPartialText('')
    setSpeakingDuration(0)
  }, [])

  // ── 预连接 WebSocket + 预获取麦克风权限 ──
  const micWarmedRef = useRef(false)
  useEffect(() => {
    if (micWarmedRef.current) return
    // 悄悄预热：获取一次麦克风权限，后续录音无需等待权限弹窗
    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      stream.getTracks().forEach((t) => t.stop())  // 立即释放
      micWarmedRef.current = true
    }).catch(() => {})
  }, [])

  // ── 按住开始 ──
  const handlePressStart = useCallback(async (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault()
    if (disabled || panelState !== 'idle') return
    // 立即显示视觉反馈（UI 零延迟）
    setPanelState('speaking')
    pendingResultRef.current = false
    sttWs.connect()
    try {
      await recorder.startRecording()
    } catch {
      // 录音失败则回退状态
      resetPanel()
    }
  }, [disabled, panelState, recorder, sttWs, resetPanel])

  // ── 松手停止 ──
  const handlePressEnd = useCallback(async (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault()
    if (panelState !== 'speaking') return
    setPanelState('processing')

    const blob = await recorder.stopRecording()
    sttWs.sendFlush()
    sttWs.disconnect()

    // 等 500ms 给 WebSocket final 一个机会
    await new Promise((r) => setTimeout(r, 500))

    if (pendingResultRef.current) {
      setPanelState('idle')
      return
    }

    // 兜底：HTTP 批量转录
    if (blob && blob.size > 0) {
      try {
        const text = await transcribeAudio(blob)
        if (text) onResult(text)
        else message.warning('未检测到语音')
      } catch { message.error('语音识别失败') }
    } else {
      message.warning('未检测到语音')
    }
    resetPanel()
  }, [panelState, recorder, sttWs, onResult, message, resetPanel])

  // ── 空格键支持 ──
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === ' ' && !e.repeat && panelState === 'idle' && !disabled) {
        e.preventDefault()
        handlePressStart(e as unknown as React.MouseEvent)
      }
    }
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.key === ' ' && panelState === 'speaking') {
        e.preventDefault()
        handlePressEnd(e as unknown as React.MouseEvent)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
    }
  }, [panelState, disabled, handlePressStart, handlePressEnd])

  const handleDeviceChange = useCallback((value: string) => setSelectedDevice(value), [])
  const hasDevices = devices.length > 1
  const isActive = panelState !== 'idle'

  // ── 渲染 ──
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {/* 麦克风设备选择器 */}
      {hasDevices && !isActive && (
        <Select
          size="small"
          value={selectedDevice}
          onChange={handleDeviceChange}
          onClick={() => getAudioDevices().then(setDevices).catch(() => {})}
          style={{ minWidth: 120, maxWidth: 190 }}
          options={devices.map((d) => ({
            value: d.deviceId,
            label: d.label.length > 22 ? d.label.slice(0, 22) + '...' : d.label,
          }))}
          dropdownMatchSelectWidth={false}
        />
      )}

      {panelState === 'idle' ? (
        <Button
          type="default"
          shape="circle"
          size="large"
          icon={<AudioOutlined />}
          disabled={disabled}
          onMouseDown={handlePressStart}
          onTouchStart={handlePressStart}
          onMouseUp={handlePressEnd}
          onTouchEnd={handlePressEnd}
          onMouseLeave={handlePressEnd}
          title="按住说话（或按空格键）"
          style={{ userSelect: 'none' }}
        />
      ) : (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '8px 14px',
            borderRadius: 20,
            background: '#fff1f0',
            border: '1px solid #ff4d4f',
            transition: 'all 0.2s',
          }}
          onMouseUp={handlePressEnd}
          onTouchEnd={handlePressEnd}
          onMouseLeave={handlePressEnd}
        >
          {panelState === 'processing' ? (
            <LoadingOutlined style={{ fontSize: 20, color: '#ff4d4f' }} />
          ) : (
            <div
              style={{
                width: 20,
                height: 20,
                borderRadius: '50%',
                background: '#ff4d4f',
                animation: 'pulse 1s infinite',
                opacity: Math.max(0.5, recorder.audioLevel * 2),
              }}
            />
          )}

          <div style={{ flex: 1, minWidth: 60 }}>
            {partialText ? (
              <Text style={{ fontSize: 14, color: '#999', fontStyle: 'italic', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', display: 'block', maxWidth: 240 }}>
                {partialText}
              </Text>
            ) : (
              <Text type="secondary" style={{ fontSize: 14 }}>
                {panelState === 'processing' ? '识别中...' : '正在聆听...'}
              </Text>
            )}
          </div>

          {panelState === 'speaking' && (
            <Tag color="red" style={{ margin: 0 }}>{speakingDuration.toFixed(1)}s</Tag>
          )}

          <CloseOutlined
            style={{ color: '#999', cursor: 'pointer', fontSize: 12 }}
            onClick={(e) => {
              e.stopPropagation()
              recorder.stopRecording()
              sttWs.disconnect()
              resetPanel()
            }}
          />
        </div>
      )}

      {!isActive && !disabled && (
        <Text type="secondary" style={{ fontSize: 11 }}>按住说话 / 空格键</Text>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { transform: scale(1); opacity: 0.8; }
          50% { transform: scale(1.25); opacity: 1; }
        }
      `}</style>
    </div>
  )
}

export default VoiceInputPanel
