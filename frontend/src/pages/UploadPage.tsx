import React, { useState } from 'react'
import { Tabs, Upload, Button, Typography, App } from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd'
import * as uploadApi from '@/api/upload'
import type { UploadResponse } from '@/types'

const { Dragger } = Upload
const { Text, Paragraph } = Typography

const UploadPage: React.FC = () => {
  const [resumeResult, setResumeResult] = useState<UploadResponse | null>(null)
  const [codeResult, setCodeResult] = useState<UploadResponse | null>(null)
  const { message } = App.useApp()
  const [uploading, setUploading] = useState(false)

  const resumeProps: UploadProps = {
    name: 'file',
    multiple: false,
    accept: '.pdf,.docx,.txt',
    beforeUpload: (file) => {
      if (file.size > 5 * 1024 * 1024) {
        message.error('文件大小不能超过 5MB')
        return Upload.LIST_IGNORE
      }
      return true
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      setUploading(true)
      try {
        const result = await uploadApi.uploadResume(file as File)
        setResumeResult(result)
        message.success('简历解析成功')
        onSuccess?.(result)
      } catch (err) {
        message.error((err as Error).message || '上传失败')
        onError?.(err as Error)
      } finally {
        setUploading(false)
      }
    },
    showUploadList: false,
  }

  const codeProps: UploadProps = {
    name: 'file',
    multiple: false,
    accept: '.py,.js,.ts,.java,.go,.rs,.cpp,.c,.h,.cs,.rb,.php,.swift,.kt,.scala,.sh,.bat,.ps1,.sql,.html,.css,.vue,.jsx,.tsx,.yaml,.yml,.json,.xml,.toml,.ini,.cfg,.md',
    beforeUpload: (file) => {
      if (file.size > 2 * 1024 * 1024) {
        message.error('文件大小不能超过 2MB')
        return Upload.LIST_IGNORE
      }
      return true
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      setUploading(true)
      try {
        const result = await uploadApi.uploadCode(file as File)
        setCodeResult(result)
        message.success('代码上传成功')
        onSuccess?.(result)
      } catch (err) {
        message.error((err as Error).message || '上传失败')
        onError?.(err as Error)
      } finally {
        setUploading(false)
      }
    },
    showUploadList: false,
  }

  return (
    <div>
      <Typography.Title level={4}>文件上传</Typography.Title>
      <Tabs
        items={[
          {
            key: 'resume',
            label: '📄 简历上传',
            children: (
              <div>
                <Dragger {...resumeProps} disabled={uploading}>
                  <p className="ant-upload-drag-icon">
                    <InboxOutlined />
                  </p>
                  <p className="ant-upload-text">点击或拖拽简历文件到此区域</p>
                  <p className="ant-upload-hint">
                    支持 PDF / DOCX / TXT 格式，最大 5MB
                  </p>
                </Dragger>
                {resumeResult && (
                  <div style={{ marginTop: 16 }}>
                    <Text strong>
                      解析结果 — {resumeResult.filename}
                    </Text>
                    <Paragraph
                      style={{
                        marginTop: 8,
                        padding: 12,
                        background: '#fafafa',
                        borderRadius: 6,
                        whiteSpace: 'pre-wrap',
                        maxHeight: 400,
                        overflow: 'auto',
                      }}
                      copyable
                    >
                      {resumeResult.text}
                    </Paragraph>
                  </div>
                )}
              </div>
            ),
          },
          {
            key: 'code',
            label: '💻 代码上传',
            children: (
              <div>
                <Dragger {...codeProps} disabled={uploading}>
                  <p className="ant-upload-drag-icon">
                    <InboxOutlined />
                  </p>
                  <p className="ant-upload-text">点击或拖拽代码文件到此区域</p>
                  <p className="ant-upload-hint">
                    支持常见编程语言文件，最大 2MB
                  </p>
                </Dragger>
                {codeResult && (
                  <div style={{ marginTop: 16 }}>
                    <Text strong>
                      代码内容 — {codeResult.filename}
                    </Text>
                    <Paragraph
                      style={{
                        marginTop: 8,
                        padding: 12,
                        background: '#1e1e1e',
                        color: '#d4d4d4',
                        borderRadius: 6,
                        whiteSpace: 'pre-wrap',
                        maxHeight: 400,
                        overflow: 'auto',
                        fontFamily: 'monospace',
                      }}
                      copyable
                    >
                      {codeResult.text}
                    </Paragraph>
                  </div>
                )}
              </div>
            ),
          },
        ]}
      />
    </div>
  )
}

export default UploadPage
