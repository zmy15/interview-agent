import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'

interface StreamingTextProps {
  text: string
  highlightCode: boolean
}

const StreamingText: React.FC<StreamingTextProps> = ({ text, highlightCode }) => {
  // 注意：滚动由父组件 ChatPage 统一管理，此处不做 scrollIntoView，
  // 避免流式输出时多个 smooth 滚动动画竞争导致界面抖动。
  return (
    <div>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={
          highlightCode
            ? {
                code({ className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className || '')
                  const codeStr = String(children).replace(/\n$/, '')
                  // eslint-disable-next-line @typescript-eslint/no-unused-vars
                  const { ref, ...rest } = props as Record<string, unknown>

                  if (match) {
                    return (
                      <SyntaxHighlighter
                        style={oneDark}
                        language={match[1]}
                        PreTag="div"
                        showLineNumbers
                      >
                        {codeStr}
                      </SyntaxHighlighter>
                    )
                  }
                  return (
                    <code className={className} {...rest}>
                      {children}
                    </code>
                  )
                },
              }
            : {}
        }
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}

export default StreamingText
