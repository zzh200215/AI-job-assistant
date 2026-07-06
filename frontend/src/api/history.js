import request from './request'

export const listHistory = (params) => request.get('/history', { params })
export const getHistoryDetail = (id) => request.get(`/history/${id}`)
export const deleteHistory = (id) => request.delete(`/history/${id}`)
