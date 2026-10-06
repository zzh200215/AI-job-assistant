/**
 * 跨页"上一次选择"（简历 / JD / 分析记录）的唯一持有者。
 *
 * 以前这件事有两套互不相通的键名：`recruit.lastX`（全局，被分析/规划/面试/历史四类页面读写）
 * 与 `recruit.lastX.<uid>`（按登录用户，被智能分析与岗位搜索读写）。后果不是风格问题：
 * 全局那套跨账号存活，换过账号的浏览器会把上一个账号的 id 预填进表单并发给后端，而每个读取方
 * 拿到的都是 `记录不存在，或无权限访问`；同时在工作台里选的简历永远传不到规划页，因为它写的是
 * 带 uid 的键。现在只有一套：按登录用户分槽，未登录落在 `guest` 槽，且登录时会把 guest 槽与
 * 旧的全局键一起清掉，所以上一个人在共享浏览器里留下的选择不会嫁给下一个登录的人。
 *
 * `JobSearch` → `SmartAnalysis` 那一坨一次性表单预填从 D125 起也走同一套槽位与同一套登录处置，
 * 但它的**形状没有被统一**（§10.9 ② 拍的是"只统一槽位"，见下面 `PENDING` 那段）。
 */

const PREFIX = 'recruit'
/* `defaultResume` 是 D102 加进来的第四个字段。它和另外三个是同一件事（"上一次选了哪份简历"），
   此前却写在**全局键** `recruit.defaultResumeId` 上：换过账号的浏览器会把上一个人的默认版本
   带给下一个人，而简历列表里那一行会因此标成"投递中"、`activeResume` 也跟着选错。
   加进 LABEL 之后它自动享有同一套按用户分槽 + 登录时清 guest 槽与旧全局键的处置。 */
const LABEL = {
  resume: 'lastResumeId',
  jd: 'lastJDId',
  record: 'lastRecordId',
  defaultResume: 'defaultResumeId',
}
const FIELDS = ['resume', 'jd', 'record', 'defaultResume']
/* §10.9 决定 ② 走"只统一槽位、不统一形状"那一支（D125，他点的 ①）。
   `recruit.pendingAnalysis` 与上面四个不是同一种东西：那四个是一个 id，这一坨是
   `JobSearch` 递给 `SmartAnalysis` 的一次性表单预填（`jdId`/`title`/`company`/`jd_text`）。
   把它塞进 `LABEL` 就得给这个只装 id 的模块加第四种值形状，而 ② 当初要拍的正是"要不要那么统一"。
   所以这里只借同一套分槽与同一套登录处置：**键名多一个后缀，形状一字不改**。
   跨账号那条老路它本来也有——共享浏览器里 A 点了一键分析没走到目的地，B 登录进来就会看见 A 的
   岗位名与 JD 原文被预填进表单；窗口小不等于不存在。 */
const PENDING = 'pendingAnalysis'

const slot = { uid: null }

function storageName(field, uid = slot.uid) {
  return `${PREFIX}.${LABEL[field]}.${uid ?? 'guest'}`
}

function pendingName(uid = slot.uid) {
  return `${PREFIX}.${PENDING}.${uid ?? 'guest'}`
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

export function rememberDefaultResume(id) {
  writeField('defaultResume', id)
}

export function readDefaultResumeId() {
  return readField('defaultResume')
}

export function readRecordId() {
  return readField('record')
}

/** 一次性载荷：`JobSearch` 点"一键智能分析"时写，`SmartAnalysis` 进来取走。 */
export function rememberPendingAnalysis(payload) {
  localStorage.setItem(pendingName(), JSON.stringify(payload))
}

/**
 * 取走 = 读 + 立刻删，坏 JSON 也一样删。这条 `finally` 里的删除是原样搬过来的（不是新加的动作）：
 * 留着它，下一次进这一页会把上一次的岗位名继续预填进来，而那一次点击可能是一周前的。
 * 解析失败保持原来那句 `console.warn`——诊断搬到这里来了，因为键搬到这里来了。
 */
export function takePendingAnalysis() {
  const key = pendingName()
  const raw = localStorage.getItem(key)
  if (!raw) return null
  localStorage.removeItem(key)
  try {
    return JSON.parse(raw)
  } catch (e) {
    console.warn('解析 pendingAnalysis 失败', e)
    return null
  }
}

/**
 * 告诉这个模块"现在是谁的会话"。只由 `stores/selection.js` 调用（§10.9 ① 之后视图不再直接认识它，
 * 而身份仍是从 `stores/auth.js` 那边发过来的）。
 * 拿到真实 uid 时顺手清掉旧全局键与 guest 槽：那些值是登录前/上一个账号留下的，
 * 谁都不该再读它们。一次性载荷同样在这一步被清掉。
 */
export function setSelectionOwner(userOrId = null) {
  const id = userOrId && typeof userOrId === 'object' ? userOrId.id : userOrId
  slot.uid = id || null
  if (slot.uid === null) return
  for (const field of FIELDS) {
    localStorage.removeItem(`${PREFIX}.${LABEL[field]}`)
    localStorage.removeItem(storageName(field, 'guest'))
  }
  localStorage.removeItem(`${PREFIX}.${PENDING}`)
  localStorage.removeItem(pendingName('guest'))
}
