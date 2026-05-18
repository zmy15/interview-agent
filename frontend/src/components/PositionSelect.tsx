import React, { useEffect, useState, useMemo } from 'react'
import { Select, Space } from 'antd'
import { usePositionStore } from '@/stores/positionStore'
import { useChatStore } from '@/stores/chatStore'
import type { JDResponse } from '@/types'

const PositionSelect: React.FC = () => {
  const { positions, fetchPositions } = usePositionStore()
  const { selectedPosition, setPosition, selectedJdId, setJdId } = useChatStore()
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    fetchPositions().finally(() => setLoading(false))
  }, [fetchPositions])

  // 当前选中岗位的 JD 列表
  const currentJds: JDResponse[] = useMemo(() => {
    if (!selectedPosition) return []
    const pos = positions.find((p) => p.name === selectedPosition)
    return pos?.jds ?? []
  }, [selectedPosition, positions])

  // 是否有多个 JD 可选
  const showJdSelect = currentJds.length > 1

  // JD 选项（含"全部JD"默认项）
  const jdOptions = useMemo(() => {
    if (currentJds.length === 0) return []
    return [
      { value: '__all__', label: `全部 JD（${currentJds.length} 份）` },
      ...currentJds.map((jd, i) => ({
        value: jd.id,
        label: `JD ${i + 1}${jd.content ? `: ${jd.content.slice(0, 40)}...` : ''}`,
      })),
    ]
  }, [currentJds])

  return (
    <Space size={4}>
      <Select
        value={selectedPosition || undefined}
        onChange={(val) => setPosition(val || null)}
        placeholder="选择岗位（可选）"
        loading={loading}
        allowClear
        style={{ minWidth: 180 }}
        options={positions.map((p) => ({
          value: p.name,
          label: p.name,
        }))}
      />
      {showJdSelect && (
        <Select
          value={selectedJdId || '__all__'}
          onChange={(val) => setJdId(val === '__all__' ? null : val)}
          placeholder="选择 JD"
          style={{ minWidth: 200 }}
          options={jdOptions}
        />
      )}
    </Space>
  )
}

export default PositionSelect
