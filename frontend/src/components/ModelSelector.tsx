import React from 'react'
import { Select, Switch, Space, Typography } from 'antd'
import { useModels } from '@/hooks/useModels'
import { useChatStore } from '@/stores/chatStore'

const { Text } = Typography

const ModelSelector: React.FC = () => {
  const { models, loading } = useModels()
  const {
    selectedModel,
    thinkingEnabled,
    reasoningEffort,
    setModel,
    setThinking,
    setReasoningEffort,
  } = useChatStore()

  const currentModel = models.find((m) => m.id === selectedModel)

  return (
    <Space size="small" wrap>
      <Select
        value={selectedModel || undefined}
        onChange={(val) => setModel(val)}
        placeholder="选择模型"
        loading={loading}
        style={{ minWidth: 200 }}
        options={models.map((m) => ({
          value: m.id,
          label: `${m.name}${m.supports_thinking ? ' 🧠' : ''}`,
        }))}
      />
      {currentModel?.supports_thinking && (
        <>
          <Space size={4}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              思考模式
            </Text>
            <Switch
              size="small"
              checked={thinkingEnabled}
              onChange={setThinking}
            />
          </Space>
          {thinkingEnabled && (
            <Select
              size="small"
              value={reasoningEffort}
              onChange={(val) => setReasoningEffort(val)}
              style={{ width: 80 }}
              options={[
                { value: 'high', label: '高' },
                { value: 'max', label: '最大' },
              ]}
            />
          )}
        </>
      )}
    </Space>
  )
}

export default ModelSelector
