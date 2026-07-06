// 岗位数据源管理 API
import request from './request'

export const listDataSources = (params = {}) =>
  request.get('/datasource', { params })

export const createDataSource = (data) =>
  request.post('/datasource', data)

export const getDataSource = (id) =>
  request.get(`/datasource/${id}`)

export const updateDataSource = (id, data) =>
  request.put(`/datasource/${id}`, data)

export const deleteDataSource = (id) =>
  request.delete(`/datasource/${id}`)

export const testDataSource = (id) =>
  request.post(`/datasource/${id}/test`, {})

export const syncDataSource = (id, data = {}) =>
  request.post(`/datasource/${id}/sync`, data)

export const listSyncLogs = (id, params = {}) =>
  request.get(`/datasource/${id}/logs`, { params })
