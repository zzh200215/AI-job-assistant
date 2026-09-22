/**
 * 「只让最后一次发起的请求写结果」。
 *
 * 轮询、筛选切换、翻页都能在同一时刻叠出两个在途请求；`await` 之后直接写 ref 的话，
 * **后完成的那次赢**，而不是后发起的那次赢。慢接口 + 10 秒轮询就会让用户看到上一轮
 * 的数据，筛选点了「进行中」却仍然显示全部结果。
 *
 * 用法：`const isCurrent = latestCall()` 在发起前拿令牌，回来后用
 * `if (!isCurrent()) return` 放弃写入。
 */
export function useLatestCall() {
  let seq = 0
  return function latestCall() {
    const id = ++seq
    return () => id === seq
  }
}
