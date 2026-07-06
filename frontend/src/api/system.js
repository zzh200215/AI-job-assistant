import request from '@/api/request'

export const getSystemStatus = () => request.get('/system/status')
export const getSystemOverview = () => request.get('/system/overview')
