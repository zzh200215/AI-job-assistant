import request from './request'

/* 后台管理面：这条挂在后端 auth.py 的 /auth/admin/* 上，但它是"管理员读别人"，
   与 account.js 那批"读/删自己"的自助端点是两条门，所以不放同一个文件。
   notifyError 在一个 GET 上只有一处承重：401 时不弹"登录已过期"那条 toast。 */

export const getAdminUsers = (params = {}, config = {}) =>
  request.get('/auth/admin/users', { params, ...config })
