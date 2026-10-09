/**
 * SystemAudioSettings — 「界面与窗口设置」里的系统音频监听开关
 *
 * 交互设计：
 *   这里只放**配置**（开关、设备、自动提问），不放实时字幕。
 *   打开开关后，只要处于 AI 对话界面就会自动开始监听，
 *   识别出的文字直接进入当前模式的对话（面试官 / 求职者）。
 *
 * 与截图答题的区别：截图是一次性动作，监听是持续状态，
 * 所以做成设置里的常驻开关而不是工具栏上的按钮。
 */

import React, { useEffect, useState } from 'react'
import { Space, Switch, Typography, Select, Tooltip, Tag, Divider } from 'antd'
import { AudioOutlined } from '@ant-design/icons'
import { useAppStore } from '@/stores/appStore'
import { systemAudioApi, type SystemAudioDevice } from '@/api/systemAudio'

const { Text } = Typography

interface SystemAudioSettingsProps {
  /** 当前是否真的在监听（由 ChatPage 的监听逻辑回传） */
  listening?: boolean
  /** STT 是否已连接 */
  sttConnected?: boolean
  /** 不可用时的原因 */
  unavailableReason?: string | null
}

const SystemAudioSettings: React.FC<SystemAudioSettingsProps> = ({
  listening,
  sttConnected,
  unavailableReason,
}) => {
  const {
    systemAudioEnabled,
    systemAudioDevice,
    systemAudioAutoAsk,
    setSystemAudioEnabled,
    setSystemAudioDevice,
    setSystemAudioAutoAsk,
  } = useAppStore()

  const [devices, setDevices] = useState<SystemAudioDevice[]>([])
  const [available, setAvailable] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 探测可用性与设备（每次展开设置时刷新，设备可能插拔）
  useEffect(() => {
    let cancelled = false
    systemAudioApi
      .info()
      .then((info) => {
        if (cancelled) return
        setAvailable(info.available)
        setError(info.error ?? null)
        setDevices(info.devices)
      })
      .catch((err) => {
        if (cancelled) return
        setAvailable(false)
        setError((err as Error).message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const disabled = !available
  const reason = unavailableReason || error

  return (
    <>
      <Divider style={{ margin: '8px 0' }} />

      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
        <Tooltip
          title={
            disabled
              ? reason || '系统音频捕获不可用'
              : '开启后，只要在 AI 对话界面就会自动监听电脑播放的声音，' +
                '识别成文字并发给当前模式的 AI'
          }
        >
          <Text style={{ fontSize: 13, opacity: disabled ? 0.45 : 1 }}>
            <AudioOutlined /> 监听系统音频
          </Text>
        </Tooltip>
        <Switch
          size="small"
          checked={systemAudioEnabled}
          disabled={disabled}
          onChange={setSystemAudioEnabled}
        />
      </Space>

      {/* 不可用原因 */}
      {disabled && reason && (
        <Text type="secondary" style={{ fontSize: 11 }}>
          {reason}
        </Text>
      )}

      {systemAudioEnabled && !disabled && (
        <>
          {/* 运行状态 */}
          <Space size={4} wrap>
            <Tag
              color={listening ? (sttConnected ? 'green' : 'orange') : 'default'}
              style={{ marginInlineEnd: 0, fontSize: 11 }}
            >
              {listening
                ? sttConnected
                  ? '监听中'
                  : '监听中（语音识别未连接）'
                : '等待进入对话页'}
            </Tag>
          </Space>

          {/* 捕获设备 */}
          <Space size={4} style={{ width: '100%' }}>
            <Text style={{ fontSize: 12 }}>设备</Text>
            <Select
              size="small"
              value={systemAudioDevice || undefined}
              onChange={(v) => setSystemAudioDevice(v || '')}
              style={{ flex: 1, minWidth: 130 }}
              placeholder="系统默认"
              options={[
                { value: '', label: '系统默认播放设备' },
                ...devices.map((d) => ({
                  value: d.id,
                  label: `${d.name}${d.is_default ? '（默认）' : ''}`,
                })),
              ]}
            />
          </Space>

          {/* 自动提问 */}
          <Space style={{ width: '100%', justifyContent: 'space-between' }}>
            <Tooltip title="识别出完整句子后，自动把它作为提问发给当前模式的 AI">
              <Text style={{ fontSize: 12 }}>自动让 AI 回答</Text>
            </Tooltip>
            <Switch size="small" checked={systemAudioAutoAsk} onChange={setSystemAudioAutoAsk} />
          </Space>

          <Text type="secondary" style={{ fontSize: 11 }}>
            {systemAudioAutoAsk
              ? '识别到的问题会自动发送，AI 的回答会出现在对话里'
              : '仅把识别到的文字填入输入框，由你决定是否发送'}
          </Text>
        </>
      )}
    </>
  )
}

export default SystemAudioSettings