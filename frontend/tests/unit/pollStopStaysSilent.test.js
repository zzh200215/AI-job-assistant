import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'

/* D207 的前提之一是"这两个视图在轮询被卸载打断时不出声"：它们的外层 `catch` 是空的，
   所以 `polling_stopped` 那个 rejection 只会跑 `finally`，不会变成一句给人看的话。
   这句今天成立是**读代码**读来的（`AnalysisResult.vue:577`、`SmartAnalysis.vue:765`），
   而 D207 恰恰量到了反例——第三处运行链的 catch 有出口，出口挂在页面上那句 `ElMessage.error`。
   所以把"这两处静默"从一次阅读变成一条门：谁以后往这两个 catch 里加提示，加的那个人就
   会在候选人离开页面的下一屏上看到一句错。 */

const VIEWS = {
  'src/features/analysis/views/AnalysisResult.vue': 'AnalysisResult',
  'src/features/analysis/views/SmartAnalysis.vue': 'SmartAnalysis',
}

/**
 * 取"那一发轮询所属函数的外层 catch 体"。
 * 锚点是 `await pollAgentTask(`（这两个视图各只有一处，D207 现取全仓 3 处调用点），
 * 往后第一个 `} catch {` 到紧接着的 `} finally {` 之间就是 catch 体。
 * 取不到返回 null——**取不到要红**，不然重构一次就把守卫改成永久通过。
 */
function outerCatchBodyAfterPoll(source) {
  const match = source.match(/await pollAgentTask\([\s\S]*?\} catch \{([\s\S]*?)\} finally \{/)
  return match ? match[1] : null
}

describe('轮询被卸载打断时，这两个视图不出声', () => {
  for (const [rel, name] of Object.entries(VIEWS)) {
    it(`${name}：外层 catch 里没有一句要给人看的话`, () => {
      const body = outerCatchBodyAfterPoll(readFileSync(rel, 'utf8'))
      expect(
        body,
        '锚点失效：轮询调用点或外层 catch/finally 的形状变了，判据要跟着改'
      ).not.toBeNull()
      expect(
        body,
        `这个 catch 现在会出声了，而它出声的那一发正是"页面被卸载"：${body.trim()}`
      ).not.toMatch(/ElMessage|userErrorCopy/)
    })
  }

  it('反证：判据认得"往这个 catch 里加一句提示"这一改动', () => {
    const shaped = [
      '  try {',
      '    const res = await start(task_id)',
      '    await pollAgentTask(res.task_id, {',
      '      onFailed() { ElMessage.error("别的样子") },',
      '    })',
      '  } catch {',
      '    ElMessage.error(userErrorCopy(e, "任务已中断"))',
      '  } finally {',
      '    loading.value = false',
      '  }',
    ].join('\n')

    const body = outerCatchBodyAfterPoll(shaped)
    expect(body).not.toBeNull()
    // 只抓外层那一句：`onFailed` 里那句在 catch 之前，属于"任务真失败"，本来就该出声
    expect(body.trim()).toContain('任务已中断')
    expect(body).toMatch(/ElMessage|userErrorCopy/)
  })
})
