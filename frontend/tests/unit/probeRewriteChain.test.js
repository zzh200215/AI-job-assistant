import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

/* D158：`撤销这次应用` 这颗按钮在真浏览器里第一次被点起来。
   之前它只有 jsdom 的证据（`resumeRewriteUndo.test.js` 那 6 条），而探针没有这四条端点的夹具，
   所以"点了会怎样"这一屏从来没人看过。点完之后：撤销发出去的是 apply 刚回的那个
   `snapshot_version_id`（9001），第二次撤的是撤销自己留下的 `undo_version_id`（9002），
   被拒那一支说"整单撤销没有执行"并且不覆写分数行。

   这条守卫钉的是**让这件事下次还能做**：探针夹具是那条链唯一的屏幕入口，而后端或 api 层
   只要把 URL 改个名，适配器就静默回 `{}`——屏幕上表现为"按钮点下去没反应"，
   测试与门禁一个都不红。这是 D76 那族假阴性的仪器侧版本，所以两头都要钉：
   ① 链上四个端点每个都还得有夹具；② 每条夹具还得 declaring 视图真正 deref 的那些键
   （D157 刚踩过：缺 `weights_used` 不会报错，会把面板冻在上一帧）。 */

const probe = readFileSync('probe/dead-style.entry.js', 'utf8')
const apiResume = readFileSync('src/api/resume.js', 'utf8')
const view = readFileSync('src/features/resume/views/ResumeUpload.vue', 'utf8')

/* 端点尾段从 api 层现取，不在这里重抄一遍 URL（重抄就是第二个出处）。
   D200 之后改写那一发是**两条**同尾端点：POST `/resume/{id}/rewrite-suggestion-jobs`（建作业）
   与 GET `/resume/rewrite-suggestion-jobs/{job_id}`（取结果），所以两种 URL 写法都要认。 */
const TAILS = ['diagnose', 'rewrite-suggestion-jobs', 'apply-rewrites', 'revert-rewrite']
const apiDeclaredTails = () => {
  const set = new Set()
  for (const m of apiResume.matchAll(
    /request\.(?:get|post|put|delete)\(\s*[`'"]\/resume\/\$\{[^}]+\}\/([a-z-]+)/g
  )) {
    set.add(m[1])
  }
  for (const m of apiResume.matchAll(/request\.(?:get|post)\(\s*[`'"]\/resume\/([a-z-]+)\/\$\{/g)) {
    set.add(m[1])
  }
  return set
}

/* 夹具表里每一条的正则源文与方法。表里有两种写法：`[/re/, 'get', {...}]` 一行式，
   以及函数夹具那种 `[\n  /re/,\n  'post',\n  (body) => …\n  ],` 多行式——**两种都要认**。
   第一版只认一行式，结果那四条写操作的夹具在守卫眼里根本不存在：守卫自己先假阴性了一次，
   这正是 D76 那一族的仪器侧版本，所以这里把两种写法都钉住并留一条反证。 */
const entriesFrom = (text) => [
  ...[...text.matchAll(/\[\s*\/(.+?)\/,\s*'(get|post|put|delete)'/g)].map((m) => ({
    pattern: m[1],
    method: m[2],
    at: m.index,
  })),
]
const fixtureFor = (tail, entries = entriesFrom(probe), method = 'post') =>
  entries.find((e) => e.method === method && e.pattern.includes(tail))

/* 该夹具那条表项的源码块：从它的 `[` 起到下一个只缩进两格的 `],` 收尾。 */
const blockIn = (text, tail, method = 'post', entries = entriesFrom(text)) => {
  const entry = fixtureFor(tail, entries, method)
  if (!entry) return null
  const rest = text.slice(entry.at)
  const end = rest.indexOf('\n  ],')
  return end < 0 ? null : rest.slice(0, end)
}
const blockFor = (tail, method = 'post') => blockIn(probe, tail, method)

/* 视图在写操作上 deref 的键，从函数体现取，并**按兜底形态分两类**：
   · `data?.k`（没有兜底）与 `data?.k || []`（空数组兜底）都算必读——后者缺键的表现正是
     "列表安静地空掉"，屏幕上什么都不说（D157 那条 `.mb` 就是这么长期量不到的）；
   · `data?.k || '一段文案'`（空串兜底）不算——那只是缺省措辞，缺了不会少画东西。
   这条分界线是有意划的：把带文案兜底的键也算进来，守卫会因为一堆无关缺省而常红，
   最后被人放宽成"全都跳过"，那还不如不写。 */
const derefedKeys = (fnName) => {
  const start = view.indexOf(`async function ${fnName}(`)
  if (start < 0) throw new Error(`视图里找不到 ${fnName}（改名了要跟着改这条守卫）`)
  const body = view.slice(start, view.indexOf('\n}', start))
  const required = new Set()
  const textFallback = new Set()
  for (const m of body.matchAll(/(?:data|job)\??\.([a-z_]+)/g)) {
    const after = body.slice(m.index + m[0].length).replace(/^\s+/, '')
    const fb = /^(?:\?\?|\|\|)\s*/.exec(after)
    const tail = fb ? after.slice(fb[0].length) : after
    /* 兜底给的是**一段文案**⇒ 缺键只让措辞变通用，屏幕上不少东西 ⇒ 不要求夹具声明它。
       其余形态（`|| []`、`?? null`、根本没有兜底）⇒ 缺键就是少画一整块 ⇒ 必须声明。 */
    if (fb && /^['"`]/.test(tail)) textFallback.add(m[1])
    else required.add(m[1])
  }
  return { required: [...required], textFallback: [...textFallback] }
}

describe('改写 → 应用 → 撤销那条链的屏幕入口', () => {
  it('keeps a probe fixture for every endpoint of the rewrite/undo chain', () => {
    const declared = apiDeclaredTails()
    for (const tail of TAILS) {
      expect([...declared], `api 层不再打 /resume/{id}/${tail}：这条守卫要跟着改`).toContain(tail)
      expect(
        fixtureFor(tail),
        `/resume/{id}/${tail} 没有夹具了——探针会把这条打成 \`{}\`，屏幕上只剩"点了没反应"，而门禁不会红`
      ).toBeTruthy()
    }
    /* 反证：从**副本**里去掉 revert 那一条，覆盖判断必须掉下来（说明这条腿真在读表，不是在背数）。
       删法用"把带这个尾段的那一行整行抹掉"——不依赖跨行正则的写法细节，删没删掉由下一行判断。 */
    const stripped = probe
      .split('\n')
      .filter((line) => !line.includes('revert-rewrite$/'))
      .join('\n')
    expect(stripped, '撤销那条夹具没真的被移出副本（锚点漂了）').not.toBe(probe)
    const entries = entriesFrom(stripped)
    expect(
      fixtureFor('revert-rewrite', entries),
      '撤掉 revert 夹具之后这条守卫还认得出缺条目，说明它没有在空转'
    ).toBeFalsy()
    /* 另外三条不能跟着一起掉——不然"掉下来"这件事没有区分力。 */
    for (const tail of ['diagnose', 'rewrite-suggestion-jobs', 'apply-rewrites']) {
      expect(fixtureFor(tail, entries), `副本里不该一起丢 ${tail}`).toBeTruthy()
    }
    /* 反向的下限：表里那四条确实各占一条，不是一条例式覆盖四家。 */
    expect(TAILS.filter((t) => fixtureFor(t)).length, '四条端点各要有一条 POST 夹具').toBe(
      TAILS.length
    )
  })

  it('keeps the undo-chain fixtures declaring every key the view dereferences', () => {
    const pairs = [
      // 作业链上"视图取值"发生在**轮询那一条**（GET），建作业那条只回 job_id。
      ['rewrite-suggestion-jobs', 'generateRewrites', 'get'],
      ['apply-rewrites', 'applyRewrites', 'post'],
      ['revert-rewrite', 'revertRewrite', 'post'],
    ]
    for (const [tail, fnName, method] of pairs) {
      const { required, textFallback } = derefedKeys(fnName)
      expect(
        required.length,
        `${fnName} 里没有一条 data?.x / job?.x 的取值？守卫要看的东西变了`
      ).toBeGreaterThan(0)
      const block = blockFor(tail, method)
      expect(block, `读不到 ${tail} 那条夹具的块（写法变了，或方法认错了）`).not.toBeNull()
      const missing = required.filter((k) => !new RegExp(`(^|[{,\\s])${k}\\s*:`).test(block))
      expect(
        missing,
        `${tail} 的夹具少了视图会读的键：${missing.join(', ')}（缺键不会报错，只会静默少画）`
      ).toEqual([])
      /* 分类本身也要自检：`note` 是空串兜底的那一个，它必须落在 skipped 里而不是 required 里，
         否则这条判据退化成"全都算必读"，下一轮就有人把它整条放宽。 */
      if (tail === 'rewrite-suggestion-jobs') {
        expect(textFallback, '`note` 的分类不再是"空串兜底"了（判据要重新看）').toContain('note')
        expect(required).not.toContain('note')
      }
    }
    /* 分数那一行不吃 `data?.score`，它吃 `score.before.score` / `score.after.score`（:659-664），
       所以单独钉：两条写操作的夹具都得带 before + after。 */
    for (const tail of ['apply-rewrites', 'revert-rewrite']) {
      const block = blockFor(tail)
      expect(block, `读不到 ${tail} 夹具`).not.toBeNull()
      expect(block).toMatch(/before\s*:/)
      expect(block).toMatch(/after\s*:/)
    }
    /* 反证：把 success 那一支的 `undo_version_id` 从副本里抹掉，上面那把尺必须报缺键。 */
    const block = blockFor('revert-rewrite')
    const stripped = block.replace(/undo_version_id\s*:/, '被抹掉的键:')
    expect(stripped, '这条反证没真的落进副本').not.toBe(block)
    expect(
      derefedKeys('revertRewrite').required.filter(
        (k) => !new RegExp(`(^|[{,\\s])${k}\\s*:`).test(stripped)
      ),
      '抹掉键之后要能报出来'
    ).toEqual(['undo_version_id'])
  })

  it('keeps the rejection branch of the undo call shape-complete', () => {
    /* 被拒那一支是这条链上唯一"不能吃掉候选人后写文字"的路径（后端 resume.py:1075），
       也是夹具里最容易漏的一支：它的形状与 success 完全不同（没有 restored_blocks，
       多一个 stale_blocks[].kind，而界面取的是 **kind** 不是 block_id）。 */
    const block = blockFor('revert-rewrite')
    expect(block, '读不到 revert 那条夹具').not.toBeNull()
    expect(block, '被拒那一支没了').toContain('__revertStale')
    expect(block).toMatch(/changed:\s*false/)
    expect(block).toMatch(/stale_blocks\s*:/)
    const kinds = [...block.matchAll(/kind:\s*'([a-z_]+)'/g)].map((m) => m[1])
    expect(
      kinds.length,
      'stale_blocks 要带 kind：界面文案读的是 kind 标签，不是 block_id'
    ).toBeGreaterThanOrEqual(2)
    /* kind 必须落在视图那张标签表里（:650），否则屏幕上会出现裸英文。 */
    const labelStart = view.indexOf('function rewriteKindLabel(')
    const labelBlock = view.slice(labelStart, view.indexOf('\n}', labelStart))
    const orphan = kinds.filter((k) => !labelBlock.includes(`${k}:`))
    expect(
      orphan,
      `stale_blocks 里有 kind 不在 rewriteKindLabel 的表里：${orphan.join(', ')}`
    ).toEqual([])
  })
})
