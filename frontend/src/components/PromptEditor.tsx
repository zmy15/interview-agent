import React, { useState, useEffect } from 'react'
import { Modal, Tabs, Input, Button, Space, Popconfirm, Typography } from 'antd'
import { useChatStore } from '@/stores/chatStore'

const { TextArea } = Input
const { Text } = Typography

interface PromptEditorProps {
  open: boolean
  onClose: () => void
}

// 默认占位文本，表示使用服务端默认 Prompt
const DEFAULT_PLACEHOLDER = '（留空则使用服务端默认模板）'

const PromptEditor: React.FC<PromptEditorProps> = ({ open, onClose }) => {
  const { promptOverrides, setPromptOverride, resetPromptOverride } = useChatStore()
  const [activeTab, setActiveTab] = useState<'interviewer' | 'candidate'>('interviewer')
  const [draft, setDraft] = useState<Record<'interviewer' | 'candidate', string>>({
    interviewer: '',
    candidate: '',
  })

  useEffect(() => {
    if (open) {
      setDraft({
        interviewer: promptOverrides.interviewer || '',
        candidate: promptOverrides.candidate || '',
      })
    }
  }, [open, promptOverrides])

  const handleSave = () => {
    if (draft.interviewer) {
      setPromptOverride('interviewer', draft.interviewer)
    } else {
      resetPromptOverride('interviewer')
    }
    if (draft.candidate) {
      setPromptOverride('candidate', draft.candidate)
    } else {
      resetPromptOverride('candidate')
    }
    onClose()
  }

  const handleReset = (mode: 'interviewer' | 'candidate') => {
    setDraft((prev) => ({ ...prev, [mode]: '' }))
    resetPromptOverride(mode)
  }

  return (
    <Modal
      title="Prompt 模板微调"
      open={open}
      onCancel={onClose}
      width={700}
      footer={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={handleSave}>
            保存
          </Button>
        </Space>
      }
    >
      <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
        可用占位符：{'{jd}'}（岗位描述）、{'{resume}'}（简历）、{'{code}'}（代码）。留空则使用服务端默认模板。
      </Text>
      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as 'interviewer' | 'candidate')}
        items={[
          {
            key: 'interviewer',
            label: 'AI 面试官',
            children: (
              <div>
                <TextArea
                  value={draft.interviewer}
                  onChange={(e) =>
                    setDraft((prev) => ({ ...prev, interviewer: e.target.value }))
                  }
                  placeholder={DEFAULT_PLACEHOLDER}
                  rows={15}
                  style={{ fontFamily: 'monospace', fontSize: 13 }}
                />
                <div style={{ marginTop: 8 }}>
                  <Popconfirm
                    title="确定恢复为默认模板？"
                    onConfirm={() => handleReset('interviewer')}
                    okText="确定"
                    cancelText="取消"
                  >
                    <Button size="small" danger>
                      恢复默认
                    </Button>
                  </Popconfirm>
                </div>
              </div>
            ),
          },
          {
            key: 'candidate',
            label: '我是求职者',
            children: (
              <div>
                <TextArea
                  value={draft.candidate}
                  onChange={(e) =>
                    setDraft((prev) => ({ ...prev, candidate: e.target.value }))
                  }
                  placeholder={DEFAULT_PLACEHOLDER}
                  rows={15}
                  style={{ fontFamily: 'monospace', fontSize: 13 }}
                />
                <div style={{ marginTop: 8 }}>
                  <Popconfirm
                    title="确定恢复为默认模板？"
                    onConfirm={() => handleReset('candidate')}
                    okText="确定"
                    cancelText="取消"
                  >
                    <Button size="small" danger>
                      恢复默认
                    </Button>
                  </Popconfirm>
                </div>
              </div>
            ),
          },
        ]}
      />
    </Modal>
  )
}

export default PromptEditor
