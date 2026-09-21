/**
 * 日期的四个出口，取代此前散在 14 个文件里的 15 份副本。
 *
 * 收敛前实测（同一批输入跑出来的真实输出）：
 *  - `toLocaleDateString` 带上 hour/minute 与 `toLocaleString` 带同样的选项**逐字节相同**
 *    （Interview 与 PipelineKanban 各写了一份，其实是同一个格式）；
 *  - `toLocaleString('zh-CN')` 与 `toLocaleString('zh-CN', { hour12: false })` 也相同
 *    （中文默认就是 24 小时制），但 Profile 那份写的是**不带 locale** 的
 *    `toLocaleString()` —— 同一条时间戳在英文浏览器上会变成 `9/21/2026, 6:30:05 PM`，
 *    而全站其他地方仍是中文格式。这里统一钉住 zh-CN。
 *  - 所有 `new Date(x).toLocaleXxx()` 对坏值都返回字符串 `Invalid Date`，**从不抛异常**，
 *    所以副本里那些 `catch { return d }` 是死代码，注释写的"保留后端返回的原始时间"
 *    其实从未发生。这里把它变成真的：坏值原样返回，只有空值才用占位符。
 */

const LOCALE = 'zh-CN'

/**
 * 空值走占位符，坏值保留原文（比 `Invalid Date` 有信息量）。
 * 用 falsy 判空与迁移前的 15 份副本一致——`new Date(null)` 是 1970 年，
 * 不在前面挡住就会把"没有日期"渲染成"1月1日"。
 */
function render(value, empty, format) {
  if (!value) return empty
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return format(date)
}

/** `9月21日` */
export function monthDay(value, empty = '') {
  return render(value, empty, (date) =>
    date.toLocaleDateString(LOCALE, { month: 'short', day: 'numeric' })
  )
}

/** `9月21日 18:05` */
export function monthDayTime(value, empty = '') {
  return render(value, empty, (date) =>
    date.toLocaleString(LOCALE, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  )
}

/** `2026/9/21 18:05:00`，固定中文与 24 小时制，不随浏览器语言变。 */
export function dateTime(value, empty = '') {
  return render(value, empty, (date) => date.toLocaleString(LOCALE, { hour12: false }))
}

/** `09/21 08:05`——窄列里用的紧凑写法（投递漏斗弹窗），与 monthDayTime 是两种排版。 */
export function compactDateTime(value, empty = '') {
  return render(value, empty, (date) =>
    date.toLocaleString(LOCALE, {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  )
}

/**
 * `2026-09-21` 这样的后端日期串直接切出 `09-21`，用于图表横轴。
 * 与上面几个的区别：它**不构造 Date**，所以不做时区换算——轴标签就该是后端给的那天。
 * 非字符串（含 null）返回占位符，这与迁移前 `typeof !== 'string'` 的判断一致。
 */
export function isoMonthDay(value, empty = '--') {
  return !value || typeof value !== 'string' ? empty : value.slice(5)
}

/**
 * 不做本地化的服务端时间戳：直接切字符串，看到的仍然是后端存的那个时刻，
 * 不会因为浏览器时区而位移。两个出口对应报告页与提示词追踪页各自的截法。
 */
function serverStamp(value, { utc = false, length = 19, empty = '' } = {}) {
  if (!value) return empty
  const text = String(value).replace('T', ' ')
  return (utc ? text.replace('+00:00', ' UTC') : text).slice(0, length)
}

/** `2026-09-21 18:05:00.123456 UTC`——评估报告页用它，缺值显示 `-`。 */
export function utcStamp(value, empty = '-') {
  return serverStamp(value, { utc: true, length: 23, empty })
}

/** `2026-09-21 18:05:00`——Prompt 追踪页用它，不带 UTC 标记。 */
export function rawStamp(value, empty = '-') {
  return serverStamp(value, { length: 19, empty })
}
