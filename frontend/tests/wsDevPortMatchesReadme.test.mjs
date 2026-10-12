/**
 * D222：面试 WS 的开发态默认端口，必须和 README 写的后端开发端口是同一个数。
 *
 * 为什么要有这条：`src/api/interview.js` 在开发态把 WS 基址推成 `localhost:8000`，
 * 这个数在 README 里也有权威来源（`python -m uvicorn --port 8000`）。两处各写一遍，
 * 谁改了另一边都不会响——后端一换端口（比如本机跑 8010），页面里的面试连接就静默连不上，
 * 2026-10-12 那次真浏览器验证就是这么撞上的（当时是绕开页面直连才验成的）。
 *
 * 逃生口是 `VITE_WS_BASE`，`.env.example` 里已写明；这条守卫盯的是**默认值两边别分叉**。
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const README = readFileSync(join(HERE, '..', '..', 'README.md'), 'utf-8')
const INTERVIEW_API = readFileSync(join(HERE, '..', 'src', 'api', 'interview.js'), 'utf-8')

function readmeDevPort() {
  const hit = README.match(/uvicorn[^\n]*?--port\s+(\d+)/)
  assert.ok(
    hit,
    'README 里找不到 `uvicorn ... --port` 那一行了：锚点变了，这条守卫要重取而不是放行'
  )
  return hit[1]
}

function apiDevFallbackPort() {
  const hit =
    INTERVIEW_API.match(/window\.location\.hostname\}:?(\d+)/) ||
    INTERVIEW_API.match(/hostname\s*\+\s*':(\d+)'/)
  assert.ok(hit, 'interview.js 里那段"开发态按页面推断"的形状变了：判据要重取')
  return hit[1]
}

test('开发态 WS 的默认端口等于 README 记的后端开发端口', () => {
  assert.equal(apiDevFallbackPort(), readmeDevPort())
})

test('两个读数都不是从空气里来的', () => {
  // 防空转：README 那句必须真含端口数字，interview.js 那段必须真在 connectInterviewWS 里
  assert.match(readmeDevPort(), /^\d{4,5}$/)
  assert.ok(INTERVIEW_API.includes('VITE_WS_BASE'), '逃生口 VITE_WS_BASE 从代码里消失了')
  assert.ok(
    INTERVIEW_API.includes(':8000') || /window\.location\.hostname\}:?\d+/.test(INTERVIEW_API),
    '看不到开发态端口这个事实本身，说明上面那个正则匹到了别处'
  )
})
