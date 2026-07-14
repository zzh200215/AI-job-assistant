import request from './request'

// 薪资总览
export const getSalaryOverview = (params = {}) => request.get('/salary/overview', { params })

// 薪资对比
export const getSalaryCompare = (params = {}) => request.get('/salary/compare', { params })

// 期望薪资合理性评估
export const checkSalaryExpectation = (params = {}) =>
  request.get('/salary/expectation-check', { params })
