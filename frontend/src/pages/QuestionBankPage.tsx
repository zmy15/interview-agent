/**
 * 题库管理页面 — 浏览/搜索/添加题目
 * LeetCode 题目已自动内置，无需手动导入
 */

import React, { useEffect, useState, useCallback } from 'react'
import {
  Table,
  Button,
  Input,
  Select,
  Space,
  Tag,
  Modal,
  Form,
  App,
  Typography,
  Popconfirm,
  Tooltip,
} from 'antd'
import {
  PlusOutlined,
  SearchOutlined,
  DeleteOutlined,
  EditOutlined,
} from '@ant-design/icons'
import { questionBankApi, type QuestionItem, type QuestionCreateRequest } from '@/api/questionBank'

const { Text, Paragraph } = Typography
const { TextArea } = Input

const DIFFICULTY_COLORS: Record<string, string> = {
  easy: 'green',
  medium: 'orange',
  hard: 'red',
}

const DIFFICULTY_LABELS: Record<string, string> = {
  easy: '简单',
  medium: '中等',
  hard: '困难',
}

const CATEGORY_LABELS: Record<string, string> = {
  algorithm: '算法',
  frontend: '前端',
  backend: '后端',
  system_design: '系统设计',
  behavioral: '行为面试',
  general: '通用',
}

const QuestionBankPage: React.FC = () => {
  const [questions, setQuestions] = useState<QuestionItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')

  // 弹窗状态
  const [modalOpen, setModalOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [viewContent, setViewContent] = useState<string | null>(null)
  const [form] = Form.useForm()
  const { message } = App.useApp()

  const pageSize = 15

  const fetchQuestions = useCallback(async () => {
    setLoading(true)
    try {
      const res = await questionBankApi.list({ page, page_size: pageSize, ...(search ? { search } : {}) })
      setQuestions(res.questions)
      setTotal(res.total)
    } catch (err) {
      message.error((err as Error).message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page, search, message])

  useEffect(() => { fetchQuestions() }, [fetchQuestions])

  const handleAdd = () => {
    setEditingId(null)
    form.resetFields()
    form.setFieldsValue({ category: 'general', difficulty: 'medium', tags: [] })
    setModalOpen(true)
  }

  const handleEdit = (record: QuestionItem) => {
    setEditingId(record.id)
    form.setFieldsValue({
      title: record.title,
      content: record.content,
      category: record.category,
      difficulty: record.difficulty,
      tags: record.tags,
      expected_answer: record.expected_answer,
    })
    setModalOpen(true)
  }

  const handleDelete = async (id: string) => {
    try {
      await questionBankApi.delete(id)
      message.success('已删除')
      fetchQuestions()
    } catch (err) {
      message.error((err as Error).message || '删除失败')
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const data: QuestionCreateRequest = {
        ...values,
        tags: values.tags || [],
      }

      if (editingId) {
        await questionBankApi.update(editingId, data)
        message.success('已更新')
      } else {
        await questionBankApi.create(data)
        message.success('已添加')
      }
      setModalOpen(false)
      fetchQuestions()
    } catch (err) {
      if ((err as Error).message) {
        message.error((err as Error).message)
      }
    }
  }

  const columns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (text: string, record: QuestionItem) => (
        <a onClick={() => setViewContent(record.content)}>{text}</a>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 100,
      render: (c: string) => CATEGORY_LABELS[c] || c,
    },
    {
      title: '难度',
      dataIndex: 'difficulty',
      key: 'difficulty',
      width: 80,
      render: (d: string) => (
        <Tag color={DIFFICULTY_COLORS[d] || 'default'}>
          {DIFFICULTY_LABELS[d] || d}
        </Tag>
      ),
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      width: 200,
      render: (tags: string[]) =>
        tags?.length
          ? tags.map((t) => <Tag key={t}>{t}</Tag>)
          : <Text type="secondary">—</Text>,
    },
    {
      title: '使用次数',
      dataIndex: 'usage_count',
      key: 'usage_count',
      width: 80,
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: unknown, record: QuestionItem) => (
        <Space>
          <Tooltip title="编辑">
            <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          </Tooltip>
          <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        {/* 工具栏 */}
        <Space wrap>
          <Input
            placeholder="搜索题目..."
            prefix={<SearchOutlined />}
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            style={{ width: 280 }}
            allowClear
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            添加题目
          </Button>
        </Space>

        {/* 表格 */}
        <Table
          dataSource={questions}
          columns={columns}
          rowKey="id"
          loading={loading}
          size="middle"
          pagination={{
            current: page,
            pageSize,
            total,
            onChange: (p) => setPage(p),
            showTotal: (t) => `共 ${t} 题`,
          }}
        />
      </Space>

      {/* 添加/编辑弹窗 */}
      <Modal
        title={editingId ? '编辑题目' : '添加题目'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        width={640}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="题目标题" rules={[{ required: true }]}>
            <Input placeholder="如：两数之和 / 什么是闭包 / 请描述一次你解决冲突的经历" />
          </Form.Item>
          <Form.Item name="content" label="题目内容" rules={[{ required: true }]}>
            <TextArea rows={6} placeholder="题目描述、示例、约束条件等..." />
          </Form.Item>
          <Space size="middle">
            <Form.Item name="category" label="分类" rules={[{ required: true }]}>
              <Select
                style={{ width: 160 }}
                options={[
                  { value: 'algorithm', label: '算法' },
                  { value: 'frontend', label: '前端' },
                  { value: 'backend', label: '后端' },
                  { value: 'system_design', label: '系统设计' },
                  { value: 'behavioral', label: '行为面试' },
                  { value: 'general', label: '通用' },
                ]}
              />
            </Form.Item>
            <Form.Item name="difficulty" label="难度" rules={[{ required: true }]}>
              <Select
                style={{ width: 120 }}
                options={[
                  { value: 'easy', label: '简单' },
                  { value: 'medium', label: '中等' },
                  { value: 'hard', label: '困难' },
                ]}
              />
            </Form.Item>
          </Space>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" placeholder="输入标签后回车" />
          </Form.Item>
          <Form.Item name="expected_answer" label="参考答案（可选）">
            <TextArea rows={4} placeholder="参考答案或解题思路..." />
          </Form.Item>
        </Form>
      </Modal>

      {/* 查看内容弹窗 */}
      <Modal
        title="题目详情"
        open={!!viewContent}
        onCancel={() => setViewContent(null)}
        footer={null}
        width={700}
      >
        <Paragraph style={{ whiteSpace: 'pre-wrap', maxHeight: '60vh', overflow: 'auto' }}>
          {viewContent}
        </Paragraph>
      </Modal>
    </div>
  )
}

export default QuestionBankPage
