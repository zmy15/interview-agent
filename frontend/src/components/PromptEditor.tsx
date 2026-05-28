import React, { useState, useEffect } from 'react'
import { Modal, Input, Button, Space, Typography } from 'antd'
import { useChatStore } from '@/stores/chatStore'

const { TextArea } = Input
const { Text } = Typography

interface PromptEditorProps {
  open: boolean
  onClose: () => void
}

const PromptEditor: React.FC<PromptEditorProps> = ({ open, onClose }) => {
  const { promptOverrides, setPromptOverride, resetPromptOverride } = useChatStore()
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
    if (draft.interviewer.trim()) {
      setPromptOverride('interviewer', draft.interviewer)
    } else {
      resetPromptOverride('interviewer')
    }
    if (draft.candidate.trim()) {
      setPromptOverride('candidate', draft.candidate)
    } else {
      resetPromptOverride('candidate')
    }
    onClose()
  }

  return (
    <Modal
      title="补充说明"
      open={open}
      onCancel={onClose}
      width={650}
      footer={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={handleSave}>
            保存
          </Button>
        </Space>
      }
    >
      <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
        此处内容会追加到 AI 的系统提示末尾。可用于补充面试侧重方向、特殊要求等额外指引。
      </Text>

      <div style={{ marginBottom: 16 }}>
        <Text strong style={{ display: 'block', marginBottom: 4 }}>
          🎯 AI 面试官模式（AI 扮演面试官时生效）
        </Text>
        <TextArea
          value={draft.candidate}
          onChange={(e) => setDraft((prev) => ({ ...prev, candidate: e.target.value }))}
          placeholder="例如：请侧重考察候选人的系统设计能力；多问一些分布式相关的问题..."
          rows={6}
          style={{ fontFamily: 'monospace', fontSize: 13 }}
        />
      </div>

      <div>
        <Text strong style={{ display: 'block', marginBottom: 4 }}>
          🧑 AI 求职者模式（AI 扮演求职者时生效）
        </Text>
        <TextArea
          value={draft.interviewer}
          onChange={(e) => setDraft((prev) => ({ ...prev, interviewer: e.target.value }))}
          placeholder="例如：请用 STAR 法则回答项目经历；回答控制在 300 字以内..."
          rows={6}
          style={{ fontFamily: 'monospace', fontSize: 13 }}
        />
      </div>
    </Modal>
  )
}

export default PromptEditor
