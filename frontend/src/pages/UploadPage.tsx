import React, { useState } from 'react'
import { Tabs, Upload, Tag, Typography, App, Tree } from 'antd'
import { InboxOutlined, FolderOpenOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd'
import type { DataNode } from 'antd/es/tree'
import * as uploadApi from '@/api/upload'
import { useAppStore } from '@/stores/appStore'
import type { UploadResponse, ProjectUploadResponse, ProjectStructure } from '@/types'

const { Dragger } = Upload
const { Text, Paragraph } = Typography

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
      title: (
        <span>
          <Tag color={color}>{label}</Tag>
          <Text type="secondary">({files.length} 个文件)</Text>
        </span>
      ),
      key: cat,
      selectable: false,
      children: files.map((f) => ({
        title: <Text code style={{ fontSize: 12 }}>{f}</Text>,
        key: `${cat}/${f}`,
        isLeaf: true,
      })),
    })
  }
  return nodes
}

const UploadPage: React.FC = () => {
  const { setResumeText, setCodeText } = useAppStore()
  const [resumeResult, setResumeResult] = useState<UploadResponse | null>(null)
  const [codeResult, setCodeResult] = useState<UploadResponse | null>(null)
  const [projectResult, setProjectResult] = useState<ProjectUploadResponse | null>(null)
  const { message } = App.useApp()
  const [uploading, setUploading] = useState(false)

  const resumeProps: UploadProps = {
    name: 'file',
    multiple: false,
    accept: '.pdf,.docx,.doc,.txt',
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
        setResumeText(result.text)
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
        setCodeText(result.text)
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

  const projectProps: UploadProps = {
    name: 'file',
    multiple: false,
    accept: '.zip,.tar.gz,.tgz,.tar.bz2,.tar,.7z',
    beforeUpload: (file) => {
      if (file.size > 50 * 1024 * 1024) {
        message.error('文件大小不能超过 50MB')
        return Upload.LIST_IGNORE
      }
      return true
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      setUploading(true)
      try {
        const result = await uploadApi.uploadProject(file as File)
        setProjectResult(result)
        setCodeText(result.total_text)  // 项目文本也存入 codeText，供对话使用
        message.success(`项目解析成功 — 共 ${result.file_count} 个文件`)
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
                    支持 PDF / DOCX / DOC / TXT 格式，最大 5MB
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
          {
            key: 'project',
            label: '📦 项目上传',
            children: (
              <div>
                <Dragger {...projectProps} disabled={uploading}>
                  <p className="ant-upload-drag-icon">
                    <FolderOpenOutlined />
                  </p>
                  <p className="ant-upload-text">点击或拖拽项目压缩包到此区域</p>
                  <p className="ant-upload-hint">
                    支持 ZIP / TAR.GZ / TAR.BZ2 / 7Z 格式，最大 50MB。
                    上传后自动解析项目结构、识别技术栈
                  </p>
                </Dragger>
                {projectResult && (
                  <div style={{ marginTop: 16 }}>
                    <div style={{ marginBottom: 12 }}>
                      <Text strong style={{ fontSize: 16 }}>
                        {projectResult.filename}
                      </Text>
                      <Text type="secondary" style={{ marginLeft: 12 }}>
                        共 {projectResult.file_count} 个文件
                      </Text>
                    </div>

                    {/* 技术栈标签 */}
                    {projectResult.tech_stack.length > 0 && (
                      <div style={{ marginBottom: 12 }}>
                        <Text strong>技术栈：</Text>
                        {projectResult.tech_stack.map((tech) => (
                          <Tag key={tech} color="blue" style={{ marginBottom: 4 }}>
                            {tech}
                          </Tag>
                        ))}
                      </div>
                    )}

                    {/* 项目文件结构树 */}
                    <div
                      style={{
                        marginBottom: 12,
                        padding: 12,
                        background: '#fafafa',
                        borderRadius: 6,
                        maxHeight: 300,
                        overflow: 'auto',
                      }}
                    >
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>
                        项目结构：
                      </Text>
                      <Tree.DirectoryTree
                        treeData={buildProjectTree(projectResult.structure)}
                        defaultExpandAll
                        showIcon={false}
                      />
                    </div>

                    {/* 提取的文本内容 */}
                    <Text strong>提取的文本内容：</Text>
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
                      {projectResult.total_text.slice(0, 10000)}
                      {projectResult.total_text.length > 10000 && '\n\n... (内容过长，已截断显示)'}
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
