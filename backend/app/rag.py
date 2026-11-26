"""本地 RAG：FastEmbed 多语言本地 Embedding + Chroma 持久化向量库。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config import CHROMA_PATH, EMBEDDING_MODEL, RAG_TOP_K, RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP

_client = None
_collection = None
_embedder = None


def _resources():
    global _client, _collection, _embedder
    if _client is None:
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("缺少 chromadb，请在 backend 虚拟环境执行 pip install -r requirements.txt。") from exc
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        _collection = _client.get_or_create_collection(
            name="knowledge_documents",
            metadata={"hnsw:space": "cosine"},
        )
    if _embedder is None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError("缺少 fastembed，请在 backend 虚拟环境执行 pip install -r requirements.txt。") from exc
        try:
            _embedder = TextEmbedding(model_name=EMBEDDING_MODEL)
        except ValueError as exc:
            supported = TextEmbedding.list_supported_models()
            names = [item.get("model") for item in supported if isinstance(item, dict)]
            raise RuntimeError(
                f"Embedding 模型配置不受当前 FastEmbed 支持：{EMBEDDING_MODEL}。"
                f"请使用受支持模型，例如 sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2。"
            ) from exc
    return _collection, _embedder


def split_text(text: str) -> list[str]:
    text = re.sub(r"\r\n?", "\n", text).strip()
    if not text:
        return []
    # 优先按 Markdown 标题/段落边界切分，再按字符窗口控制块长度。
    paragraphs = re.split(r"\n(?=#{1,6}\s)|\n\s*\n", text)
    units: list[str] = []
    current = ""
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(current) + len(paragraph) + 2 <= RAG_CHUNK_SIZE:
            current = f"{current}\n\n{paragraph}".strip()
        else:
            if current:
                units.append(current)
            while len(paragraph) > RAG_CHUNK_SIZE:
                units.append(paragraph[:RAG_CHUNK_SIZE])
                paragraph = paragraph[max(1, RAG_CHUNK_SIZE - RAG_CHUNK_OVERLAP):]
            current = paragraph
    if current:
        units.append(current)
    chunks: list[str] = []
    for i, unit in enumerate(units):
        if i and RAG_CHUNK_OVERLAP:
            overlap = units[i - 1][-RAG_CHUNK_OVERLAP:]
            chunks.append((overlap + "\n" + unit).strip())
        else:
            chunks.append(unit)
    return chunks


def ingest_document(doc_id: str, filename: str, text: str) -> int:
    chunks = split_text(text)
    if not chunks:
        raise ValueError("文件没有可用于建立知识库的文本内容。")
    collection, model = _resources()
    vectors = [vector.tolist() for vector in model.embed(chunks)]
    ids = [f"{doc_id}-{i}" for i in range(len(chunks))]
    metadatas = [{"doc_id": doc_id, "filename": filename, "chunk_index": i} for i in range(len(chunks))]
    collection.add(ids=ids, documents=chunks, embeddings=vectors, metadatas=metadatas)
    return len(chunks)


def delete_document_vectors(doc_id: str) -> None:
    collection, _ = _resources()
    collection.delete(where={"doc_id": doc_id})


def retrieve(query: str, top_k: int | None = None) -> list[dict[str, Any]]:
    collection, model = _resources()
    if collection.count() == 0:
        return []
    vector = [next(model.query_embed(query)).tolist()]
    result = collection.query(
        query_embeddings=vector,
        n_results=min(top_k or RAG_TOP_K, collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    sources = []
    for doc, meta, distance in zip(
        (result.get("documents") or [[]])[0],
        (result.get("metadatas") or [[]])[0],
        (result.get("distances") or [[]])[0],
    ):
        sources.append({
            "filename": meta.get("filename", "未知文件"),
            "chunk_index": int(meta.get("chunk_index", 0)),
            "content": doc,
            "distance": round(float(distance), 4),
        })
    return sources


def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".md", ".markdown", ".txt", ".csv", ".json", ".py", ".js", ".ts", ".html", ".css"}:
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("文本文件编码无法识别，请转换为 UTF-8 后上传。")
    if suffix == ".pdf":
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        from docx import Document
        import io
        document = Document(io.BytesIO(data))
        return "\n\n".join(p.text for p in document.paragraphs)
    raise ValueError("暂不支持该文件类型。请上传 Markdown、TXT、PDF 或 DOCX 文件。")
