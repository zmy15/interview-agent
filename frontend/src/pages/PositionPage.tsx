import React, { useEffect, useState } from 'react'
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Popconfirm,
  Space,
  Typography,
  App,
  Tag,
  theme,
} from 'antd'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import { usePositionStore } from '@/stores/positionStore'
import * as positionApi from '@/api/position'
import type { PositionResponse, JDResponse } from '@/types'

const { Text } = Typography

const PositionPage: React.FC = () => {
  const { positions, loading, fetchPositions, createPosition, deletePosition } =
    usePositionStore()
  const [modalOpen, setModalOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()
  const { token } = theme.useToken()

  // JD 管理
  const [jdModalOpen, setJdModalOpen] = useState(false)
  const { message } = App.useApp()
  const [jdForm] = Form.useForm()
  const [currentPosition, setCurrentPosition] = useState<string>('')
  const [jds, setJds] = useState<JDResponse[]>([])
  const [jdLoading, setJdLoading] = useState(false)

  useEffect(() => {
    fetchPositions()
  }, [fetchPositions])

  const handleCreate = () => {
    form.resetFields()
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    let values: { name: string; jd_content?: string }
    try {
      values = await form.validateFields()
    } catch {
      return // 校验未通过，antd 已在表单上提示
    }

    setSubmitting(true)
    try {
      // JD 与岗位一起提交：后端在同一事务里落库，不会出现「岗位建好但 JD 丢了」
      await createPosition(values.name.trim(), (values.jd_content || '').trim() || undefined)
      message.success(values.jd_content?.trim() ? '岗位与 JD 已创建' : '岗位已创建')
      setModalOpen(false)
      form.resetFields()
    } catch (err) {
      message.error((err as Error).message || '操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (name: string) => {
    try {
      await deletePosition(name)
      message.success('岗位已删除')
    } catch (err) {
      message.error((err as Error).message || '删除失败')
    }
  }

  const loadJDs = async (positionName: string) => {
    setCurrentPosition(positionName)
    setJdLoading(true)
    try {
      const pos = await positionApi.getPosition(positionName)
      setJds(pos.jds)
      setJdModalOpen(true)
    } catch (err) {
      message.error((err as Error).message || '加载 JD 失败')
    } finally {
      setJdLoading(false)
    }
  }

  const handleAddJD = async () => {
    const values = await jdForm.validateFields()
    try {
      await positionApi.addJD(currentPosition, { content: values.content })
      message.success('JD 已添加')
      jdForm.resetFields()
      // 刷新 JD 列表
      const pos = await positionApi.getPosition(currentPosition)
      setJds(pos.jds)
    } catch (err) {
      message.error((err as Error).message || '添加 JD 失败')
    }
  }

  const handleDeleteJD = async (jdId: string) => {
    try {
      await positionApi.removeJD(currentPosition, jdId)
      message.success('JD 已删除')
      const pos = await positionApi.getPosition(currentPosition)
      setJds(pos.jds)
    } catch (err) {
      message.error((err as Error).message || '删除 JD 失败')
    }
  }

  const columns = [
    {
      title: '岗位名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => <Text strong>{name}</Text>,
    },
    {
      title: '岗位类型',
      dataIndex: 'position_type',
      key: 'position_type',
      width: 100,
      render: (t: string) => {
        const colorMap: Record<string, string> = {
          '技术岗': 'blue',
          '非技术岗': 'green',
          '未知': 'default',
        }
        return <Tag color={colorMap[t] || 'default'}>{t}</Tag>
      },
    },
    {
      title: 'JD 数量',
      key: 'jdCount',
      width: 100,
      render: (_: unknown, record: PositionResponse) => (
        <Tag color={record.jds.length > 0 ? 'blue' : 'default'}>{record.jds.length} 条</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (t: string) => new Date(t).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: unknown, record: PositionResponse) => (
        <Space size="small">
          <Button
            size="small"
            onClick={() => loadJDs(record.name)}
          >
            管理 JD
          </Button>
          <Popconfirm
            title="确定删除此岗位？"
            onConfirm={() => handleDelete(record.name)}
            okText="确定"
            cancelText="取消"
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          marginBottom: 16,
        }}
      >
        <Typography.Title level={4} style={{ margin: 0 }}>
          岗位管理
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
          新建岗位
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={positions}
        rowKey="name"
        loading={loading}
        pagination={false}
      />

      {/* 新建岗位弹窗：岗位名称 + 第一份 JD（一步到位） */}
      <Modal
        title="新建岗位"
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        okText="创建"
        cancelText="取消"
        confirmLoading={submitting}
        width={640}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="岗位名称"
            rules={[
              { required: true, whitespace: true, message: '请输入岗位名称' },
              {
                // 名字允许空格，但「 a 」「  」这类去掉首尾空白后不足 2 字符的不行，
                // 否则后端归一化后会变成 1 个字符、返回 422
                validator: (_, value: string) =>
                  !value || value.trim().length >= 2
                    ? Promise.resolve()
                    : Promise.reject(new Error('去掉首尾空格后至少 2 个字符')),
              },
              { max: 50, message: '最多 50 个字符' },
              {
                // 与后端 _NAME_PATTERN 保持一致：允许空格，但不允许纯空白
                pattern: /^[\w\u4e00-\u9fff\- ]{2,50}$/,
                message: '允许字母/数字/中文/下划线/连字符/空格',
              },
            ]}
          >
            <Input placeholder="如: AI Agent 质量效能工程师" maxLength={50} />
          </Form.Item>
          <Form.Item
            name="jd_content"
            label="JD 内容（可选）"
            extra="创建后立即成为该岗位的第一份 JD，对话时会被拼进提示词；之后可用「管理 JD」继续添加或修改。"
          >
            <Input.TextArea rows={8} placeholder="粘贴岗位描述 (Job Description)…" />
          </Form.Item>
        </Form>
      </Modal>

      {/* JD 管理弹窗 */}
      <Modal
        title={`管理 JD — ${currentPosition}`}
        open={jdModalOpen}
        onCancel={() => setJdModalOpen(false)}
        footer={null}
        width={600}
        loading={jdLoading}
      >
        <div style={{ marginBottom: 16 }}>
          <Form form={jdForm} layout="vertical">
            <Form.Item
              name="content"
              label="新增 JD"
              rules={[{ required: true, message: '请输入 JD 内容' }]}
            >
              <Input.TextArea rows={4} placeholder="输入岗位描述 (Job Description)" />
            </Form.Item>
            <Button type="primary" onClick={handleAddJD}>
              添加 JD
            </Button>
          </Form>
        </div>
        <div>
          {jds.length === 0 ? (
            <Text type="secondary">暂无 JD</Text>
          ) : (
            jds.map((jd) => (
              <div
                key={jd.id}
                style={{
                  padding: '8px 12px',
                  marginBottom: 8,
                  background: token.colorFillSecondary,
                  borderRadius: 6,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  gap: 8,
                }}
              >
                <div style={{ flex: 1 }}>
                  <Text style={{ whiteSpace: 'pre-wrap' }}>{jd.content}</Text>
                  <br />
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {new Date(jd.created_at).toLocaleString('zh-CN')}
                  </Text>
                </div>
                <Popconfirm
                  title="确定删除此 JD？"
                  onConfirm={() => handleDeleteJD(jd.id)}
                  okText="确定"
                  cancelText="取消"
                >
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </div>
            ))
          )}
        </div>
      </Modal>
    </div>
  )
}

export default PositionPage
