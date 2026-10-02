import request from './request'

// 薪资总览。第二个入参是给调用方透传 axios config 的口子（`useSalaryMarket.js:32` 就用它带
// `notifyError: false`）——在它之前那个参数是被**丢掉**的，见 docs/upgrade-plan.md D74。
export const getSalaryOverview = (params = {}, config = {}) =>
  request.get('/salary/overview', { params, ...config })

// 薪资对比
export const getSalaryCompare = (params = {}) => request.get('/salary/compare', { params })

// 期望薪资合理性评估
export const checkSalaryExpectation = (params = {}) =>
  request.get('/salary/expectation-check', { params })
