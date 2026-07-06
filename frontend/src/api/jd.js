import request from './request'

export const createJD = (data) => request.post('/jd', data)
export const parseJD   = (jd_id) => request.post('/jd/parse', { jd_id })
export const getJD     = (id) => request.get(`/jd/${id}`)
export const getJDList = (params = {}) => request.get('/jd/list', { params })
