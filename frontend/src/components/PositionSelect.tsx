import React, { useEffect, useState } from 'react'
import { Select } from 'antd'
import { usePositionStore } from '@/stores/positionStore'
import { useChatStore } from '@/stores/chatStore'

const PositionSelect: React.FC = () => {
  const { positions, fetchPositions } = usePositionStore()
  const { selectedPosition, setPosition } = useChatStore()
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    fetchPositions().finally(() => setLoading(false))
  }, [fetchPositions])

  return (
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
  )
}

export default PositionSelect
