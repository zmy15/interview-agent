import React, { useEffect, useState } from 'react'
import {
  Typography,
  Upload,
  Select,
  Button,
  Input,
  List,
  Tag,
  Popconfirm,
  App,
  Space,
  Card,
  Row,
  Col,
} from 'antd'
import { InboxOutlined, SearchOutlined, DeleteOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd'
import { usePositionStore } from '@/stores/positionStore'
import * as knowledgeApi from '@/api/knowledge'
import type { KnowledgeChunk } from '@/types'

const { Dragger } = Upload
const { Text, Paragraph, Title } = Typography

const KnowledgePage: React.FC = () => {
  const { positions, fetchPositions } = usePositionStore()
  const [collections, setCollections] = useState<{ name: string; count: number }[]>([])
  const [collectionsLoading, setCollectionsLoading] = useState(false)

  // 上传
  const [uploadPos, setUploadPos] = useState<string | null>(null)
  const [docType, setDocType] = useState<'faq' | 'code'>('faq')
  const [uploading, setUploading] = useState(false)

  // 搜索
  const [searchQuery, setSearchQuery] = useState('')
  const [searchPos, setSearchPos] = useState<string | null>(null)
  const [searchResults, setSearchResults] = useState<KnowledgeChunk[]>([])
  const { message } = App.useApp()
  const [searching, setSearching] = useState(false)

  const loadCollections = async () => {
    setCollectionsLoading(true)
    try {
      const res = await knowledgeApi.listCollections()
      setCollections(res.collections || [])
    } catch (err) {
      message.error((err as Error).message || '加载知识库列表失败')
    } finally {
      setCollectionsLoading(false)
    }
  }

  useEffect(() => {
    fetchPositions()
    loadCollections()
  }, [fetchPositions])

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: false,
    beforeUpload: (file) => {
      if (file.size > 10 * 1024 * 1024) {
        message.error('文件大小不能超过 10MB')
        return Upload.LIST_IGNORE
      }
      if (!uploadPos) {
        message.warning('请先选择关联岗位')
        return Upload.LIST_IGNORE
      }
      return true
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      setUploading(true)
      try {
        const result = await knowledgeApi.uploadKnowledge(
          file as File,
          uploadPos!,
          docType,
        )
        message.success(`上传成功，切分为 ${result.chunks_count} 个知识块`)
        onSuccess?.(result)
        loadCollections()
      } catch (err) {
        message.error((err as Error).message || '上传失败')
        onError?.(err as Error)
      } finally {
        setUploading(false)
      }
    },
    showUploadList: false,
  }

  const handleSearch = async () => {
    if (!searchQuery.trim() || !searchPos) {
      message.warning('请输入查询内容和选择岗位')
      return
    }
    setSearching(true)
    try {
      const res = await knowledgeApi.searchKnowledge(searchQuery, searchPos, 5)
      setSearchResults(res.results)
    } catch (err) {
      message.error((err as Error).message || '搜索失败')
    } finally {
      setSearching(false)
    }
  }

  const handleDeleteCollection = async (name: string) => {
    try {
      await knowledgeApi.deleteCollection(name)
      message.success('知识库已删除')
      loadCollections()
    } catch (err) {
      message.error((err as Error).message || '删除失败')
    }
  }

  return (
    <div>
      <Title level={4}>知识库管理</Title>

      <Row gutter={24}>
        {/* 左侧：知识库列表 */}
        <Col xs={24} lg={8}>
          <Card
            title="知识库集合"
            size="small"
            loading={collectionsLoading}
            style={{ marginBottom: 16 }}
          >
            {collections.length === 0 ? (
              <Text type="secondary">暂无知识库，请先上传文档</Text>
            ) : (
              <List
                dataSource={collections}
                renderItem={(item) => (
                  <List.Item
                    actions={[
                      <Popconfirm
                        key="delete"
                        title="确定删除此知识库？"
                        onConfirm={() => handleDeleteCollection(item.name)}
                        okText="确定"
                        cancelText="取消"
                      >
                        <Button
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                        />
                      </Popconfirm>,
                    ]}
                  >
                    <List.Item.Meta
                      title={item.name}
                      description={
                        <Tag color="blue">{item.count} 个知识块</Tag>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>

        {/* 右侧：上传 + 搜索 */}
        <Col xs={24} lg={16}>
          {/* 上传区域 */}
          <Card title="上传知识文档" size="small" style={{ marginBottom: 16 }}>
            <Space style={{ marginBottom: 12 }} wrap>
              <Select
                value={uploadPos || undefined}
                onChange={(val) => setUploadPos(val || null)}
                placeholder="选择关联岗位"
                style={{ minWidth: 180 }}
                options={positions.map((p) => ({
                  value: p.name,
                  label: p.name,
                }))}
              />
              <Select
                value={docType}
                onChange={(val) => setDocType(val)}
                style={{ width: 120 }}
                options={[
                  { value: 'faq', label: 'FAQ 文档' },
                  { value: 'code', label: '代码文档' },
                ]}
              />
            </Space>
            <Dragger {...uploadProps} disabled={uploading}>
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">点击或拖拽文档到此区域</p>
              <p className="ant-upload-hint">
                支持 PDF / DOCX / TXT / 代码文件，最大 10MB
              </p>
            </Dragger>
          </Card>

          {/* 搜索区域 */}
          <Card title="知识检索" size="small">
            <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
              <Select
                value={searchPos || undefined}
                onChange={(val) => setSearchPos(val || null)}
                placeholder="选择岗位"
                style={{ minWidth: 160 }}
                options={positions.map((p) => ({
                  value: p.name,
                  label: p.name,
                }))}
              />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="输入查询关键词..."
                onPressEnter={handleSearch}
              />
              <Button
                type="primary"
                icon={<SearchOutlined />}
                onClick={handleSearch}
                loading={searching}
              >
                搜索
              </Button>
            </Space.Compact>

            {searchResults.length > 0 && (
              <List
                dataSource={searchResults}
                renderItem={(item, idx) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <Space>
                          <Tag color="green">
                            相关度: {(item.score * 100).toFixed(0)}%
                          </Tag>
                          <Text type="secondary">#{idx + 1}</Text>
                        </Space>
                      }
                      description={
                        <Paragraph
                          ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}
                          style={{ whiteSpace: 'pre-wrap' }}
                        >
                          {item.content}
                        </Paragraph>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}

export default KnowledgePage
