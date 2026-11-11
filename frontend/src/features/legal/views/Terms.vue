<template>
  <div class="legal-page">
    <article class="legal-card">
      <header class="legal-head">
        <p class="eyebrow">法律与说明</p>
        <h1>服务条款与隐私说明</h1>
        <p class="lead">
          这一页在登录前就能打开。注册页那颗勾选框指向这里——勾一个打不开的链接，比不勾更糟。
        </p>
      </header>

      <section>
        <h2>一、这个产品是什么</h2>
        <p>
          一个面向求职者的 AI 助手：解析简历、匹配岗位、模拟面试、给职业规划建议。
          它是工具，不是中介，也不代替你向任何公司投递。
        </p>
      </section>

      <section>
        <h2>二、AI 生成内容仅供参考</h2>
        <p>
          简历改写建议、匹配评分、面试评价与职业规划里的每一句，都是模型生成或按规则算出来的。
          <strong>它们可能出错，可能不准，可能需要你自己判断。</strong>
          我们不会把 AI
          的输出当成事实，也请你不要把它当成结论——尤其是薪资区间、岗位匹配度和面试结论。
        </p>
        <p>
          当模型服务不可用、或当前跑的是示例数据时，界面会明确标出来，而不是悄悄用一份假结果顶替。
        </p>
      </section>

      <section>
        <h2>三、我们存了你的什么</h2>
        <ul>
          <li><strong>账号</strong>：用户名、邮箱、密码的哈希（不是密码本身）。</li>
          <li><strong>简历与岗位</strong>：你上传的简历文件、粘贴的 JD，以及由此解析出的文本。</li>
          <li>
            <strong>使用痕迹</strong>：分析记录、投递记录、面试记录、模型调用日志（含耗时与 token
            数）。
          </li>
        </ul>
        <p>这些数据存在你自己的数据库里。这个项目不发遥测、不做用户画像、不把简历卖给任何人。</p>
      </section>

      <section>
        <h2>四、你的数据你自己处置</h2>
        <p>
          登录后可在<a class="link" @click.prevent="goPrivacy" href="/privacy">隐私与数据</a>页
          一键导出全部个人数据（JSON），或按类别删除简历、分析记录、面试记录，也可以直接注销账号——
          注销会永久删除账号与其全部数据，不可恢复。
        </p>
      </section>

      <section>
        <h2>五、请不要上传别人的隐私</h2>
        <p>
          简历里通常带着姓名、手机号、邮箱、住址。上传即表示你确认这些内容属于你本人、或你已获得授权。
        </p>
      </section>

      <section>
        <h2>六、变更</h2>
        <p>这一页随产品一起演进。条款若发生实质变化，会在你下次登录时提示重新确认。</p>
      </section>

      <footer class="legal-foot">
        <el-button plain @click="goBack">返 回</el-button>
        <el-button type="primary" @click="goRegister">去注册</el-button>
      </footer>
    </article>
  </div>
</template>

<script setup>
/* 公开的法律页：注册页的同意勾选指向这里，登录页页脚也指向这里。

   为什么不是复用 `/privacy`：那一页是"数据管理"（挂载即调鉴权接口、导出、分类删除、注销），
   登录前打不开也不该打开。把条款与隐私说明单独做成一个匿名可达的静态页，
   两件事就不必挤在同一页上互相将就。 */
import { useRouter } from 'vue-router'

const router = useRouter()

function goBack() {
  if (window.history.length > 1) {
    router.back()
    return
  }
  router.push('/login')
}

function goRegister() {
  router.push('/register')
}

function goPrivacy() {
  router.push('/privacy')
}
</script>

<style scoped>
/* 和登录前那几页同属 `:root` 浅色作用域。刻意零色值字面量：视图的色值预算是只能降不能升的。 */
.legal-page {
  min-height: 100vh;
  padding: 40px 16px 64px;
  background: var(--app-bg);
}

.legal-card {
  width: min(100%, 760px);
  margin: 0 auto;
  padding: 36px;
  background: var(--app-surface-strong);
  border: 1px solid var(--app-line);
  border-radius: 24px;
  box-shadow: 0 22px 60px var(--app-shadow);
}

.legal-head {
  padding-bottom: 20px;
  border-bottom: 1px solid var(--app-line);
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--app-muted);
}

h1 {
  margin: 0;
  font-size: 26px;
  color: var(--app-text);
}

.lead {
  margin: 12px 0 0;
  line-height: 1.8;
  color: var(--app-muted);
}

section {
  margin-top: 24px;
}

h2 {
  margin: 0 0 10px;
  font-size: 17px;
  color: var(--app-text);
}

p,
li {
  margin: 0 0 10px;
  line-height: 1.85;
  color: var(--app-muted);
}

ul {
  margin: 0 0 10px;
  padding-left: 20px;
}

strong {
  color: var(--app-text);
}

.link {
  color: var(--app-primary);
  cursor: pointer;
  text-decoration: underline;
}

.legal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 32px;
  padding-top: 20px;
  border-top: 1px solid var(--app-line);
}

@media (max-width: 640px) {
  .legal-card {
    padding: 24px 18px;
    border-radius: 20px;
  }

  .legal-foot {
    flex-direction: column-reverse;
  }

  .legal-foot :deep(.el-button) {
    width: 100%;
    margin-left: 0;
  }
}
</style>
