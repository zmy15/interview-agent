import React, { useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'

interface StreamingTextProps {
  text: string
  highlightCode: boolean
}

const StreamingText: React.FC<StreamingTextProps> = ({ text, highlightCode }) => {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [text])

  return (
    <div ref={containerRef}>
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
