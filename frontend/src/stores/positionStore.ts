import { create } from 'zustand'
import type { PositionResponse } from '@/types'
import * as positionApi from '@/api/position'

interface PositionState {
  positions: PositionResponse[]
  loading: boolean
  error: string | null

  fetchPositions: () => Promise<void>
  createPosition: (name: string, description: string) => Promise<void>
  updatePosition: (name: string, description: string) => Promise<void>
  deletePosition: (name: string) => Promise<void>
}

export const usePositionStore = create<PositionState>()((set) => ({
  positions: [],
  loading: false,
  error: null,

  fetchPositions: async () => {
    set({ loading: true, error: null })
    try {
      const res = await positionApi.listPositions()
      set({ positions: res.positions, loading: false })
    } catch (err) {
      set({ error: (err as Error).message, loading: false })
    }
  },

  createPosition: async (name, description) => {
    set({ loading: true, error: null })
    try {
      await positionApi.createPosition({ name, description })
      // 刷新列表
      const res = await positionApi.listPositions()
      set({ positions: res.positions, loading: false })
    } catch (err) {
      set({ error: (err as Error).message, loading: false })
      throw err
    }
  },

  updatePosition: async (name, description) => {
    set({ loading: true, error: null })
    try {
      await positionApi.updatePosition(name, { description })
      const res = await positionApi.listPositions()
      set({ positions: res.positions, loading: false })
    } catch (err) {
      set({ error: (err as Error).message, loading: false })
      throw err
    }
  },

  deletePosition: async (name) => {
    set({ loading: true, error: null })
    try {
      await positionApi.deletePosition(name)
      const res = await positionApi.listPositions()
      set({ positions: res.positions, loading: false })
    } catch (err) {
      set({ error: (err as Error).message, loading: false })
      throw err
    }
  },
}))
