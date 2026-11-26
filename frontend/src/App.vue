<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
import {
  createConversation,
  getConversations,
  getErrorMessage,
  getHealth,
  getMessages,
  removeConversation,
  streamMessage,
  getKnowledgeDocuments,
  uploadKnowledgeDocument,
  deleteKnowledgeDocument,
} from './api/chat'

const conversations = ref([])
const messages = ref([])
const selectedId = ref(null)
const draft = ref('')
const loading = ref(false)
const sending = ref(false)
const apiStatus = ref('checking')
const providerName = ref('模型服务')
const modelName = ref('')
const errorText = ref('')
const messageList = ref(null)
const inputBox = ref(null)
const streamController = ref(null)
const knowledgeEnabled = ref(false)
const knowledgePanelOpen = ref(false)
const knowledgeDocuments = ref([])
const uploading = ref(false)
const uploadInput = ref(null)

const selectedConversation = computed(() =>
  conversations.value.find((item) => item.id === selectedId.value) || null,
)
const hasMessages = computed(() => messages.value.length > 0)

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  typographer: false,
})

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char])
}

markdown.renderer.rules.fence = (tokens, index) => {
  const token = tokens[index]
  const rawLanguage = token.info.trim().split(/\s+/g)[0] || 'text'
  const language = /^[\w+-]+$/.test(rawLanguage) ? rawLanguage : 'text'
  const source = token.content
  let highlighted
  if (language !== 'text' && hljs.getLanguage(language)) {
    highlighted = hljs.highlight(source, { language }).value
  } else {
    highlighted = escapeHtml(source)
  }
  return `<div class="code-block"><div class="code-block-toolbar"><span>${escapeHtml(language)}</span><button type="button" class="copy-code-button" data-copy-code>复制代码</button></div><pre><code class="hljs language-${escapeHtml(language)}">${highlighted}</code></pre></div>`
}

function renderMarkdown(content) {
  return DOMPurify.sanitize(markdown.render(content || ''), {
    USE_PROFILES: { html: true },
    ADD_ATTR: ['data-copy-code'],
  })
}

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

function scrollToBottom() {
  nextTick(() => {
    if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
  })
}

async function handleMessageClick(event) {
  const button = event.target.closest('[data-copy-code]')
  if (!button) return
  const code = button.closest('.code-block')?.querySelector('pre code')?.innerText
  if (!code) return
  try {
    await navigator.clipboard.writeText(code)
    button.textContent = '已复制'
    window.setTimeout(() => { button.textContent = '复制代码' }, 1500)
  } catch {
    errorText.value = '复制失败，请手动选择代码复制。'
  }
}

async function checkBackend() {
  try {
    const { data } = await getHealth()
    providerName.value = data?.provider || '模型服务'
    modelName.value = data?.model || ''
    apiStatus.value = 'online'
  } catch {
    apiStatus.value = 'offline'
  }
}

async function refreshConversations() {
  const { data } = await getConversations()
  conversations.value = data
}

async function refreshKnowledgeDocuments() {
  const { data } = await getKnowledgeDocuments()
  knowledgeDocuments.value = data
}

async function handleKnowledgeUpload(event) {
  const file = event.target.files?.[0]
  if (!file) return
  uploading.value = true
  errorText.value = ''
  try {
    const { data } = await uploadKnowledgeDocument(file)
    await refreshKnowledgeDocuments()
    errorText.value = `已加入知识库：${data.filename}，切分为 ${data.chunk_count} 个文本片段。`
  } catch (error) {
    errorText.value = getErrorMessage(error)
  } finally {
    uploading.value = false
    event.target.value = ''
  }
}

async function removeKnowledgeDocument(item) {
  if (!window.confirm(`确定从知识库删除「${item.filename}」吗？`)) return
  try {
    await deleteKnowledgeDocument(item.id)
    await refreshKnowledgeDocuments()
  } catch (error) { errorText.value = getErrorMessage(error) }
}

async function openConversation(id) {
  if (sending.value) return
  selectedId.value = id
  localStorage.setItem('ai-chat-selected-id', String(id))
  loading.value = true
  errorText.value = ''
  try {
    const { data } = await getMessages(id)
    messages.value = data
    scrollToBottom()
  } catch (error) {
    errorText.value = getErrorMessage(error)
  } finally {
    loading.value = false
  }
}

async function startNewConversation() {
  if (sending.value) return
  errorText.value = ''
  try {
    const { data } = await createConversation()
    conversations.value.unshift({ ...data, message_count: 0 })
    selectedId.value = data.id
    messages.value = []
    localStorage.setItem('ai-chat-selected-id', String(data.id))
    nextTick(() => inputBox.value?.focus())
  } catch (error) {
    errorText.value = getErrorMessage(error)
  }
}

async function deleteConversation(item, event) {
  event?.stopPropagation()
  if (sending.value) return
  const confirmed = window.confirm(`确定删除「${item.title}」及其聊天记录吗？`)
  if (!confirmed) return
  try {
    await removeConversation(item.id)
    conversations.value = conversations.value.filter((row) => row.id !== item.id)
    if (selectedId.value === item.id) {
      selectedId.value = null
      messages.value = []
      localStorage.removeItem('ai-chat-selected-id')
      if (conversations.value.length > 0) await openConversation(conversations.value[0].id)
    }
  } catch (error) {
    errorText.value = getErrorMessage(error)
  }
}

async function submitMessage() {
  const content = draft.value.trim()
  if (!content || sending.value) return
  if (apiStatus.value !== 'online') {
    errorText.value = '当前无法连接后端服务，请先启动 FastAPI。'
    return
  }

  sending.value = true
  errorText.value = ''
  draft.value = ''
  const userTempId = `temp-user-${Date.now()}`
  const assistantTempId = `temp-assistant-${Date.now()}`
  let wasAborted = false

  try {
    if (!selectedId.value) {
      const { data } = await createConversation()
      selectedId.value = data.id
      conversations.value.unshift({ ...data, message_count: 0 })
      localStorage.setItem('ai-chat-selected-id', String(data.id))
    }

    messages.value.push(
      { id: userTempId, role: 'user', content, created_at: new Date().toISOString() },
      { id: assistantTempId, role: 'assistant', content: '', created_at: new Date().toISOString() },
    )
    scrollToBottom()

    streamController.value = new AbortController()
    const { data } = await streamMessage(selectedId.value, content, {
      signal: streamController.value.signal,
      useKnowledgeBase: knowledgeEnabled.value,
      onSources: (sources) => {
        const target = messages.value.find((item) => item.id === assistantTempId)
        if (target) target.sources = sources
      },
      onDelta: (piece) => {
        const target = messages.value.find((item) => item.id === assistantTempId)
        if (target) target.content += piece
        scrollToBottom()
      },
    })

    messages.value = messages.value.filter(
      (item) => item.id !== userTempId && item.id !== assistantTempId,
    )
    messages.value.push(data.user_message, data.assistant_message)
    await refreshConversations()
    scrollToBottom()
  } catch (error) {
    wasAborted = error?.name === 'AbortError'
    if (!wasAborted) {
      messages.value = messages.value.filter(
        (item) => item.id !== userTempId && item.id !== assistantTempId,
      )
      draft.value = content
      errorText.value = getErrorMessage(error)
    } else {
      errorText.value = '已停止生成。未完成的回答不会保存到聊天记录。'
    }
  } finally {
    streamController.value = null
    sending.value = false
    if (wasAborted && selectedId.value) {
      try {
        const { data } = await getMessages(selectedId.value)
        messages.value = data
        await refreshConversations()
      } catch { /* 保留当前界面，不覆盖停止提示 */ }
    }
    scrollToBottom()
    nextTick(() => inputBox.value?.focus())
  }
}

function stopGeneration() {
  streamController.value?.abort()
}

function handleKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submitMessage()
  }
}

onMounted(async () => {
  await checkBackend()
  if (apiStatus.value !== 'online') return
  try {
    await refreshConversations()
    await refreshKnowledgeDocuments()
    const rememberedId = Number(localStorage.getItem('ai-chat-selected-id'))
    const target = conversations.value.find((item) => item.id === rememberedId)
      || conversations.value[0]
    if (target) await openConversation(target.id)
  } catch (error) {
    errorText.value = getErrorMessage(error)
  }
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand-row">
        <div class="brand-mark">AI</div>
        <div>
          <div class="brand-title">AI 对话助手</div>
          <div class="brand-subtitle">Vue · FastAPI · {{ providerName }}</div>
        </div>
      </div>

      <button class="new-chat-button" :disabled="sending" @click="startNewConversation">
        <span class="plus-icon">＋</span><span>新建对话</span>
      </button>

      <div class="section-label">最近对话</div>
      <div class="conversation-list">
        <button
          v-for="item in conversations" :key="item.id" class="conversation-item"
          :class="{ active: selectedId === item.id }" :disabled="sending"
          @click="openConversation(item.id)"
        >
          <span class="conversation-icon">▤</span>
          <span class="conversation-title">{{ item.title || '新对话' }}</span>
          <span class="delete-conversation" title="删除会话" @click="deleteConversation(item, $event)">×</span>
        </button>
        <div v-if="conversations.length === 0" class="empty-history">暂无对话记录</div>
      </div>

      <div class="sidebar-footer">
        <span class="status-dot" :class="apiStatus"></span>
        <span>{{ apiStatus === 'online' ? '后端服务已连接' : apiStatus === 'checking' ? '正在连接服务…' : '后端服务未连接' }}</span>
      </div>
    </aside>

    <main class="main-panel">
      <header class="topbar">
        <div class="topbar-left">
          <div class="page-title">{{ selectedConversation?.title || '新对话' }}</div>
          <div class="page-caption">让想法快速变成答案</div>
        </div>
        <div class="topbar-actions">
          <button class="knowledge-open-button" @click="knowledgePanelOpen = true">知识库管理 <span>{{ knowledgeDocuments.length }}</span></button>
          <div class="model-chip"><span class="model-dot"></span> {{ providerName }} · {{ apiStatus === 'online' ? '后端已连接' : '等待后端' }}</div>
        </div>
      </header>

      <section ref="messageList" class="message-area">
        <div v-if="!hasMessages && !loading" class="welcome-state">
          <div class="welcome-orb">✦</div>
          <h1>你好，今天想聊点什么？</h1>
          <p>可以提问、梳理思路，或让 AI 帮你解释代码和技术概念。</p>
          <div class="suggestion-grid">
            <button class="suggestion-card" @click="draft = '请用初学者能理解的方式解释 FastAPI 的工作原理。'; inputBox?.focus()">
              <span class="suggestion-icon blue">⌘</span><span><b>学习新技术</b><small>解释 FastAPI 的工作原理</small></span>
            </button>
            <button class="suggestion-card" @click="draft = '请帮我设计一个适合初学者的 Python 后端学习计划。'; inputBox?.focus()">
              <span class="suggestion-icon purple">↗</span><span><b>制定学习计划</b><small>规划 Python 后端学习路径</small></span>
            </button>
            <button class="suggestion-card" @click="draft = '请帮我分析一个 Vue 页面如何通过 Axios 调用 FastAPI 接口。'; inputBox?.focus()">
              <span class="suggestion-icon amber">◇</span><span><b>理解项目代码</b><small>Vue 如何调用 FastAPI 接口</small></span>
            </button>
          </div>
        </div>

        <div v-else class="message-list" @click="handleMessageClick">
          <article v-for="message in messages" :key="message.id" class="message-row" :class="message.role">
            <div class="avatar" :class="message.role">{{ message.role === 'user' ? '我' : 'AI' }}</div>
            <div class="message-content-wrap">
              <div class="message-meta">
                <b>{{ message.role === 'user' ? '你' : providerName }}</b>
                <time>{{ formatTime(message.created_at) }}</time>
                <span v-if="message.id === messages[messages.length - 1]?.id && sending" class="streaming-label">正在生成</span>
              </div>
              <div v-if="message.role === 'user'" class="message-content user-content">{{ message.content }}</div>
              <div v-else class="message-content markdown-body" v-html="renderMarkdown(message.content || (sending ? '▍' : ''))"></div>
              <div v-if="message.role === 'assistant' && message.sources?.length" class="source-list">
                <div class="source-heading">参考来源</div>
                <div v-for="(source, index) in message.sources" :key="`${source.filename}-${source.chunk_index}-${index}`" class="source-chip">
                  <span class="source-index">[{{ index + 1 }}]</span> {{ source.filename }} <small>片段 {{ source.chunk_index + 1 }}</small>
                </div>
              </div>
            </div>
          </article>
        </div>
        <div v-if="loading" class="loading-history">正在加载对话记录…</div>
      </section>

      <div class="composer-area">
        <div v-if="errorText" class="error-banner">
          <span>⚠</span><span>{{ errorText }}</span><button @click="errorText = ''">关闭</button>
        </div>
        <div class="composer-box">
          <textarea
            ref="inputBox" v-model="draft" :disabled="sending || apiStatus !== 'online'"
            rows="1" maxlength="8000" placeholder="输入你的问题…（Enter 发送，Shift + Enter 换行）"
            @keydown="handleKeydown"
          ></textarea>
          <div class="composer-bottom">
            <label class="rag-toggle"><input v-model="knowledgeEnabled" type="checkbox" :disabled="knowledgeDocuments.length === 0"> 使用知识库检索 <span v-if="knowledgeDocuments.length">{{ knowledgeDocuments.length }} 份资料</span><span v-else>请先上传资料</span></label>
            <div class="send-actions">
              <span class="char-count">{{ draft.length }}/8000</span>
              <button v-if="sending" class="stop-button" @click="stopGeneration">停止生成</button>
              <button v-else class="send-button" :disabled="!draft.trim() || apiStatus !== 'online'" @click="submitMessage">发送 ↗</button>
            </div>
          </div>
        </div>
        <div class="footer-note">由 {{ providerName }} 模型服务提供能力 · 支持 RAG 检索、来源引用与 Markdown · 对话记录保存在本地 SQLite 数据库</div>
      </div>
    </main>

    <div v-if="knowledgePanelOpen" class="modal-backdrop" @click.self="knowledgePanelOpen = false">
      <section class="knowledge-panel">
        <header class="knowledge-header"><div><h2>知识库管理</h2><p>上传资料后，系统会在本地完成文本切分、Embedding 和 Chroma 向量存储。</p></div><button class="panel-close" @click="knowledgePanelOpen = false">×</button></header>
        <div class="knowledge-upload" @click="uploadInput?.click()">
          <input ref="uploadInput" type="file" accept=".md,.markdown,.txt,.pdf,.docx,.csv,.json,.py,.js,.ts,.html,.css" hidden @change="handleKnowledgeUpload">
          <strong>{{ uploading ? '正在解析并向量化…' : '＋ 上传知识文档' }}</strong>
          <span>支持 Markdown、TXT、PDF、DOCX 等格式，单文件最大 15 MB</span>
        </div>
        <div class="knowledge-summary">已入库 {{ knowledgeDocuments.length }} 份文档</div>
        <div v-if="knowledgeDocuments.length" class="knowledge-doc-list">
          <div v-for="doc in knowledgeDocuments" :key="doc.id" class="knowledge-doc">
            <div class="doc-icon">MD</div><div class="doc-info"><b>{{ doc.filename }}</b><small>{{ doc.chunk_count }} 个文本片段 · {{ formatTime(doc.created_at) }}</small></div>
            <button class="doc-delete" title="删除文档" @click="removeKnowledgeDocument(doc)">删除</button>
          </div>
        </div>
        <div v-else class="knowledge-empty">还没有知识文档。上传一份 Markdown 或 PDF，开始构建你的本地知识库。</div>
        <div class="knowledge-note">Embedding 模型：sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2（本地 CPU）<br>向量数据库：Chroma PersistentClient<br>文档内容保存在本机 backend/data 目录。</div>
      </section>
    </div>
  </div>
</template>
