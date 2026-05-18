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
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import { usePositionStore } from '@/stores/positionStore'
import * as positionApi from '@/api/position'
import type { PositionResponse, JDResponse } from '@/types'

const { Text } = Typography

const PositionPage: React.FC = () => {
  const { positions, loading, fetchPositions, createPosition, updatePosition, deletePosition } =
    usePositionStore()
  const [modalOpen, setModalOpen] = useState(false)
  const [editingPos, setEditingPos] = useState<PositionResponse | null>(null)
  const [form] = Form.useForm()

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
    setEditingPos(null)
    form.resetFields()
    setModalOpen(true)
  }

  const handleEdit = (pos: PositionResponse) => {
    setEditingPos(pos)
    form.setFieldsValue({ name: pos.name, description: pos.description })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    try {
      if (editingPos) {
        await updatePosition(editingPos.name, values.description)
        message.success('岗位已更新')
      } else {
        await createPosition(values.name, values.description)
        message.success('岗位已创建')
      }
      setModalOpen(false)
      form.resetFields()
    } catch (err) {
      message.error((err as Error).message || '操作失败')
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
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: 'JD 数量',
      key: 'jdCount',
      render: (_: unknown, record: PositionResponse) => (
        <Tag color="blue">{record.jds.length} 条</Tag>
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
      width: 240,
      render: (_: unknown, record: PositionResponse) => (
        <Space size="small">
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
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

      {/* 岗位编辑弹窗 */}
      <Modal
        title={editingPos ? '编辑岗位' : '新建岗位'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="岗位名称"
            rules={[
              { required: true, message: '请输入岗位名称' },
              { min: 2, max: 50, message: '2-50 个字符' },
              {
                pattern: /^[\w\u4e00-\u9fff-]{2,50}$/,
                message: '允许字母/数字/中文/下划线/连字符',
              },
            ]}
          >
            <Input disabled={!!editingPos} placeholder="如: 前端工程师" />
          </Form.Item>
          <Form.Item name="description" label="岗位描述">
            <Input.TextArea rows={3} placeholder="简要描述岗位职责和要求" />
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
                  background: '#fafafa',
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
