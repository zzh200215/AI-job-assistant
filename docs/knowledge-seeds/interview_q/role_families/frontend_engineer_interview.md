## 前端｜事件循环与渲染时机

- 题目：宏任务、微任务和浏览器渲染的先后顺序是什么？
- 考察点：任务队列、微任务清空、requestAnimationFrame、长任务。
- 参考要点：同步代码先跑；每轮宏任务后清空微任务；再进入渲染；requestAnimationFrame 在渲染前；长任务会阻塞渲染与交互。
- 追问：setTimeout 延时为 0 为什么不会立刻执行？

## 前端｜Vue 响应式与更新调度

- 题目：Vue 3 的 reactive、ref 和依赖收集是怎样工作的？
- 考察点：Proxy、track 与 trigger、effect 调度、批量更新。
- 参考要点：Proxy 拦截读写；读取时 track 收集 effect；修改时 trigger 通知；更新任务进微任务队列批量执行；ref 用对象包装原始值。
- 追问：解构 props 或 reactive 对象为什么会丢失响应式？

## 前端｜首屏性能定位与优化

- 题目：首屏加载很慢，你如何定位和优化？
- 考察点：LCP、INP、CLS、资源体积、缓存、渲染阻塞。
- 参考要点：用 Performance 面板看长任务与关键路径；压缩并拆分资源；路由懒加载；静态资源长缓存；首屏图片控制尺寸并预加载；减少无效重渲染。
- 追问：LCP 元素是一张背景大图，优先改哪里？

## 前端｜XSS 与 CSRF 的成因和防护

- 题目：XSS 和 CSRF 分别如何产生，前端应该怎么防？
- 考察点：输出编码、CSP、Cookie 属性、SameSite、CSRF Token。
- 参考要点：所有不可信内容按上下文编码；CSP 禁内联脚本；敏感 Cookie 加 HttpOnly 与 SameSite；写操作校验 Token 或来源；避免把密钥放前端。
- 追问：Token 放 localStorage 有哪些风险，替代方案是什么？
