import request from '@/api/request'

export const getSystemStatus = (config = {}) => request.get('/system/status', config)
export const getSystemOverview = (config = {}) => request.get('/system/overview', config)
export const probeModelRuntime = (config = {}) => request.post('/system/model-probe', {}, config)
