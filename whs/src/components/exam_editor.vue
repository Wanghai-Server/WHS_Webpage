<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import MarkdownIt from 'markdown-it'
import { Plus, Trash2, Save, Upload, Eye } from 'lucide-vue-next'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'

// 可复用组件：管理员在线编辑入服考试试卷（类似答题卡审阅的逐题编辑，支持新增/删除题目）
const { t, locale } = useI18n()
const { state: authState } = useAuth()
const { showTip } = useTips()

const loading = ref(true)
const saving = ref(false)
const form = ref(null) // { total_score, tips, tips_doc, questions: [...] }
const showTipsPreview = ref(false)

const QUESTION_TYPES = ['single_choice', 'multiple_choice', 'fill_blank', 'subjective']

// Markdown 渲染（试卷说明 tips 预览；html: false 防 XSS）
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
function renderTips(content) {
  return md.render(content || '')
}

// 附图上传：共享隐藏 file input，openUpload 记录目标对象（题目 / 选项 / tips），
// 上传成功后：题目与选项写入目标的 image 字段；tips 模式把 Markdown 图片语法追加到说明末尾。
const fileInputRef = ref(null)
const uploadTarget = ref(null)
const uploadingImg = ref(false)
const uploadingDoc = ref(false)

function openUpload(target) {
  if (uploadingImg.value || uploadingDoc.value) return
  uploadTarget.value = target
  fileInputRef.value?.click()
}

function openDocUpload() {
  if (uploadingImg.value || uploadingDoc.value) return
  docInputRef.value?.click()
}

async function onDocUploadFile(event) {
  const f = event.target.files && event.target.files[0]
  event.target.value = '' // 重置，允许重复选择同一文件
  if (!f) return
  uploadingDoc.value = true
  try {
    const fd = new FormData()
    fd.append('file', f)
    const res = await fetch('/api/admin/exam/doc', {
      method: 'POST',
      headers: authHeaders(),
      body: fd,
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      form.value.tips_doc = data.url
      showTip('info', t('admin.examConfigDocUploaded'))
    } else {
      showTip('error', localMessage(data))
    }
  } finally {
    uploadingDoc.value = false
  }
}

function clearDoc() {
  form.value.tips_doc = ''
}

// 从文档 URL 提取文件名用于展示
function docName(url) {
  if (!url) return ''
  const name = url.split('/').pop() || ''
  return name.startsWith('cfg_doc_') ? name.slice(8) : name
}

async function onUploadFile(event) {
  const f = event.target.files && event.target.files[0]
  event.target.value = '' // 重置，允许重复选择同一文件
  if (!f || !uploadTarget.value) return
  uploadingImg.value = true
  try {
    const fd = new FormData()
    fd.append('file', f)
    const res = await fetch('/api/admin/exam/image', {
      method: 'POST',
      headers: authHeaders(),
      body: fd,
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      if (uploadTarget.value.tips) {
        // 试卷说明：插入 Markdown 图片语法
        form.value.tips = `${form.value.tips || ''}\n![${t('admin.examConfigImage')}](${data.url})\n`
      } else if (uploadTarget.value.kind === 'questionImages') {
        // 题目多张附图：追加到 images 列表
        uploadTarget.value.question.images.push(data.url)
      } else {
        uploadTarget.value.image = data.url
      }
      showTip('info', t('admin.examConfigImageUploaded'))
    } else {
      showTip('error', localMessage(data))
    }
  } finally {
    uploadingImg.value = false
    uploadTarget.value = null
  }
}

function localMessage(data) {
  const m = data && data.message
  if (!m) return t('auth.request_failed')
  return m[locale.value] || m.zh || m.en || ''
}

function authHeaders(extra = {}) {
  return {
    ...(authState.token ? { Authorization: `Bearer ${authState.token}` } : {}),
    ...extra,
  }
}

// ---------- 数据转换 ----------
// 填空题编辑态：q.multiBlank 标记是否多项填空
//  - 单项：q.answer 为字符串数组（多个可接受答案匹配同一个空）
//  - 多项：q.answer 为字符串数组（每空一个字符串，可接受答案用逗号分隔）
function normalizeAnswer(q) {
  if (q.type === 'multiple_choice') return Array.isArray(q.answer) ? [...q.answer] : []
  if (q.type === 'fill_blank') {
    if (Array.isArray(q.answer) && Array.isArray(q.answer[0])) {
      // 多项填空（list of list）：每空的可接受答案用逗号连接展示
      return q.answer.map((blank) => blank.join(', '))
    }
    return Array.isArray(q.answer) ? [...q.answer] : []
  }
  return q.answer ?? ''
}

// 题目附图：统一为 images 列表（兼容旧的单个 image 字段）
function normalizeImages(q) {
  if (Array.isArray(q.images)) return q.images.map((x) => String(x || ''))
  return q.image ? [q.image] : []
}

function fromServer(cfg) {
  const questions = Object.entries(cfg.questions || {}).map(([id, q]) => ({
    id: Number(id),
    type: q.type,
    subject: q.subject || '',
    score: q.score ?? 0,
    images: normalizeImages(q),
    subjective: !!q.subjective,
    allow_upload: !!q.allow_upload,
    multiBlank: q.type === 'fill_blank' && Array.isArray(q.answer) && Array.isArray(q.answer[0]),
    options: q.options
      ? Object.entries(q.options).map(([key, opt]) => ({
          key,
          text: (opt && opt.text) || '',
          image: (opt && opt.image) || '',
        }))
      : [],
    answer: normalizeAnswer(q),
  }))
  questions.sort((a, b) => a.id - b.id)
  return { total_score: cfg.total_score ?? 0, tips: cfg.tips || '', tips_doc: cfg.tips_doc || '', questions }
}

// 选项 key 自动分配 a、b、c…（后端答案校验依赖这些 key）
function nextOptionKey(list) {
  for (let i = 0; i < 26; i++) {
    const key = String.fromCharCode(97 + i)
    if (!list.some((o) => o.key === key)) return key
  }
  return 'k' + Date.now() // 兜底
}

function newQuestion() {
  const maxId = form.value.questions.reduce((m, q) => Math.max(m, q.id), 0)
  return {
    id: maxId + 1,
    type: 'single_choice',
    subject: '',
    score: 0,
    images: [],
    subjective: false,
    allow_upload: false,
    multiBlank: false,
    options: [
      { key: 'a', text: '', image: '' },
      { key: 'b', text: '', image: '' },
    ],
    answer: '',
  }
}

function addQuestion() {
  form.value.questions.push(newQuestion())
}

function removeQuestion(q) {
  form.value.questions = form.value.questions.filter((x) => x.id !== q.id)
}

function addOption(q) {
  q.options.push({ key: nextOptionKey(q.options), text: '', image: '' })
}

function removeOption(q, opt) {
  q.options = q.options.filter((o) => o.key !== opt.key)
  if (q.type === 'single_choice' && q.answer === opt.key) q.answer = ''
  if (q.type === 'multiple_choice' && Array.isArray(q.answer)) {
    q.answer = q.answer.filter((k) => k !== opt.key)
  }
}

// 题目多张附图：添加 / 删除
function addImage(q) {
  if (!Array.isArray(q.images)) q.images = []
  q.images.push('')
}

function removeImage(q, i) {
  q.images.splice(i, 1)
}

// 主观题（题型为 subjective 或勾选"不计分"）恒 0 分，不允许设置分值
function isNotScored(q) {
  return q.type === 'subjective' || !!q.subjective
}

// 切换题型：重置选项与答案；切到主观题时分值归零（不计分）
function onTypeChange(q) {
  q.options = []
  q.answer = q.type === 'multiple_choice' || q.type === 'fill_blank' ? [] : ''
  q.multiBlank = false // 非填空题 / 新填空题默认单项
  if (q.type === 'single_choice') {
    q.options = [
      { key: 'a', text: '', image: '' },
      { key: 'b', text: '', image: '' },
    ]
  }
  if (q.type === 'subjective') {
    q.score = 0
    q.subjective = false // 主观题题型本身不计分，无需额外标记
  }
}

// 勾选"不计分"：分值归零（不参与判分）
function onSubjectiveChange(q) {
  if (q.subjective) q.score = 0
}

// 单项填空：多个可接受答案匹配同一个空
function addFillAnswer(q) {
  if (!Array.isArray(q.answer)) q.answer = []
  q.answer.push('')
}

function removeFillAnswer(q, i) {
  q.answer.splice(i, 1)
}

// 多项填空：每空一个字符串（可接受答案用逗号分隔）
function addBlank(q) {
  if (!Array.isArray(q.answer)) q.answer = []
  q.answer.push('')
}

function removeBlank(q, i) {
  q.answer.splice(i, 1)
}

// 填空题是否设置了至少一个可接受答案（未设置则不自动判分）
function hasFillAnswer(q) {
  if (!Array.isArray(q.answer)) return false
  if (q.multiBlank) {
    return q.answer.some((s) => String(s ?? '').trim())
  }
  return q.answer.some((a) => String(a ?? '').trim())
}

// 切换单项/多项填空（v-model 已更新 q.multiBlank，这里做答案结构转换）
function toggleMultiBlank(q) {
  if (q.multiBlank) {
    // 单项 -> 多项：原可接受答案并入第一空
    const first = (Array.isArray(q.answer) ? q.answer : [])
      .map((a) => String(a).trim())
      .filter(Boolean)
      .join(', ')
    q.answer = [first]
  } else {
    // 多项 -> 单项：所有空的可接受答案扁平合并
    const all = (Array.isArray(q.answer) ? q.answer : [])
      .flatMap((s) => String(s).split(/[,，]/).map((x) => x.trim()).filter(Boolean))
    q.answer = all
  }
}

// ---------- 保存（转换为后端结构） ----------
function toServer() {
  const questions = {}
  for (const q of form.value.questions) {
    const item = {
      type: q.type,
      subject: (q.subject || '').trim(),
      score: Number(q.score) || 0,
      subjective: !!q.subjective,
    }
    // 题目多张附图（过滤空项）
    const imgs = (Array.isArray(q.images) ? q.images : [])
      .map((x) => String(x).trim())
      .filter(Boolean)
    if (imgs.length) item.images = imgs
    if (q.type === 'single_choice' || q.type === 'multiple_choice') {
      const options = {}
      for (const o of q.options || []) {
        const text = (o.text || '').trim()
        const image = (o.image || '').trim()
        if (o.key && (text || image)) options[o.key] = { text, image }
      }
      item.options = options
      if (q.type === 'single_choice') {
        if (q.answer) item.answer = q.answer
      } else {
        const ans = (Array.isArray(q.answer) ? q.answer : []).filter(Boolean)
        if (ans.length) item.answer = ans
      }
    } else if (q.type === 'fill_blank') {
      if (q.multiBlank) {
        // 多项填空：每空一组可接受答案（按逗号分隔）
        const blanks = (Array.isArray(q.answer) ? q.answer : [])
          .map((s) => String(s).split(/[,，]/).map((x) => x.trim()).filter(Boolean))
          .filter((b) => b.length > 0)
        if (blanks.length) item.answer = blanks
      } else {
        // 单项填空：多个可接受答案匹配同一个空
        const ans = (Array.isArray(q.answer) ? q.answer : [])
          .map((a) => String(a).trim())
          .filter(Boolean)
        if (ans.length) item.answer = ans
      }
      if (q.allow_upload) item.allow_upload = true
    } else if (typeof q.answer === 'string' && q.answer.trim()) {
      item.answer = q.answer.trim()
    }
    questions[q.id] = item
  }
  return {
    total_score: Number(form.value.total_score) || 0,
    tips: form.value.tips || '',
    tips_doc: form.value.tips_doc || '',
    questions,
  }
}

async function save() {
  saving.value = true
  try {
    const res = await fetch('/api/admin/exam/config', {
      method: 'PUT',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(toServer()),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      showTip('info', t('admin.examConfigSaved'))
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    saving.value = false
  }
}

async function fetchConfig() {
  loading.value = true
  try {
    const res = await fetch('/api/admin/exam/config', { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      form.value = fromServer(data)
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchConfig)
</script>

<template>
  <div class="exam-editor">
    <div v-if="loading" class="editor-empty"><span class="spinner"></span>{{ t('admin.loading') }}</div>

    <template v-else-if="form">
      <!-- 顶部工具栏 -->
      <div class="editor-toolbar">
        <label class="total-label">
          {{ t('admin.examConfigTotal') }}
          <input v-model.number="form.total_score" type="number" min="0" class="total-input" />
        </label>
        <button type="button" class="tool-btn" @click="addQuestion">
          <Plus :size="16" /> {{ t('admin.examConfigAddQuestion') }}
        </button>
        <button type="button" class="tool-btn primary" :disabled="saving" @click="save">
          <span v-if="saving" class="spinner"></span>
          <Save v-else :size="16" /> {{ t('admin.examConfigSave') }}
        </button>
      </div>

      <!-- 试卷说明（tips）：Markdown 文本 + 图片上传，考生先阅读才能填个人信息 -->
      <div class="tips-card">
        <div class="tips-head">
          <span class="tips-title">{{ t('admin.examConfigTips') }}</span>
          <button type="button" class="mini-btn" :disabled="uploadingImg || uploadingDoc" @click="openUpload({ tips: true })">
            <span v-if="uploadingImg" class="spinner"></span>
            <Upload v-else :size="14" /> {{ t('admin.examConfigTipsUpload') }}
          </button>
          <button type="button" class="mini-btn" @click="showTipsPreview = !showTipsPreview">
            <Eye :size="14" /> {{ showTipsPreview ? t('admin.examConfigTipsHide') : t('admin.examConfigTipsPreview') }}
          </button>
        </div>
        <textarea
          v-model="form.tips"
          class="subject-input"
          rows="5"
          :placeholder="t('admin.examConfigTipsPlaceholder')"
        ></textarea>
        <div v-if="showTipsPreview" class="tips-preview" v-html="renderTips(form.tips)"></div>

        <!-- 试卷说明文档（仅 .docx，考生端以悬浮窗浏览） -->
        <div class="doc-row">
          <span class="doc-label">{{ t('admin.examConfigDoc') }}</span>
          <template v-if="form.tips_doc">
            <span class="doc-name">{{ docName(form.tips_doc) }}</span>
            <a class="mini-btn doc-open" :href="form.tips_doc" target="_blank" rel="noopener">
              {{ t('admin.examConfigDocOpen') }}
            </a>
            <button type="button" class="mini-btn" @click="clearDoc">
              <Trash2 :size="14" /> {{ t('admin.examConfigDocClear') }}
            </button>
          </template>
          <button v-else type="button" class="mini-btn" :disabled="uploadingImg || uploadingDoc" @click="openDocUpload">
            <span v-if="uploadingDoc" class="spinner"></span>
            <Upload v-else :size="14" /> {{ t('admin.examConfigDocUpload') }}
          </button>
        </div>
      </div>

      <!-- 题目卡片 -->
      <div v-for="(q, qi) in form.questions" :key="q.id" class="q-card">
        <div class="q-head">
          <span class="q-title">{{ t('admin.examConfigQuestion', { n: qi + 1, id: q.id }) }}</span>
          <select v-model="q.type" class="q-type" @change="onTypeChange(q)">
            <option v-for="tp in QUESTION_TYPES" :key="tp" :value="tp">{{ t('admin.examTypes.' + tp) }}</option>
          </select>
          <label class="q-score" :class="{ disabled: isNotScored(q) }">
            {{ t('admin.examConfigScore') }}
            <input
              v-model.number="q.score"
              type="number"
              min="0"
              class="score-input"
              :disabled="isNotScored(q)"
              :title="isNotScored(q) ? t('admin.examConfigScoreDisabled') : ''"
            />
          </label>
          <button
            type="button"
            class="del-btn"
            :title="t('admin.examConfigDeleteQuestion')"
            :aria-label="t('admin.examConfigDeleteQuestion')"
            @click="removeQuestion(q)"
          >
            <Trash2 :size="16" />
          </button>
        </div>

        <div class="q-body">
          <textarea
            v-model="q.subject"
            class="subject-input"
            rows="2"
            :placeholder="t('admin.examConfigSubject')"
          ></textarea>

          <!-- 题目附图（支持多张） -->
          <div class="field-row">
            <span class="img-label">{{ t('admin.examConfigImages') }}</span>
            <button type="button" class="mini-btn" :disabled="uploadingImg || uploadingDoc" @click="openUpload({ kind: 'questionImages', question: q })">
              <span v-if="uploadingImg" class="spinner"></span>
              <Upload v-else :size="14" /> {{ t('admin.examConfigImageUpload') }}
            </button>
            <button type="button" class="mini-btn" @click="addImage(q)">
              <Plus :size="14" /> {{ t('admin.examConfigAddImage') }}
            </button>
            <label class="inline-label">
              <input v-model="q.subjective" type="checkbox" @change="onSubjectiveChange(q)" /> {{ t('admin.examConfigSubjective') }}
            </label>
          </div>
          <div v-for="(img, ii) in q.images" :key="ii" class="opt-row">
            <input v-model="q.images[ii]" class="text-input grow" :placeholder="t('admin.examConfigImage')" />
            <button type="button" class="icon-btn" :aria-label="t('admin.examConfigDeleteImage')" @click="removeImage(q, ii)">
              <Trash2 :size="14" />
            </button>
          </div>

          <!-- 选择题：选项 + 标准答案 -->
          <template v-if="q.type === 'single_choice' || q.type === 'multiple_choice'">
            <div class="section-title">{{ t('admin.examConfigOptions') }}</div>
            <div v-for="opt in q.options" :key="opt.key" class="opt-row">
              <span class="opt-key">{{ opt.key }}.</span>
              <input v-model="opt.text" class="text-input grow" :placeholder="t('admin.examConfigOptionText')" />
              <input v-model="opt.image" class="text-input grow" :placeholder="t('admin.examConfigOptionImage')" />
              <button type="button" class="mini-btn" :disabled="uploadingImg || uploadingDoc" @click="openUpload(opt)">
                <span v-if="uploadingImg" class="spinner"></span>
                <Upload v-else :size="14" /> {{ t('admin.examConfigImageUpload') }}
              </button>
              <button type="button" class="icon-btn" :aria-label="t('admin.examConfigDeleteOption')" @click="removeOption(q, opt)">
                <Trash2 :size="14" />
              </button>
            </div>
            <button type="button" class="mini-btn" @click="addOption(q)">
              <Plus :size="14" /> {{ t('admin.examConfigAddOption') }}
            </button>

            <div class="section-title">{{ t('admin.examConfigAnswer') }}</div>
            <select v-if="q.type === 'single_choice'" v-model="q.answer" class="answer-select">
              <option value="">{{ t('admin.examConfigNone') }}</option>
              <option v-for="opt in q.options" :key="opt.key" :value="opt.key">
                {{ opt.key }}. {{ opt.text || opt.image || opt.key }}
              </option>
            </select>
            <div v-else class="answer-checks">
              <label v-for="opt in q.options" :key="opt.key" class="check-label">
                <input type="checkbox" :value="opt.key" v-model="q.answer" />
                {{ opt.key }}. {{ opt.text || opt.image || opt.key }}
              </label>
            </div>
          </template>

          <!-- 填空题：可接受答案 + 多项填空切换 + 上传开关 -->
          <template v-else-if="q.type === 'fill_blank'">
            <div class="section-title">
              {{ q.multiBlank ? t('admin.examConfigBlanks') : t('admin.examConfigFillAnswers') }}
              <label class="inline-label multi-toggle">
                <input v-model="q.multiBlank" type="checkbox" @change="toggleMultiBlank(q)" />
                {{ t('admin.examConfigFillMulti') }}
              </label>
            </div>

            <!-- 单项填空：多个可接受答案匹配同一个空 -->
            <template v-if="!q.multiBlank">
              <div v-for="(a, ai) in q.answer" :key="ai" class="opt-row">
                <input v-model="q.answer[ai]" class="text-input grow" :placeholder="t('admin.examConfigAnswerPlaceholder')" />
                <button type="button" class="icon-btn" :aria-label="t('admin.examConfigDeleteAnswer')" @click="removeFillAnswer(q, ai)">
                  <Trash2 :size="14" />
                </button>
              </div>
              <button type="button" class="mini-btn" @click="addFillAnswer(q)">
                <Plus :size="14" /> {{ t('admin.examConfigAddAnswer') }}
              </button>
            </template>

            <!-- 多项填空：每空一行（可接受答案用逗号分隔） -->
            <template v-else>
              <div v-for="(b, bi) in q.answer" :key="bi" class="opt-row">
                <span class="opt-key">{{ bi + 1 }}.</span>
                <input v-model="q.answer[bi]" class="text-input grow" :placeholder="t('admin.examConfigBlankPlaceholder')" />
                <button type="button" class="icon-btn" :aria-label="t('admin.examConfigDeleteBlank')" @click="removeBlank(q, bi)">
                  <Trash2 :size="14" />
                </button>
              </div>
              <button type="button" class="mini-btn" @click="addBlank(q)">
                <Plus :size="14" /> {{ t('admin.examConfigAddBlank') }}
              </button>
            </template>

            <label class="inline-label">
              <input v-model="q.allow_upload" type="checkbox" /> {{ t('admin.examConfigAllowUpload') }}
            </label>

            <!-- 未设置答案：本题不自动判分 -->
            <p v-if="!hasFillAnswer(q)" class="no-answer-hint">{{ t('admin.examConfigNoAnswerHint') }}</p>
          </template>

          <!-- 主观题：参考回答 -->
          <template v-else>
            <div class="section-title">{{ t('admin.examConfigAnswer') }}</div>
            <textarea
              v-model="q.answer"
              class="subject-input"
              rows="2"
              :placeholder="t('admin.examConfigAnswerPlaceholder')"
            ></textarea>
          </template>
        </div>
      </div>

      <!-- 底部操作 -->
      <div class="editor-toolbar bottom">
        <button type="button" class="tool-btn" @click="addQuestion">
          <Plus :size="16" /> {{ t('admin.examConfigAddQuestion') }}
        </button>
        <button type="button" class="tool-btn primary" :disabled="saving" @click="save">
          <span v-if="saving" class="spinner"></span>
          <Save v-else :size="16" /> {{ t('admin.examConfigSave') }}
        </button>
      </div>
    </template>

    <!-- 附图上传：隐藏文件选择器，由各"上传"按钮触发 -->
    <input
      ref="fileInputRef"
      type="file"
      accept="image/jpeg,image/png,image/webp,image/gif"
      hidden
      @change="onUploadFile"
    />
    <!-- 试卷文档上传（仅 .docx） -->
    <input
      ref="docInputRef"
      type="file"
      accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      hidden
      @change="onDocUploadFile"
    />
  </div>
</template>

<style scoped>
.exam-editor {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.editor-empty {
  padding: 60px 0;
  text-align: center;
  color: var(--links-color);
}

.editor-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.editor-toolbar.bottom {
  justify-content: center;
  padding-bottom: 8px;
}

.total-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--links-color);
}

.total-input {
  width: 70px;
  padding: 6px 8px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: var(--bg-color);
  color: var(--text-color);
  font: inherit;
}

.tool-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: transparent;
  color: var(--links-color);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.tool-btn:hover {
  color: var(--text-color);
  background: var(--btn-hover);
}

.tool-btn.primary {
  background: #ebaa28;
  border-color: transparent;
  color: #1f2937;
}

.tool-btn.primary:hover {
  background: #d99a1f;
}

.tool-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.mini-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 8px;
  border: 1px dashed rgba(148, 163, 184, 0.4);
  background: transparent;
  color: var(--links-color);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}

.mini-btn:hover {
  color: var(--text-color);
  border-color: var(--links-color);
}

.q-card {
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 14px;
  background: var(--card-color);
  overflow: hidden;
}

/* 试卷说明编辑卡片 */
.tips-card {
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 14px;
  background: var(--card-color);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tips-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.tips-title {
  font-weight: 700;
  font-size: 14px;
  color: var(--text-color);
}

.tips-preview {
  border-top: 1px dashed rgba(148, 163, 184, 0.35);
  padding-top: 10px;
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-color);
  word-break: break-word;
}

.tips-preview :deep(p) {
  margin: 0 0 10px;
}

.tips-preview :deep(h1),
.tips-preview :deep(h2),
.tips-preview :deep(h3) {
  margin: 12px 0 8px;
  color: var(--text-color);
}

.tips-preview :deep(ul),
.tips-preview :deep(ol) {
  margin: 0 0 10px;
  padding-left: 22px;
}

.tips-preview :deep(img) {
  max-width: 100%;
  border-radius: 8px;
  margin: 6px 0;
}

.tips-preview :deep(a) {
  color: var(--links-color);
}

.tips-preview :deep(code) {
  background: var(--btn-hover);
  padding: 2px 6px;
  border-radius: 6px;
  font-size: 13px;
}

.tips-preview :deep(pre) {
  background: var(--btn-hover);
  padding: 10px;
  border-radius: 8px;
  overflow-x: auto;
}

/* 试卷文档行 */
.doc-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  border-top: 1px dashed rgba(148, 163, 184, 0.35);
  padding-top: 10px;
}

.doc-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--links-color);
}

.doc-name {
  font-size: 13px;
  color: var(--text-color);
  word-break: break-all;
}

.doc-open {
  text-decoration: none;
}

.q-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--btn-hover);
  flex-wrap: wrap;
}

.q-title {
  font-weight: 700;
  font-size: 14px;
  color: var(--text-color);
}

.q-type {
  padding: 4px 8px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: var(--bg-color);
  color: var(--text-color);
  font: inherit;
  font-size: 13px;
}

.q-score {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--links-color);
}

.q-score.disabled {
  opacity: 0.5;
}

.score-input {
  width: 60px;
  padding: 4px 6px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: var(--bg-color);
  color: var(--text-color);
  font: inherit;
}

.score-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.del-btn {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #e5484d;
  cursor: pointer;
}

.del-btn:hover {
  background: rgba(229, 72, 77, 0.12);
}

.q-body {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.subject-input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: var(--bg-color);
  color: var(--text-color);
  font: inherit;
  font-size: 14px;
  resize: vertical;
}

.text-input {
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: var(--bg-color);
  color: var(--text-color);
  font: inherit;
  font-size: 13px;
}

.text-input.grow {
  flex: 1;
  min-width: 120px;
}

.field-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.inline-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  color: var(--links-color);
  white-space: nowrap;
}

.section-title {
  margin-top: 2px;
  font-size: 13px;
  font-weight: 700;
  color: var(--links-color);
}

.section-title .multi-toggle {
  margin-left: 10px;
  font-weight: 400;
}

.img-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--links-color);
}

.no-answer-hint {
  margin: 0;
  font-size: 12px;
  color: #e5a50a;
}

.opt-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.opt-key {
  width: 16px;
  font-weight: 700;
  font-size: 13px;
  color: var(--links-color);
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--links-color);
  cursor: pointer;
  flex-shrink: 0;
}

.icon-btn:hover {
  color: #e5484d;
  background: rgba(229, 72, 77, 0.1);
}

.answer-select {
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: var(--bg-color);
  color: var(--text-color);
  font: inherit;
  font-size: 13px;
}

.answer-checks {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.check-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-color);
}
</style>
