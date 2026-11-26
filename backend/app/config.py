"""应用配置：从 backend/.env 读取模型服务和运行参数。"""
from pathlib import Path
import os
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


def _csv_env(name: str, default: str) -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


# 优先使用通用 LLM_* 配置；兼容旧版 DEEPSEEK_* 环境变量。
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("DEEPSEEK_API_KEY", "")).strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", os.getenv(
    "DEEPSEEK_BASE_URL", "https://api.groq.com/openai/v1"
)).strip().rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", os.getenv(
    "DEEPSEEK_MODEL", "openai/gpt-oss-120b"
)).strip()
_default_provider = "Groq" if "groq.com" in LLM_BASE_URL.lower() else (
    "DeepSeek" if "deepseek.com" in LLM_BASE_URL.lower() else "模型服务"
)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", _default_provider).strip() or _default_provider
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", os.getenv("DEEPSEEK_TIMEOUT", "90")))

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(BACKEND_DIR / "data" / "chat.db")))
CORS_ORIGINS = _csv_env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "2048"))
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "你是一名严谨、友好的中文 AI 助手。你通过当前配置的模型服务提供回答，不要声称自己是 ChatGPT、OpenAI 或其他特定公司的模型。请优先使用清晰、易懂的中文回答；遇到不确定的信息时说明不确定，不要编造事实。支持 Markdown 格式。",
)

# RAG 本地向量库与 Embedding 配置
CHROMA_PATH = Path(os.getenv("CHROMA_PATH", str(BACKEND_DIR / "data" / "chroma")))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2").strip()
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))
RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "800"))
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "120"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "15"))
