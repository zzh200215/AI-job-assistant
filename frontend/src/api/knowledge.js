import request from './request'

export const uploadKnowledge = (formData, onUploadProgress) =>
  request.post('/knowledge/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress,
  })

export const listKnowledge = (params = {}) =>
  request.get('/knowledge/list', { params })

export const getKnowledgeDoc = (id) =>
  request.get(`/knowledge/${id}`)

export const getKnowledgeChunks = (id) =>
  request.get(`/knowledge/${id}/chunks`)

export const deleteKnowledgeDoc = (id) =>
  request.delete(`/knowledge/${id}`)

export const reprocessKnowledgeDoc = (id) =>
  request.post(`/knowledge/${id}/reprocess`)

export const searchKnowledge = (data) =>
  request.post('/knowledge/search', data)

export const rebuildKnowledge = () =>
  request.post('/knowledge/rebuild')

export const getEmbeddingStats = () =>
  request.get('/knowledge/admin/embedding-stats')

export const queryRewriteTest = (data) =>
  request.post('/knowledge/query-rewrite-test', data)
