/**
 * 跨页"上一次选择"（简历 / JD / 分析记录）的唯一持有者。
 *
 * 以前这件事有两套互不相通的键名：`recruit.lastX`（全局，被分析/规划/面试/历史四类页面读写）
 * 与 `recruit.lastX.<uid>`（按登录用户，被智能分析与岗位搜索读写）。后果不是风格问题：
 * 全局那套跨账号存活，换过账号的浏览器会把上一个账号的 id 预填进表单并发给后端，而每个读取方
 * 拿到的都是 `记录不存在，或无权限访问`；同时在工作台里选的简历永远传不到规划页，因为它写的是
 * 带 uid 的键。现在只有一套：按登录用户分槽，未登录落在 `guest` 槽，且登录时会把 guest 槽与
 * 旧的全局键一起清掉，所以上一个人在共享浏览器里留下的选择不会嫁给下一个登录的人。
 */

const PREFIX = 'recruit'
const LABEL = { resume: 'lastResumeId', jd: 'lastJDId', record: 'lastRecordId' }
const FIELDS = ['resume', 'jd', 'record']

const slot = { uid: null }

function storageName(field, uid = slot.uid) {
  return `${PREFIX}.${LABEL[field]}.${uid ?? 'guest'}`
}

function writeField(field, value) {
  if (value === null || value === undefined || value === '') return
  localStorage.setItem(storageName(field), String(value))
}

function readField(field) {
  const raw = localStorage.getItem(storageName(field))
  if (!raw) return null
  const id = Number(raw)
  return Number.isFinite(id) ? id : null
}

export function rememberResume(id) {
  writeField('resume', id)
}

export function readResumeId() {
  return readField('resume')
}

export function forgetResume() {
  localStorage.removeItem(storageName('resume'))
}

export function rememberJD(id) {
  writeField('jd', id)
}

export function readJDId() {
  return readField('jd')
}

export function forgetJD() {
  localStorage.removeItem(storageName('jd'))
}

export function rememberRecord(id) {
  writeField('record', id)
}

export function readRecordId() {
  return readField('record')
}

/**
 * 告诉这个模块"现在是谁的会话"。由 `stores/auth.js` 独家调用（它是 user 的持有者）。
 * 拿到真实 uid 时顺手清掉旧全局键与 guest 槽：那些值是登录前/上一个账号留下的，
 * 谁都不该再读它们。
 */
export function setSelectionOwner(userOrId = null) {
  const id = userOrId && typeof userOrId === 'object' ? userOrId.id : userOrId
  slot.uid = id || null
  if (slot.uid === null) return
  for (const field of FIELDS) {
    localStorage.removeItem(`${PREFIX}.${LABEL[field]}`)
    localStorage.removeItem(storageName(field, 'guest'))
  }
}
