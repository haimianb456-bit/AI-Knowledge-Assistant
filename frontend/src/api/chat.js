import axios from 'axios'

// 前端只请求自己的 FastAPI 服务，不直接暴露或调用模型供应商 API Key。
const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api',
  timeout: 100000,
  // 不要在实例级别固定 Content-Type：上传 FormData 时浏览器必须自动补 multipart boundary。
  // 普通 JSON 请求由 Axios 根据请求体自动设置 application/json。
})

export function getHealth() {
  return http.get('/health')
}

export function getConversations() {
  return http.get('/conversations')
}

export function createConversation() {
  return http.post('/conversations')
}

export function getMessages(conversationId) {
  return http.get(`/conversations/${conversationId}/messages`)
}

export function sendMessage(conversationId, content, useKnowledgeBase = false) {
  return http.post(`/conversations/${conversationId}/messages`, { content, use_knowledge_base: useKnowledgeBase })
}

export function getKnowledgeDocuments() {
  return http.get('/knowledge/documents')
}

export function uploadKnowledgeDocument(file) {
  const form = new FormData()
  form.append('file', file)
  return http.post('/knowledge/documents', form, { timeout: 180000 })
}

export function deleteKnowledgeDocument(id) {
  return http.delete(`/knowledge/documents/${id}`)
}

export function removeConversation(conversationId) {
  return http.delete(`/conversations/${conversationId}`)
}

export function getErrorMessage(error) {
  return error?.response?.data?.detail || error?.message || '请求失败，请检查服务是否启动。'
}

/** 使用 Fetch + ReadableStream 消费 FastAPI 返回的 SSE 事件。 */
export async function streamMessage(conversationId, content, { signal, onDelta, useKnowledgeBase = false, onSources } = {}) {
  const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'
  const response = await fetch(`${baseURL}/conversations/${conversationId}/messages/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ content, use_knowledge_base: useKnowledgeBase }),
    signal,
  })

  if (!response.ok) {
    let detail = `请求失败（HTTP ${response.status}）`
    try {
      const body = await response.json()
      detail = body?.detail || detail
    } catch { /* 忽略非 JSON 错误响应 */ }
    throw new Error(detail)
  }
  if (!response.body) throw new Error('浏览器不支持读取流式响应，请更换现代浏览器。')

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let completed = null

  const handleEvent = (rawEvent) => {
    if (!rawEvent.trim()) return
    let eventName = 'message'
    const dataLines = []
    for (const line of rawEvent.split(/\r?\n/)) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    }
    if (!dataLines.length) return
    const payload = JSON.parse(dataLines.join('\n'))
    if (eventName === 'delta') onDelta?.(payload.content || '')
    if (eventName === 'sources') onSources?.(payload.sources || [])
    if (eventName === 'done') completed = payload
    if (eventName === 'error') throw new Error(payload.message || '模型生成失败。')
  }

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split(/\r?\n\r?\n/)
      buffer = events.pop() || ''
      for (const eventText of events) handleEvent(eventText)
    }
    buffer += decoder.decode()
    if (buffer.trim()) handleEvent(buffer)
  } finally {
    reader.releaseLock()
  }

  if (!completed) throw new Error('连接已结束，但没有收到完整回答记录。')
  return { data: completed }
}
