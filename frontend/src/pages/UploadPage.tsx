import React, { useState, useEffect, useCallback } from 'react'
import {
  Tabs, Upload, Tag, Typography, App, Tree, List, Button, Popconfirm,
  Empty, Space, Badge, Spin, Segmented,
} from 'antd'
import {
  InboxOutlined, FolderOpenOutlined, FileTextOutlined,
  CodeOutlined, ProjectOutlined, DeleteOutlined, CheckCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import type { UploadProps } from 'antd'
import type { DataNode } from 'antd/es/tree'
import * as uploadApi from '@/api/upload'
import { useAppStore } from '@/stores/appStore'
import type { UploadResponse, ProjectUploadResponse, ProjectStructure, UploadRecord } from '@/types'

const { Dragger } = Upload
const { Text, Paragraph } = Typography

/** 文件类型对应的图标和颜色 */
const TYPE_META: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  resume: { icon: <FileTextOutlined />, color: '#1677ff', label: '简历' },
  code: { icon: <CodeOutlined />, color: '#52c41a', label: '代码' },
  project: { icon: <ProjectOutlined />, color: '#fa8c16', label: '项目' },
}

/** 将 project structure 转为 Ant Design Tree 数据 */
function buildProjectTree(structure: ProjectStructure): DataNode[] {
  const categoryLabels: Record<keyof ProjectStructure, { label: string; color: string }> = {
    source: { label: '📝 源码', color: 'blue' },
    config: { label: '⚙️ 配置', color: 'orange' },
    document: { label: '📖 文档', color: 'green' },
    build: { label: '🔧 构建', color: 'purple' },
    test: { label: '🧪 测试', color: 'cyan' },
    other: { label: '📦 其他', color: 'default' },
  }
  const nodes: DataNode[] = []
  for (const [cat, files] of Object.entries(structure) as [keyof ProjectStructure, string[]][]) {
    if (files.length === 0) continue
    const { label, color } = categoryLabels[cat]
    nodes.push({
      title: <span><Tag color={color}>{label}</Tag><Text type="secondary">({files.length} 个文件)</Text></span>,
      key: cat, selectable: false,
      children: files.map((f) => ({
        title: <Text code style={{ fontSize: 12 }}>{f}</Text>,
        key: `${cat}/${f}`, isLeaf: true,
      })),
    })
  }
  return nodes
}

/** 格式化时间 */
function formatTime(iso: string) {
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

// ==================== 主组件 ====================

const UploadPage: React.FC = () => {
  const {
    resumeText, codeText, activeUploadId, uploads,
    setResumeText, setCodeText, setActiveUpload, setUploads,
    addUpload, removeUpload, setProjectMeta,
  } = useAppStore()

  const [resumeResult, setResumeResult] = useState<UploadResponse | null>(null)
  const [codeResult, setCodeResult] = useState<UploadResponse | null>(null)
  const [projectResult, setProjectResult] = useState<ProjectUploadResponse | null>(null)
  const [uploading, setUploading] = useState(false)
  const [filesLoading, setFilesLoading] = useState(false)
  const [managementFilter, setManagementFilter] = useState<string>('all')
  const { message } = App.useApp()

  // 加载服务端文件列表
  const refreshFileList = useCallback(async () => {
    setFilesLoading(true)
    try {
      const res = await uploadApi.listUploads()
      setUploads(res.uploads)
    } catch {
      // 离线时使用本地缓存
    } finally {
      setFilesLoading(false)
    }
  }, [setUploads])

  useEffect(() => {
    refreshFileList()
  }, [refreshFileList])

  // 激活文件（用于对话）
  const handleActivate = async (record: UploadRecord) => {
    // 如果本地文本不完整，从服务端获取
    if (record.text.length < 50) {
      try {
        const full = await uploadApi.getUpload(record.id)
        setActiveUpload(full)
        message.success(`已激活: ${record.filename}`)
        return
      } catch { /* 使用已有文本 */ }
    }
    setActiveUpload(record)
    message.success(`已激活: ${record.filename}`)
  }

  // 删除文件
  const handleDelete = async (id: string) => {
    try {
      await uploadApi.deleteUpload(id)
    } catch { /* 服务端不可用时只删本地 */ }
    removeUpload(id)
    message.success('已删除')
  }

  // ========== 上传回调 ==========

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
        // 从服务端刷新列表
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

  const codeProps: UploadProps = {
    name: 'file', multiple: false,
    accept: '.py,.js,.ts,.java,.go,.rs,.cpp,.c,.h,.cs,.rb,.php,.swift,.kt,.scala,.sh,.bat,.ps1,.sql,.html,.css,.vue,.jsx,.tsx,.yaml,.yml,.json,.xml,.toml,.ini,.cfg,.md',
    beforeUpload: (file) => {
      if (file.size > 2 * 1024 * 1024) { message.error('文件大小不能超过 2MB'); return Upload.LIST_IGNORE }
      return true
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      setUploading(true)
      try {
        const result = await uploadApi.uploadCode(file as File)
        setCodeResult(result)
        setCodeText(result.text)
        await refreshFileList()
        message.success('代码上传成功')
        onSuccess?.(result)
      } catch (err) {
        message.error((err as Error).message || '上传失败')
        onError?.(err as Error)
      } finally { setUploading(false) }
    },
    showUploadList: false,
  }

  const projectProps: UploadProps = {
    name: 'file', multiple: false,
    accept: '.zip,.tar.gz,.tgz,.tar.bz2,.tar,.7z',
    beforeUpload: (file) => {
      if (file.size > 50 * 1024 * 1024) { message.error('文件大小不能超过 50MB'); return Upload.LIST_IGNORE }
      return true
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      setUploading(true)
      try {
        const result = await uploadApi.uploadProject(file as File)
        setProjectResult(result)
        setCodeText(result.total_text)
        setProjectMeta(result.structure, result.tech_stack)
        await refreshFileList()
        message.success(`项目解析成功 — 共 ${result.file_count} 个文件`)
        onSuccess?.(result)
      } catch (err) {
        message.error((err as Error).message || '上传失败')
        onError?.(err as Error)
      } finally { setUploading(false) }
    },
    showUploadList: false,
  }

  // ========== 过滤后的文件列表 ==========

  const filteredUploads = managementFilter === 'all'
    ? uploads
    : uploads.filter((u) => u.type === managementFilter)

  return (
    <div>
      <Typography.Title level={4}>文件上传与管理</Typography.Title>
      <Tabs
        items={[
          // ===== Tab 1: 简历上传 =====
          {
            key: 'resume',
            label: '📄 简历上传',
            children: (
              <div>
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
            ),
          },
          // ===== Tab 2: 代码上传 =====
          {
            key: 'code',
            label: '💻 代码上传',
            children: (
              <div>
                <Dragger {...codeProps} disabled={uploading}>
                  <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                  <p className="ant-upload-text">点击或拖拽代码文件到此区域</p>
                  <p className="ant-upload-hint">支持常见编程语言文件，最大 2MB</p>
                </Dragger>
                {codeResult && (
                  <div style={{ marginTop: 16 }}>
                    <Text strong>代码内容 — {codeResult.filename}</Text>
                    <Paragraph
                      style={{ marginTop: 8, padding: 12, background: '#1e1e1e', color: '#d4d4d4', borderRadius: 6, whiteSpace: 'pre-wrap', maxHeight: 400, overflow: 'auto', fontFamily: 'monospace' }}
                      copyable
                    >
                      {codeResult.text}
                    </Paragraph>
                  </div>
                )}
              </div>
            ),
          },
          // ===== Tab 3: 项目上传 =====
          {
            key: 'project',
            label: '📦 项目上传',
            children: (
              <div>
                <Dragger {...projectProps} disabled={uploading}>
                  <p className="ant-upload-drag-icon"><FolderOpenOutlined /></p>
                  <p className="ant-upload-text">点击或拖拽项目压缩包到此区域</p>
                  <p className="ant-upload-hint">支持 ZIP / TAR.GZ / TAR.BZ2 / 7Z 格式，最大 50MB。上传后自动解析项目结构、识别技术栈</p>
                </Dragger>
                {projectResult && (
                  <div style={{ marginTop: 16 }}>
                    <div style={{ marginBottom: 12 }}>
                      <Text strong style={{ fontSize: 16 }}>{projectResult.filename}</Text>
                      <Text type="secondary" style={{ marginLeft: 12 }}>共 {projectResult.file_count} 个文件</Text>
                    </div>
                    {projectResult.tech_stack.length > 0 && (
                      <div style={{ marginBottom: 12 }}>
                        <Text strong>技术栈：</Text>
                        {projectResult.tech_stack.map((tech) => (
                          <Tag key={tech} color="blue" style={{ marginBottom: 4 }}>{tech}</Tag>
                        ))}
                      </div>
                    )}
                    <div style={{ marginBottom: 12, padding: 12, background: '#fafafa', borderRadius: 6, maxHeight: 300, overflow: 'auto' }}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>项目结构：</Text>
                      <Tree.DirectoryTree treeData={buildProjectTree(projectResult.structure)} defaultExpandAll showIcon={false} />
                    </div>
                    <Text strong>提取的文本内容：</Text>
                    <Paragraph
                      style={{ marginTop: 8, padding: 12, background: '#1e1e1e', color: '#d4d4d4', borderRadius: 6, whiteSpace: 'pre-wrap', maxHeight: 400, overflow: 'auto', fontFamily: 'monospace' }}
                      copyable
                    >
                      {projectResult.total_text.slice(0, 10000)}
                      {projectResult.total_text.length > 10000 && '\n\n... (内容过长，已截断显示)'}
                    </Paragraph>
                  </div>
                )}
              </div>
            ),
          },
          // ===== Tab 4: 我的文件 =====
          {
            key: 'manage',
            label: (
              <Badge count={uploads.length} size="small" offset={[6, -2]}>
                <span style={{ paddingRight: 4 }}>📋 我的文件</span>
              </Badge>
            ),
            children: (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <Segmented
                    value={managementFilter}
                    onChange={(val) => setManagementFilter(val as string)}
                    options={[
                      { value: 'all', label: `全部 (${uploads.length})` },
                      { value: 'resume', label: `简历 (${uploads.filter((u) => u.type === 'resume').length})` },
                      { value: 'code', label: `代码 (${uploads.filter((u) => u.type === 'code').length})` },
                      { value: 'project', label: `项目 (${uploads.filter((u) => u.type === 'project').length})` },
                    ]}
                  />
                  <Button size="small" icon={<ReloadOutlined />} onClick={refreshFileList} loading={filesLoading}>
                    刷新
                  </Button>
                </div>

                <Spin spinning={filesLoading}>
                  {filteredUploads.length === 0 ? (
                    <Empty description="还没有上传过文件，去上方标签页上传吧" />
                  ) : (
                    <List
                      dataSource={filteredUploads}
                      renderItem={(item) => {
                        const meta = TYPE_META[item.type]
                        const isActive = (item.type === 'resume' && resumeText === item.text)
                          || (item.type !== 'resume' && codeText === item.text)
                        return (
                          <List.Item
                            style={{
                              padding: '12px 16px',
                              background: isActive ? '#f6ffed' : '#fff',
                              borderRadius: 6,
                              marginBottom: 8,
                              border: isActive ? '1px solid #b7eb8f' : '1px solid #f0f0f0',
                            }}
                            actions={[
                              isActive ? (
                                <Tag color="success" icon={<CheckCircleOutlined />} style={{ marginRight: 0 }}>当前使用</Tag>
                              ) : (
                                <Button size="small" type="link" onClick={() => handleActivate(item)}>
                                  使用此文件
                                </Button>
                              ),
                              <Popconfirm
                                key="delete"
                                title="确定删除此文件？"
                                onConfirm={() => handleDelete(item.id)}
                                okText="删除" cancelText="取消"
                              >
                                <Button size="small" danger type="text" icon={<DeleteOutlined />} />
                              </Popconfirm>,
                            ]}
                          >
                            <List.Item.Meta
                              avatar={
                                <Tag color={meta.color} style={{ marginRight: 0, fontSize: 14 }}>
                                  {meta.icon} {meta.label}
                                </Tag>
                              }
                              title={
                                <Space>
                                  <Text strong>{item.filename}</Text>
                                  {item.file_count > 1 && (
                                    <Text type="secondary" style={{ fontSize: 12 }}>{item.file_count} 个文件</Text>
                                  )}
                                </Space>
                              }
                              description={
                                <div>
                                  <Text type="secondary" style={{ fontSize: 12 }} ellipsis>
                                    {item.preview}
                                  </Text>
                                  <div style={{ marginTop: 4 }}>
                                    <Text type="secondary" style={{ fontSize: 11 }}>
                                      {formatTime(item.created_at)}
                                    </Text>
                                    {item.tech_stack.length > 0 && (
                                      <span style={{ marginLeft: 8 }}>
                                        {item.tech_stack.map((t) => (
                                          <Tag key={t} style={{ fontSize: 10, lineHeight: '16px' }}>{t}</Tag>
                                        ))}
                                      </span>
                                    )}
                                  </div>
                                </div>
                              }
                            />
                          </List.Item>
                        )
                      }}
                    />
                  )}
                </Spin>
              </div>
            ),
          },
        ]}
      />
    </div>
  )
}

export default UploadPage
