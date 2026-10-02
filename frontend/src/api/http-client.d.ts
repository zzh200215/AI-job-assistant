import type { AxiosInstance, AxiosRequestConfig } from 'axios'

declare module 'axios' {
  interface AxiosRequestConfig {
    // 为 false 时响应拦截器不弹错误 toast（GET 一律不弹）。
    notifyError?: boolean
  }
}

// request.js 的响应拦截器 resolve 的是解包后的载荷（`code === 0` 给 `body.data`，
// 其余给整个 body），不是 AxiosResponse。这里的八个方法就是把这件事写进类型。
export type HttpClient = Omit<
  AxiosInstance,
  'request' | 'get' | 'delete' | 'head' | 'options' | 'post' | 'put' | 'patch'
> & {
  request<T = any>(config: AxiosRequestConfig): Promise<T>
  get<T = any>(url: string, config?: AxiosRequestConfig): Promise<T>
  delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<T>
  head<T = any>(url: string, config?: AxiosRequestConfig): Promise<T>
  options<T = any>(url: string, config?: AxiosRequestConfig): Promise<T>
  post<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
  put<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
  patch<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
}

// 拦截器 reject 出去的那套约定字段；调用方在 catch 里读它们。
export interface ApiError extends Error {
  requestId?: string
  payload?: unknown
  userMessage?: string
  isApiError?: boolean
}
