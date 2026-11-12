import request from './request'

/* 演示数据入口（首次体验）。

   一次动三张表：一份自己的简历、一批演示岗位、几条不同阶段的投递记录。
   三步各自幂等——重复点只会跳过已存在的行，不会灌重复，所以可以放心把按钮留在页面上。

   为什么不是 `seedDemoJobs()`：那个只灌岗位，灌完工作台上仍是"没有简历"，
   人还是走不动主链。`/demo/seed` 是"从零能走完一遍"的那一颗。 */
export const seedDemoDataset = () => request.post('/demo/seed')
