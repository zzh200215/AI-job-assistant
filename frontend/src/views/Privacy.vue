<template>
  <div class="page-shell">
    <div class="page-header">
      <div>
        <h2>隐私与数据</h2>
        <div class="page-header-sub">了解我们如何收集、使用和保护您的数据</div>
      </div>
    </div>

    <section v-if="dataSummary" class="data-summary" aria-label="个人数据概览">
      <div v-for="item in summaryItems" :key="item.key" class="summary-item">
        <strong>{{ item.value }}</strong>
        <span>{{ item.label }}</span>
      </div>
    </section>

    <!-- 拉不到就整块消失，等于对用户说"我们没有你的数据"：这块是合规面，必须显式失败 -->
    <AppLoadError
      v-else-if="summaryError"
      title="个人数据概览加载失败"
      :message="summaryError"
      @retry="loadDataSummary"
    />

    <div class="panel">
      <div class="panel-header"><h3>数据管理</h3></div>
      <div class="panel-body">
        <div class="data-actions">
          <div class="data-action-row">
            <div>
              <strong>导出我的数据</strong>
              <p>下载您的所有数据，包括简历、投递记录、面试报告、分析结果</p>
            </div>
            <el-button @click="exportData" :loading="exporting">导出</el-button>
          </div>
          <div class="data-action-row">
            <div>
              <strong>删除简历</strong>
              <p>删除所有已上传的简历文件及其解析结果</p>
            </div>
            <el-button type="danger" plain @click="deleteResumes">删除简历</el-button>
          </div>
          <div class="data-action-row">
            <div>
              <strong>删除分析记录</strong>
              <p>删除所有简历分析、匹配分析、面试报告等生成记录</p>
            </div>
            <el-button type="danger" plain @click="deleteAnalyses">删除分析记录</el-button>
          </div>
          <div class="data-action-row">
            <div>
              <strong>删除面试记录</strong>
              <p>删除所有模拟面试的对话记录和评分结果</p>
            </div>
            <el-button type="danger" plain @click="deleteInterviews">删除面试记录</el-button>
          </div>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header"><h3>隐私政策</h3></div>
      <div class="panel-body">
        <div class="privacy-content">
          <section>
            <h4>1. 收集的信息</h4>
            <p>我们收集以下类型的信息以提供求职服务：</p>
            <ul>
              <li><b>账号信息：</b>用户名、邮箱地址（用于登录和通知）</li>
              <li>
                <b>简历内容：</b
                >您上传的简历文件及其解析结果（姓名、联系方式、教育经历、工作经历、技能等）
              </li>
              <li><b>求职偏好：</b>期望岗位、薪资、城市、行业等偏好设置</li>
              <li><b>面试记录：</b>模拟面试中的问答对话、评分结果、AI 分析报告</li>
              <li><b>使用数据：</b>功能使用频率、页面访问路径、操作行为（用于优化产品）</li>
            </ul>
          </section>

          <section>
            <h4>2. 数据使用目的</h4>
            <ul>
              <li>提供简历解析、岗位匹配、模拟面试等核心功能</li>
              <li>生成个性化职业规划建议和 Offer 决策分析</li>
              <li>改进 AI 模型的准确性和服务质量</li>
              <li>发送求职进度提醒和产品更新通知</li>
            </ul>
          </section>

          <section>
            <h4>3. 数据存储与保留</h4>
            <ul>
              <li>数据存储在中国境内的安全服务器上</li>
              <li>账号活跃期间持续保留您的数据</li>
              <li>账号注销后 30 天内彻底删除所有关联数据</li>
              <li>匿名化统计数据可保留用于产品分析</li>
            </ul>
          </section>

          <section>
            <h4>4. 数据共享</h4>
            <p>我们不会将您的个人数据出售给第三方。在以下情况下可能共享：</p>
            <ul>
              <li>您主动通过分享链接分享简历给招聘方</li>
              <li>法律要求或保护合法权益需要</li>
              <li>经您明确同意的其他情况</li>
            </ul>
          </section>

          <section>
            <h4>5. 您的权利</h4>
            <ul>
              <li><b>访问权：</b>随时查看您的个人数据</li>
              <li><b>更正权：</b>修改不准确的个人信息</li>
              <li><b>删除权：</b>删除特定数据或注销整个账号</li>
              <li><b>导出权：</b>下载您的数据副本</li>
              <li><b>撤回同意：</b>随时关闭通知或数据收集</li>
            </ul>
          </section>

          <section>
            <h4>6. 安全措施</h4>
            <ul>
              <li>传输加密：所有 API 请求使用 HTTPS</li>
              <li>存储加密：密码使用 bcrypt 哈希存储</li>
              <li>访问控制：严格的身份验证和权限管理</li>
              <li>定期审计：代码安全审查和依赖更新</li>
            </ul>
          </section>

          <section>
            <h4>7. 联系我们</h4>
            <p>如对隐私政策有任何疑问，或需要行使您的数据权利，请通过以下方式联系我们：</p>
            <p>邮箱：privacy@career-signal.ai</p>
          </section>

          <p class="privacy-date">最后更新：2025 年 7 月</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from '@/plugins/element-services'
import request from '@/api/request'
import AppLoadError from '@/components/ui/AppLoadError.vue'

const exporting = ref(false)
const dataSummary = ref(null)
const summaryError = ref('')

const summaryItems = computed(() => [
  { key: 'resumes', label: '简历', value: dataSummary.value?.resumes || 0 },
  { key: 'versions', label: '版本', value: dataSummary.value?.resume_versions || 0 },
  { key: 'analyses', label: '分析', value: dataSummary.value?.analyses || 0 },
  { key: 'interviews', label: '面试', value: dataSummary.value?.interviews || 0 },
  { key: 'applications', label: '投递', value: dataSummary.value?.applications || 0 },
])

onMounted(loadDataSummary)

async function loadDataSummary() {
  summaryError.value = ''
  try {
    dataSummary.value = await request.get('/auth/data-summary')
  } catch (e) {
    dataSummary.value = null
    summaryError.value = e?.userMessage || e?.message || '未能获取你的数据概览'
  }
}

async function exportData() {
  exporting.value = true
  try {
    const res = await request.get('/auth/export-data', { responseType: 'blob' })
    const url = window.URL.createObjectURL(res)
    const a = document.createElement('a')
    a.href = url
    a.download = `my_data_${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('数据导出成功')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

async function deleteResumes() {
  try {
    await ElMessageBox.confirm(
      '将删除所有简历文件及其解析结果，此操作不可恢复。确定继续？',
      '删除简历',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
    )
    await request.delete('/auth/data/resumes')
    ElMessage.success('简历已删除')
    loadDataSummary()
  } catch (error) {
    notifyDeleteFailure(error, '删除简历')
  }
}

async function deleteAnalyses() {
  try {
    await ElMessageBox.confirm(
      '将删除所有分析记录和报告，此操作不可恢复。确定继续？',
      '删除分析记录',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
    )
    await request.delete('/auth/data/analyses')
    ElMessage.success('分析记录已删除')
    loadDataSummary()
  } catch (error) {
    notifyDeleteFailure(error, '删除分析记录')
  }
}

async function deleteInterviews() {
  try {
    await ElMessageBox.confirm(
      '将删除所有面试记录和评分结果，此操作不可恢复。确定继续？',
      '删除面试记录',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
    )
    await request.delete('/auth/data/interviews')
    ElMessage.success('面试记录已删除')
    loadDataSummary()
  } catch (error) {
    notifyDeleteFailure(error, '删除面试记录')
  }
}

function notifyDeleteFailure(error, action) {
  if (error === 'cancel' || error === 'close') return
  ElMessage.error(`${action}失败，请稍后重试`)
}
</script>

<style scoped>
.page-shell {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 18px 0;
}
.panel {
  border-radius: 16px;
  border: 1px solid var(--app-line);
  background: var(--app-surface-strong);
  box-shadow: var(--app-shadow-soft);
}
.data-summary {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  border: 1px solid var(--app-line);
  border-radius: 8px;
  background: var(--app-surface-strong);
}
.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 16px;
  border-right: 1px solid var(--app-line);
}
.summary-item:last-child {
  border-right: 0;
}
.summary-item strong {
  color: var(--app-primary);
  font-size: 22px;
}
.summary-item span {
  color: var(--app-muted);
  font-size: 12px;
}
.panel-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--app-line);
}
.panel-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}
.panel-body {
  padding: 20px;
}

.data-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.data-action-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px;
  border-radius: 10px;
  background: var(--app-bg);
  border: 1px solid var(--app-line);
}
.data-action-row strong {
  display: block;
  font-size: 14px;
  font-weight: 600;
}
.data-action-row p {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--app-muted);
}

.privacy-content section {
  margin-bottom: 24px;
}
.privacy-content h4 {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 700;
  color: var(--app-text);
}
.privacy-content p {
  margin: 0 0 8px;
  font-size: 14px;
  line-height: 1.7;
  color: var(--app-muted);
}
.privacy-content ul {
  margin: 0;
  padding-left: 18px;
}
.privacy-content li {
  margin-bottom: 6px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--app-muted);
}
.privacy-date {
  margin-top: 16px;
  font-size: 12px;
  color: var(--app-muted);
  text-align: center;
}
@media (max-width: 680px) {
  .data-summary {
    grid-template-columns: repeat(2, 1fr);
  }
  .summary-item:nth-child(2n) {
    border-right: 0;
  }
}
</style>
