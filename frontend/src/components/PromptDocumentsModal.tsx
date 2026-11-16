import React, { useState } from 'react'
import {
  App,
  Button,
  Empty,
  Input,
  List,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Tag,
  Typography,
  Upload,
} from 'antd'
import {
  DeleteOutlined,
  EditOutlined,
  FileTextOutlined,
  InboxOutlined,
} from '@ant-design/icons'
import type { UploadProps } from 'antd'
import { MAX_PROMPT_DOCS, useAppStore } from '@/stores/appStore'
import { uploadPromptDocument } from '@/api/upload'
import type { PromptDocument } from '@/types'

const { Text, Paragraph } = Typography
const { Dragger } = Upload
const { TextArea } = Input

/** 与后端 PROMPT_DOC_EXTENSIONS 保持一致 */
const ACCEPT =
  '.txt,.md,.markdown,.text,.rst,.csv,.tsv,.json,.yaml,.yml,.xml,.log,.ini,.pdf,.docx'
const MAX_FILE_SIZE = 5 * 1024 * 1024
/** 前端提示用的合计上限（后端默认 PROMPT_DOC_MAX_TOTAL_CHARS=200000） */
const HINT_TOTAL_CHARS = 200000

interface PromptDocumentsModalProps {
  open: boolean
  onClose: () => void
}

/**
 * 提示词资料文档管理。
 *
 * 上传的文档不会进入消息列表，也不会改写 prompts/*.txt：
 * 后端把它拼成一条独立消息，插在**系统提示词之后、对话之前**
 * （见 routers/chat.py 的 Phase 1.5）。它整场对话不变，
 * 所以依旧属于稳定前缀，服务端前缀缓存照样命中。
 */
const PromptDocumentsModal: React.FC<PromptDocumentsModalProps> = ({ open, onClose }) => {
  const {
    promptDocs,
    addPromptDoc,
    removePromptDoc,
    togglePromptDoc,
    updatePromptDocText,
    clearPromptDocs,
  } = useAppStore()
  const { message } = App.useApp()

  const [uploading, setUploading] = useState(0)
  const [editing, setEditing] = useState<PromptDocument | null>(null)
  const [draft, setDraft] = useState('')

  const enabledChars = promptDocs
    .filter((doc) => doc.enabled)
    .reduce((sum, doc) => sum + doc.text.length, 0)

  const full = promptDocs.length >= MAX_PROMPT_DOCS

  /** 关闭列表弹窗时一并丢掉未保存的草稿，避免下次打开看到上一次的内容 */
  const handleClose = () => {
    setEditing(null)
    setDraft('')
    onClose()
  }

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: true,
    accept: ACCEPT,
    showUploadList: false,
    disabled: full,
    beforeUpload: (file) => {
      if (file.size > MAX_FILE_SIZE) {
        message.error(`${file.name} 超过 5MB 限制`)
        return Upload.LIST_IGNORE
      }
      return true
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      setUploading((count) => count + 1)
      try {
        const result = await uploadPromptDocument(file as File)
        addPromptDoc({
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          name: result.filename,
          text: result.text,
          enabled: true,
          addedAt: Date.now(),
        })
        message.success(`${result.filename} 已附加（${result.text.length} 字）`)
        onSuccess?.(result)
      } catch (err) {
        message.error((err as Error).message || '上传失败')
        onError?.(err as Error)
      } finally {
        setUploading((count) => count - 1)
      }
    },
  }

  const openEditor = (doc: PromptDocument) => {
    setEditing(doc)
    setDraft(doc.text)
  }

  const saveEditor = () => {
    if (!editing) return
    updatePromptDocText(editing.id, draft)
    setEditing(null)
    message.success('已保存修改')
  }

  return (
    <>
      <Modal
        title="提示词资料（附加文档）"
        open={open}
        onCancel={handleClose}
        width={760}
        footer={
          <Space>
            {promptDocs.length > 0 && (
              <Popconfirm
                title="清空全部附加文档？"
                okText="清空"
                cancelText="取消"
                okButtonProps={{ danger: true }}
                onConfirm={() => {
                  clearPromptDocs()
                  message.success('已清空')
                }}
              >
                <Button danger>清空全部</Button>
              </Popconfirm>
            )}
            <Button type="primary" onClick={handleClose}>
              完成
            </Button>
          </Space>
        }
      >
        <Paragraph type="secondary" style={{ marginBottom: 12 }}>
          上传 txt / md 等文档（也可上传 pdf / docx），内容会作为一条独立消息
          <Text strong> 插在系统提示词之后、对话之前 </Text>
          ，整场对话里保持不变 —— 既不会挤掉历史问答，也不会破坏前缀缓存。
          文档只保存在本机浏览器，不会上传到知识库。
        </Paragraph>

        <Dragger {...uploadProps} style={{ marginBottom: 16 }}>
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">
            {uploading > 0 ? '正在解析…' : '点击或拖拽文件到此处上传'}
          </p>
          <p className="ant-upload-hint">
            支持 .txt / .md / .csv / .json / .yaml / .pdf / .docx 等，单文件不超过 5MB，
            最多 {MAX_PROMPT_DOCS} 份{full ? '（已满，请先删除）' : ''}
          </p>
        </Dragger>

        <List
          dataSource={promptDocs}
          locale={{
            emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有附加文档" />,
          }}
          renderItem={(doc) => (
            <List.Item
              actions={[
                <Switch
                  key="enabled"
                  size="small"
                  checked={doc.enabled}
                  onChange={() => togglePromptDoc(doc.id)}
                  checkedChildren="启用"
                  unCheckedChildren="停用"
                />,
                <Button
                  key="edit"
                  size="small"
                  type="text"
                  icon={<EditOutlined />}
                  onClick={() => openEditor(doc)}
                >
                  编辑
                </Button>,
                <Popconfirm
                  key="delete"
                  title={`删除 ${doc.name}？`}
                  okText="删除"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => removePromptDoc(doc.id)}
                >
                  <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                avatar={<FileTextOutlined style={{ fontSize: 18, color: doc.enabled ? undefined : '#bbb' }} />}
                title={
                  <Space size={6} wrap>
                    <Text delete={!doc.enabled}>{doc.name}</Text>
                    <Tag>{doc.text.length} 字</Tag>
                    {!doc.enabled && <Tag color="default">未附加</Tag>}
                  </Space>
                }
                description={
                  <Paragraph
                    type="secondary"
                    ellipsis={{ rows: 2 }}
                    style={{ marginBottom: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}
                  >
                    {doc.text}
                  </Paragraph>
                }
              />
            </List.Item>
          )}
        />

        <div style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            已启用 {promptDocs.filter((doc) => doc.enabled).length} 份 · 合计 {enabledChars} 字
            {enabledChars > HINT_TOTAL_CHARS && '（超过后端上限的部分不会附加）'}
          </Text>
        </div>
      </Modal>

      {/* 正文编辑：上传解析可能带进多余的空行/页眉，允许就地删改 */}
      <Modal
        title={`编辑：${editing?.name ?? ''}`}
        open={!!editing}
        onCancel={() => setEditing(null)}
        onOk={saveEditor}
        okText="保存"
        cancelText="取消"
        width={720}
      >
        <TextArea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={18}
          style={{ fontFamily: 'monospace', fontSize: 13 }}
        />
        <Text type="secondary" style={{ fontSize: 12 }}>
          当前 {draft.length} 字。修改会影响整场对话的稳定前缀，服务端缓存会在下一次请求时重建一次。
        </Text>
      </Modal>
    </>
  )
}

export default PromptDocumentsModal
