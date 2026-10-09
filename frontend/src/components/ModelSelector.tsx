import React from 'react'
import { Select, Switch, Space, Typography, Tooltip, Tag } from 'antd'
import { PictureOutlined } from '@ant-design/icons'
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
          // 🧠 支持思考模式，🖼 支持图片输入（截图答题需要）
          label: `${m.name}${m.supports_thinking ? ' 🧠' : ''}${m.supports_vision ? ' 🖼' : ''}`,
          title: m.description || m.id,
        }))}
        optionRender={(option) => {
          const m = models.find((x) => x.id === option.value)
          if (!m) return option.label
          return (
            <Space direction="vertical" size={0} style={{ maxWidth: 380 }}>
              <Space size={4}>
                <Text strong style={{ fontSize: 13 }}>{m.name}</Text>
                <Text type="secondary" style={{ fontSize: 11 }}>{m.id}</Text>
                {m.supports_thinking && <Tag color="blue" style={{ marginInlineEnd: 0 }}>思考</Tag>}
                {m.supports_vision && (
                  <Tag color="green" style={{ marginInlineEnd: 0 }}>
                    <PictureOutlined /> 图片
                  </Tag>
                )}
              </Space>
              {m.description && (
                <Text type="secondary" style={{ fontSize: 11 }}>{m.description}</Text>
              )}
            </Space>
          )
        }}
      />

      {/* 截图答题需要模型支持图片输入，这里给出明确提示 */}
      {currentModel && !currentModel.supports_vision && (
        <Tooltip title="截图答题需要模型支持图片输入，当前模型为纯文本模型，点击截图按钮会提示不支持">
          <Tag color="warning" style={{ marginInlineEnd: 0 }}>
            <PictureOutlined /> 不支持图片
          </Tag>
        </Tooltip>
      )}

      {currentModel?.supports_thinking && (
        <>
          <Space size={4}>
            <Tooltip title="思考强度：低=更快更省 token，高=默认，最大=最充分的推理">
              <Text type="secondary" style={{ fontSize: 12 }}>
                思考模式
              </Text>
            </Tooltip>
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
                { value: 'low', label: '低' },
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