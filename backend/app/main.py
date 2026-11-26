"""FastAPI 入口：聊天、SSE、文档知识库管理与 RAG 检索。"""
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from .config import (
    CORS_ORIGINS, MAX_HISTORY_MESSAGES, LLM_MODEL, LLM_PROVIDER, MAX_UPLOAD_MB,
)
from .database import connection, init_db, now_iso, row_to_dict
from .llm import LLMConfigError, LLMRequestError, create_answer, stream_answer
from .schemas import SendMessageRequest
from .rag import extract_text, ingest_document, retrieve, delete_document_vectors


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AI Chat + RAG Knowledge Base API",
    description="Vue + FastAPI + local Embedding + Chroma + Groq",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


def _load_conversation_history(conversation_id: int) -> list[dict[str, str]]:
    with connection() as conn:
        exists = conn.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="会话不存在或已被删除。")
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
            (conversation_id, MAX_HISTORY_MESSAGES),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def _decode_message(row):
    item = dict(row)
    try:
        item["sources"] = json.loads(item.pop("sources_json", "[]") or "[]")
    except (TypeError, ValueError):
        item["sources"] = []
    return item


def _save_exchange(conversation_id: int, content: str, answer: str, sources: list[dict] | None = None) -> dict[str, Any]:
    now = now_iso()
    sources_json = json.dumps(sources or [], ensure_ascii=False)
    with connection() as conn:
        user_cursor = conn.execute(
            "INSERT INTO messages(conversation_id, role, content, sources_json, created_at) VALUES (?, 'user', ?, '[]', ?)",
            (conversation_id, content, now),
        )
        assistant_cursor = conn.execute(
            "INSERT INTO messages(conversation_id, role, content, sources_json, created_at) VALUES (?, 'assistant', ?, ?, ?)",
            (conversation_id, answer, sources_json, now),
        )
        current = conn.execute("SELECT title FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="会话不存在或已被删除。")
        title = current["title"]
        if title == "新对话":
            title = content.replace("\n", " ").strip()
            if len(title) > 24:
                title = title[:24] + "…"
        conn.execute("UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?", (title, now, conversation_id))
        user_row = conn.execute("SELECT * FROM messages WHERE id = ?", (user_cursor.lastrowid,)).fetchone()
        assistant_row = conn.execute("SELECT * FROM messages WHERE id = ?", (assistant_cursor.lastrowid,)).fetchone()
        conversation_row = conn.execute("SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    return {
        "conversation": row_to_dict(conversation_row),
        "user_message": _decode_message(user_row),
        "assistant_message": _decode_message(assistant_row),
    }


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_rag_context(sources: list[dict]) -> str:
    if not sources:
        return "用户没有启用知识库，或知识库中没有检索到相关内容。请基于已有知识正常回答，不要伪造知识库引用。"
    blocks = []
    for index, source in enumerate(sources, start=1):
        blocks.append(f"[来源 {index}] 文件：{source['filename']}（片段 {source['chunk_index'] + 1}）\n{source['content']}")
    return (
        "你正在执行基于检索增强生成（RAG）的回答。优先依据以下知识库片段回答；若片段不足以回答，明确说明资料不足，不要编造。"
        "引用知识库内容时，在相关句子末尾使用 [来源 1]、[来源 2] 格式标注。回答末尾不要重复生成来源清单，前端会展示来源卡片。\n\n"
        + "\n\n".join(blocks)
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "provider": LLM_PROVIDER, "model": LLM_MODEL, "rag": "local-embedding+chroma"}


@app.get("/api/conversations")
def list_conversations():
    with connection() as conn:
        rows = conn.execute(
            """SELECT c.id, c.title, c.created_at, c.updated_at, COUNT(m.id) AS message_count
               FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id
               GROUP BY c.id ORDER BY c.updated_at DESC, c.id DESC"""
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/conversations")
def create_conversation():
    now = now_iso()
    with connection() as conn:
        cursor = conn.execute("INSERT INTO conversations(title, created_at, updated_at) VALUES (?, ?, ?)", ("新对话", now, now))
        row = conn.execute("SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row)


@app.get("/api/conversations/{conversation_id}/messages")
def get_messages(conversation_id: int):
    with connection() as conn:
        exists = conn.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="会话不存在或已被删除。")
        rows = conn.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC", (conversation_id,)).fetchall()
    return [_decode_message(row) for row in rows]


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: int):
    with connection() as conn:
        cursor = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="会话不存在或已被删除。")
    return {"deleted": True, "conversation_id": conversation_id}


@app.get("/api/knowledge/documents")
def list_knowledge_documents():
    with connection() as conn:
        rows = conn.execute("SELECT id, filename, file_type, chunk_count, created_at FROM knowledge_documents ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


@app.post("/api/knowledge/documents")
async def upload_knowledge_document(file: UploadFile = File(...)):
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="请选择有效文件。")
    data = await file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件不能超过 {MAX_UPLOAD_MB} MB。")
    try:
        text = extract_text(filename, data)
        doc_id = uuid.uuid4().hex
        chunk_count = await run_in_threadpool(ingest_document, doc_id, filename, text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"文档向量化失败：{type(exc).__name__}。请检查本地 Embedding 模型是否已成功下载。") from exc
    now = now_iso()
    with connection() as conn:
        conn.execute(
            "INSERT INTO knowledge_documents(id, filename, file_type, chunk_count, created_at) VALUES (?, ?, ?, ?, ?)",
            (doc_id, filename, Path(filename).suffix.lower(), chunk_count, now),
        )
    return {"id": doc_id, "filename": filename, "chunk_count": chunk_count, "created_at": now}


@app.delete("/api/knowledge/documents/{doc_id}")
async def delete_knowledge_document(doc_id: str):
    with connection() as conn:
        row = conn.execute("SELECT id FROM knowledge_documents WHERE id = ?", (doc_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="知识库文档不存在。")
    try:
        await run_in_threadpool(delete_document_vectors, doc_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="删除向量数据失败，请查看后端日志。") from exc
    with connection() as conn:
        conn.execute("DELETE FROM knowledge_documents WHERE id = ?", (doc_id,))
    return {"deleted": True, "id": doc_id}


async def _prepare_answer_context(content: str, use_knowledge_base: bool):
    if not use_knowledge_base:
        return [], ""
    try:
        sources = await run_in_threadpool(retrieve, content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"知识库检索失败：{type(exc).__name__}。请确认已上传文档且 Embedding 模型可用。") from exc
    return sources, _build_rag_context(sources)


@app.post("/api/conversations/{conversation_id}/messages")
async def send_message(conversation_id: int, body: SendMessageRequest):
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="消息内容不能为空。")
    history = _load_conversation_history(conversation_id)
    sources, context = await _prepare_answer_context(content, body.use_knowledge_base)
    try:
        answer = await create_answer(history, content, context)
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _save_exchange(conversation_id, content, answer, sources)


@app.post("/api/conversations/{conversation_id}/messages/stream")
async def send_message_stream(conversation_id: int, body: SendMessageRequest):
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="消息内容不能为空。")
    history = _load_conversation_history(conversation_id)
    sources, context = await _prepare_answer_context(content, body.use_knowledge_base)

    async def event_generator():
        chunks: list[str] = []
        try:
            if body.use_knowledge_base:
                yield _sse("sources", {"sources": [{k: v for k, v in item.items() if k != "content"} for item in sources]})
            async for piece in stream_answer(history, content, context):
                chunks.append(piece)
                yield _sse("delta", {"content": piece})
            answer = "".join(chunks).strip()
            if not answer:
                yield _sse("error", {"message": "模型返回内容为空，请稍后重试。"})
                return
            saved = _save_exchange(conversation_id, content, answer, sources)
            yield _sse("done", saved)
        except LLMConfigError as exc:
            yield _sse("error", {"message": str(exc)})
        except LLMRequestError as exc:
            yield _sse("error", {"message": str(exc)})
        except Exception:
            yield _sse("error", {"message": "流式生成过程中发生意外错误，请查看后端终端日志。"})

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no",
    })
