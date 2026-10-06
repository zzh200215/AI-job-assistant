import { defineStore } from 'pinia'
import {
  forgetJD as eraseJD,
  readDefaultResumeId,
  readJDId,
  readRecordId,
  readResumeId,
  rememberDefaultResume as storeDefaultResume,
  rememberJD as storeJD,
  rememberPendingAnalysis as storePending,
  rememberRecord as storeRecord,
  rememberResume as storeResume,
  setSelectionOwner,
  takePendingAnalysis as takePending,
} from '@/utils/lastSelection'

/**
 * 跨页"上一次选择"（简历 / JD / 分析记录 / 默认版本）的**唯一入口**——§10.9 决定 ①，D124。
 *
 * 键名、按登录用户分槽、未登录落 `guest`、登录时清 guest 槽与旧的全局键——**这些规则仍然只住在
 * `utils/lastSelection` 里**，这个 store 不复制一份真相。它换掉的是"谁来调它们"：以前 11 个文件
 * 各自 import 五个具名函数（27 个调用点），`stores/auth.js` 还要单独认识 `setSelectionOwner`；
 * 现在视图只引这一个 store，身份通知成了它的内部动作。
 *
 * **读取是方法、不是 computed**，这一点刻意：computed 会缓存，而 localStorage 可能被另一个标签页
 * 或另一个账号写过。"这一页 `onMounted` 读到的就是此刻的值"是今天的行为，收成 store 不该顺手把它
 * 换成"本会话第一次读到的值"。真要反应式状态，得先把跨标签页那条路补上，而不是先造一套会过期的缓存。
 */
export const useSelectionStore = defineStore('selection', () => ({
  /** 此刻这一格存的是什么；没有就是 null。每次调用都落到存储。 */
  resumeId: () => readResumeId(),
  jdId: () => readJDId(),
  recordId: () => readRecordId(),
  defaultResumeId: () => readDefaultResumeId(),
  rememberResume(id) {
    storeResume(id)
  },
  rememberJD(id) {
    storeJD(id)
  },
  forgetJD() {
    eraseJD()
  },
  rememberRecord(id) {
    storeRecord(id)
  },
  rememberDefaultResume(id) {
    storeDefaultResume(id)
  },
  /** `JobSearch` → `SmartAnalysis` 的那一坨一次性表单预填（形状没统一，只统一了槽位）。 */
  rememberPendingAnalysis(payload) {
    storePending(payload)
  },
  /** 取走 = 读到什么就删掉什么，所以这个名字刻意带 take：第二次调用必然拿到 null。 */
  takePendingAnalysis() {
    return takePending()
  },
  /** 只由 `stores/auth.js` 调用：身份一变槽就跟着变，guest 槽与旧全局键在这一步被清掉。 */
  setOwner(userOrId) {
    setSelectionOwner(userOrId ?? null)
  },
}))
