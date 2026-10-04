/* AI 输出的分数字段怎么读——§10.20（D113）拍定的那一刀。
   `career_planning` 是 `chat_json` 的原始返回（backend/app/agents/career_agent.py:55），
   分数字段没有任何 schema 约束：模型可以写 "约80"、写 true、漏写字段。旧实现 `safeScore`
   把这些一律夹成 0，于是屏幕出现"0 分提升空间"、雷达那个角塌到圆心——那是把"这条我没读懂"
   讲成"你这项能力是 0"。现在读不懂就返回 null，由每一屏自己说"暂无数据"，并且不进雷达与提升空间。
   0 是**合法分数**，和"读不懂"不是同一个值。
   与 `scoreTone.js` 的分工：那里管档位与颜色（不夹取，84.6 就是 84.6），这里管"能不能读成一个
   要拿去算宽度/半径的数"，所以夹 0-100 并四舍五入是这里的活。 */

/** 读不懂 → null；读得懂 → 夹在 0-100 的整数。 */
export function readScore(value) {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'boolean') return null
  const number = Number(value)
  if (!Number.isFinite(number)) return null
  return Math.max(0, Math.min(100, Math.round(number)))
}

/** 提升空间：任一端读不懂就是"不知道"，不是 0。 */
export function scoreGap(current, target) {
  const from = readScore(current)
  const to = readScore(target)
  if (from === null || to === null) return null
  return to - from
}

/** 这一对分数能不能进雷达、能不能参与提升空间。 */
export function scorePairReadable(current, target) {
  return scoreGap(current, target) !== null
}

/** 屏幕上"这一项的分数没读懂"要说的那句话的唯一出处，两屏都得是同一句（§10.21 的教训）。 */
export const SCORE_UNREADABLE_TEXT = '暂无数据'
