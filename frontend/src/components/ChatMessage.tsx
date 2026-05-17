import React from 'react'
import { Collapse, Typography, theme } from 'antd'
import { UserOutlined, RobotOutlined } from '@ant-design/icons'
import StreamingText from './StreamingText'
import type { Message } from '@/types'

const { Text } = Typography

interface ChatMessageProps {
  message: Message
  highlightCode: boolean
  isStreaming?: boolean
}

const ChatMessage: React.FC<ChatMessageProps> = ({ message, highlightCode, isStreaming }) => {
  const { token } = theme.useToken()
  const isUser = message.role === 'user'
  const isAssistant = message.role === 'assistant'

  return (
    <div
      style={{
        display: 'flex',
        gap: 12,
        padding: '12px 0',
        flexDirection: isUser ? 'row-reverse' : 'row',
      }}
    >
      {/* 头像 */}
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: isUser ? token.colorPrimary : token.colorSuccess,
          color: '#fff',
          flexShrink: 0,
        }}
      >
        {isUser ? <UserOutlined /> : <RobotOutlined />}
      </div>

      {/* 消息体 */}
      <div
        style={{
          maxWidth: '75%',
          padding: '10px 16px',
          borderRadius: 12,
          background: isUser ? token.colorPrimaryBg : token.colorBgContainer,
          border: `1px solid ${token.colorBorderSecondary}`,
        }}
      >
        {isUser ? (
          <Text style={{ whiteSpace: 'pre-wrap' }}>{message.content}</Text>
        ) : (
          <>
            {/* 思维链折叠 */}
            {message.reasoning && (
              <Collapse
                size="small"
                ghost
                items={[
                  {
                    key: 'reasoning',
                    label: (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        🤔 思考过程
                      </Text>
                    ),
                    children: (
                      <Text
                        type="secondary"
                        style={{
                          fontSize: 12,
                          whiteSpace: 'pre-wrap',
                          fontStyle: 'italic',
                        }}
                      >
                        {message.reasoning}
                      </Text>
                    ),
                  },
                ]}
                style={{ marginBottom: 8 }}
              />
            )}
            <StreamingText text={message.content} highlightCode={highlightCode} />
            {isStreaming && (
              <span
                style={{
                  display: 'inline-block',
                  width: 8,
                  height: 16,
                  background: token.colorPrimary,
                  marginLeft: 2,
                  animation: 'blink 1s infinite',
                }}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default ChatMessage
