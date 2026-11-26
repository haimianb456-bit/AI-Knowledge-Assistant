"""API 请求与响应结构。"""
from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000, description="用户输入的消息")
    use_knowledge_base: bool = Field(default=False, description="是否启用 RAG 知识库检索")
