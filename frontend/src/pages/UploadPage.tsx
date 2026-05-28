import React, { useState, useEffect, useCallback } from 'react'
import {
  Upload, Tag, Typography, App, List, Button, Popconfirm,
  Empty, Spin,
} from 'antd'
import {
  InboxOutlined, FileTextOutlined,
  DeleteOutlined, CheckCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import type { UploadProps } from 'antd'
import * as uploadApi from '@/api/upload'
import { useAppStore } from '@/stores/appStore'
import type { UploadResponse, UploadRecord } from '@/types'

const { Dragger } = Upload
const { Text, Paragraph } = Typography

function formatTime(iso: string) {
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

const UploadPage: React.FC = () => {
  const {
    resumeText, activeResumeId, uploads,
    setResumeText, setActiveResume, setUploads,
    removeUpload,
  } = useAppStore()

  const [resumeResult, setResumeResult] = useState<UploadResponse | null>(null)
  const [uploading, setUploading] = useState(false)
  const [filesLoading, setFilesLoading] = useState(false)
  const { message } = App.useApp()

  const refreshFileList = useCallback(async () => {
    setFilesLoading(true)
    try {
      const res = await uploadApi.listUploads('resume')
      setUploads(res.uploads)
    } catch {
      // offline fallback
    } finally {
      setFilesLoading(false)
    }
  }, [setUploads])

  useEffect(() => {
    refreshFileList()
  }, [refreshFileList])

  const handleActivate = async (record: UploadRecord) => {
    let fullRecord = record
    if (record.text.length < 50) {
      try {
        fullRecord = await uploadApi.getUpload(record.id)
      } catch { /* use cached */ }
    }
    setActiveResume(fullRecord)
    message.success(`已激活简历: ${record.filename}`)
  }

  const handleDelete = async (id: string) => {
    try {
      await uploadApi.deleteUpload(id)
    } catch { /* offline */ }
    removeUpload(id)
    message.success('已删除')
  }

  const resumeProps: UploadProps = {
    name: 'file', multiple: false,
    accept: '.pdf,.docx,.doc,.txt',
    beforeUpload: (file) => {
      if (file.size > 5 * 1024 * 1024) { message.error('文件大小不能超过 5MB'); return Upload.LIST_IGNORE }
      return true
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      setUploading(true)
      try {
        const result = await uploadApi.uploadResume(file as File)
        setResumeResult(result)
        setResumeText(result.text)
        await refreshFileList()
        message.success('简历解析成功')
        onSuccess?.(result)
      } catch (err) {
        message.error((err as Error).message || '上传失败')
        onError?.(err as Error)
      } finally { setUploading(false) }
    },
    showUploadList: false,
  }

  const resumes = uploads.filter((u) => u.type === 'resume')

  return (
    <div>
      <Typography.Title level={4}>简历上传与管理</Typography.Title>

      <div style={{ marginBottom: 24 }}>
        <Dragger {...resumeProps} disabled={uploading}>
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">点击或拖拽简历文件到此区域</p>
          <p className="ant-upload-hint">支持 PDF / DOCX / DOC / TXT 格式，最大 5MB</p>
        </Dragger>
        {resumeResult && (
          <div style={{ marginTop: 16 }}>
            <Text strong>解析结果 — {resumeResult.filename}</Text>
            <Paragraph
              style={{ marginTop: 8, padding: 12, background: '#fafafa', borderRadius: 6, whiteSpace: 'pre-wrap', maxHeight: 400, overflow: 'auto' }}
              copyable
            >
              {resumeResult.text}
            </Paragraph>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <Text strong>已上传的简历 ({resumes.length})</Text>
        <Button size="small" icon={<ReloadOutlined />} onClick={refreshFileList} loading={filesLoading}>刷新</Button>
      </div>

      <Spin spinning={filesLoading}>
        {resumes.length === 0 ? (
          <Empty description="还没有上传过简历" />
        ) : (
          <>
            {activeResumeId && (
              <div style={{ marginBottom: 12, padding: '8px 12px', background: '#e6f4ff', borderRadius: 6, border: '1px solid #91caff' }}>
                <Text type="secondary" style={{ fontSize: 12, marginRight: 8 }}>当前简历：</Text>
                <Tag color="blue" closable onClose={() => setActiveResume(null)}>
                  {resumes.find((u) => u.id === activeResumeId)?.filename || '未知'}
                </Tag>
              </div>
            )}
            <List
              dataSource={resumes}
              renderItem={(item) => {
                const isActive = activeResumeId === item.id
                return (
                  <List.Item
                    style={{
                      padding: '12px 16px',
                      background: isActive ? '#f6ffed' : '#fff',
                      borderRadius: 6, marginBottom: 8,
                      border: isActive ? '1px solid #b7eb8f' : '1px solid #f0f0f0',
                    }}
                    actions={[
                      isActive ? (
                        <Tag color="success" icon={<CheckCircleOutlined />} style={{ marginRight: 0 }}>当前使用</Tag>
                      ) : (
                        <Button size="small" type="link" onClick={() => handleActivate(item)}>使用此简历</Button>
                      ),
                      <Popconfirm
                        key="delete" title="确定删除此简历？"
                        onConfirm={() => handleDelete(item.id)}
                        okText="删除" cancelText="取消"
                      >
                        <Button size="small" danger type="text" icon={<DeleteOutlined />} />
                      </Popconfirm>,
                    ]}
                  >
                    <List.Item.Meta
                      avatar={<Tag color="#1677ff" style={{ marginRight: 0, fontSize: 14 }}><FileTextOutlined /> 简历</Tag>}
                      title={<Text strong>{item.filename}</Text>}
                      description={
                        <div>
                          <Text type="secondary" style={{ fontSize: 12 }} ellipsis>{item.preview}</Text>
                          <div style={{ marginTop: 4 }}>
                            <Text type="secondary" style={{ fontSize: 11 }}>{formatTime(item.created_at)}</Text>
                          </div>
                        </div>
                      }
                    />
                  </List.Item>
                )
              }}
            />
          </>
        )}
      </Spin>
    </div>
  )
}

export default UploadPage
