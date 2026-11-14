<template>
  <div class="eng-body">
    <el-card shadow="never" class="panel-card">
      <template #header><span>一句话</span></template>
      <p class="eng-intro">
        D1–D11 分两半：前五轮把"能演"做实（一条主链从空库走到结果），后六轮把"说的每句话站得住"做实
        ——失败会说清原因、排队会被看见、没人用的东西被删掉。
      </p>
    </el-card>

    <el-card shadow="never" class="panel-card">
      <template #header><span>四把尺（当前读数）</span></template>
      <ul class="eng-rulers">
        <li v-for="ruler in rulers" :key="ruler.name">
          <b>{{ ruler.name }}</b>
          <span>{{ ruler.value }}</span>
          <span class="eng-cmd">{{ ruler.command }}</span>
        </li>
      </ul>
    </el-card>

    <el-card shadow="never" class="panel-card">
      <template #header><span>十一轮：之前 / 现在</span></template>
      <div v-for="round in rounds" :key="round.id" class="eng-round">
        <h4>{{ round.id }}</h4>
        <p><span class="eng-label">之前</span>{{ round.before }}</p>
        <p><span class="eng-label">现在</span>{{ round.after }}</p>
      </div>
    </el-card>

    <el-card shadow="never" class="panel-card">
      <template #header><span>还差什么</span></template>
      <ul class="eng-gaps">
        <li v-for="gap in gaps" :key="gap">{{ gap }}</li>
      </ul>
      <p class="eng-source">
        完整版在仓库 <span class="eng-cmd">docs/交付摘要.md</span>；逐条证据与在册限制在
        <span class="eng-cmd">docs/delivery-index.md</span>；判据与变异证据在
        <span class="eng-cmd">docs/engineering-quality.md</span>。
      </p>
    </el-card>
  </div>
</template>

<script setup>
/* 工程口径的那一页。内容与 `docs/交付摘要.md` 是**同一件事的两处写法**：
   文档给仓库读者，这里给只有浏览器的人。数字必须一致——`tests/deliveryNumbersAgree.test.mjs`
   会把这份组件与文档对齐着比，谁改了另一边没跟就红。 */
const rulers = [
  {
    name: '后端测试',
    value: '1593 passed / 0 failed',
    command: 'cd backend && python -m pytest -q',
  },
  {
    name: '前端测试',
    value: '127 文件 / 814 条',
    command: 'cd frontend && npx vitest run',
  },
  {
    name: '静态守卫',
    value: '57 条（首屏字节、类型预算、元素注册、样式债棘轮…）',
    command: 'cd frontend && node --test tests/*.test.mjs',
  },
  {
    name: '格式门',
    value: 'eslint 0 error / 0 warning；prettier 与 ruff format 486 文件全绿',
    command: 'npm run lint && npm run format:check',
  },
  {
    name: '首屏',
    value: '406 kB gzip（天花板 420，其中 245 kB 是 Element Plus）',
    command: 'tests/bundleBudget.test.mjs 跑真构建量的',
  },
]

const rounds = [
  {
    id: 'D1',
    before:
      '改密码不校验旧密码；验证邮件与忘记口令会 500；重置口令一步就能改；侧栏挂着走不通的入口。',
    after: '改密要旧密码；重置拆成"发信 → 凭 token 设新密"两步；两个入口出树。',
  },
  {
    id: 'D2',
    before: '空库进去什么都没有，演示要手工灌数据；两个 seed 入口各写一份清单。',
    after: '空库点一次 → 1 个目标 + 1 份简历 + 5 个岗位 + 5 条投递；两个入口归一。',
  },
  {
    id: 'D3',
    before: '失败和"没有数据"在屏幕上是同一句话；四个入口点了没反应。',
    after: '六处内联错误 + 重试；"失败 ≠ 空"；运行时两条提示（示例数据 / AI 降级）。',
  },
  {
    id: 'D4',
    before: '看板只能拖（手机上等于不能推进）；阶段状态机只活在后端。',
    after: '卡片菜单也能推进，与拖拽发同一个请求；11 页 × 3 档手机宽度实测无溢出。',
  },
  {
    id: 'D5',
    before: '六个组件族能渲染但裸奔（样式表从没被导入过），而所有门都是绿的。',
    after: '补齐样式表，判据从"只查多余"改成双向；首屏钉了 420 kB 天花板。',
  },
  {
    id: 'D6',
    before: '分析接口回 200 就"已启动"，任务在队列里躺了 733 秒没人跑，屏幕上只有一个转圈。',
    after:
      '没有消费者就 503 拒绝接单；worker_alive 变成可观测量；从没开始的任务两分钟内收口并写清原因。',
  },
  {
    id: 'D7',
    before: '一次性三步的旧分析接口：第 3 步失败整发 500、前两步白跑，而前端从未调用它。',
    after: '整条出树；分析记录只剩一个写入方，并由一条判据钉住。',
  },
  {
    id: 'D8',
    before: '前端 API 层有 16 个写完没人用的封装，其中一个指向不存在的路由。',
    after: '清零；并立一条按引用图判的守卫（注释里提到不算用过）。',
  },
  {
    id: 'D9',
    before: '任务"已提交但没开始跑"和"跑了但卡住"长得一样：一个不动的 0%。',
    after: '多了一个"排队中"态，四类屏说同一句话；"没开始就失败"由前端自己说，不搬服务端原文。',
  },
  {
    id: 'D10',
    before: '分析结果页失败只弹 5 秒 toast；任务中心排队与卡住画同一条 0%。',
    after: '失败留在页面上（带重试）；任务中心排队不画进度条。',
  },
  {
    id: 'D11',
    before: '三份报告作业（简历 / 项目 / 作品集）排队时也说"正在逐节生成"。',
    after: '排队就说排队，被领走之后才说逐节生成。',
  },
]

const gaps = [
  '真 provider 今天跑不通：主模型 429、embedding 账号欠费，所以推荐分数来自规则臂，不是模型。配额恢复后一条命令重跑，在那之前任何"推荐质量"的结论都不成立。',
  'ORCHESTRATION_BACKEND=redis_queue 时必须另起编排 worker；不起它，分析接口会直接 503（这是故意的，比回一个没人跑的任务号诚实）。升级时先升 worker 再升 web。',
  '投递看板的终态（已入职 / 已拒绝 / 已放弃）没有出口，误点只能删除重建——后端状态机里这三个是空集，加"撤销"是领域决定，不是代码债。',
]
</script>

<style scoped>
.eng-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.eng-intro {
  margin: 0;
  line-height: 1.9;
}

.eng-rulers,
.eng-gaps {
  margin: 0;
  padding-left: 18px;
  line-height: 2;
}

.eng-rulers b {
  margin-right: 8px;
}

.eng-cmd {
  display: inline-block;
  margin-left: 8px;
  padding: 0 6px;
  border-radius: 4px;
  background: var(--app-surface-muted);
  color: var(--app-muted);
  font-size: 12px;
}

.eng-round + .eng-round {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--app-line);
}

.eng-round h4 {
  margin: 0 0 4px;
  font-size: 14px;
}

.eng-round p {
  margin: 2px 0;
  line-height: 1.8;
}

.eng-label {
  display: inline-block;
  width: 44px;
  color: var(--app-muted);
}

.eng-source {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--app-muted);
  line-height: 1.9;
}
</style>
