# Vue + FastAPI + Groq + 本地 RAG 知识库

在原有 Vue 3 + FastAPI + Groq 聊天项目上增加完整的本地 RAG 流程：文档上传、文本解析、分块、免费本地 Embedding、Chroma 持久化向量检索、检索增强生成及来源引用。模型 API Key 仍只保存在后端。

## 功能

- 原有聊天功能：多会话、SQLite 历史记录、SSE 流式输出、停止生成。
- Markdown 展示：标题、列表、表格、引用、代码块高亮和复制。
- 知识库管理：上传、列表、删除文档；支持 `.md`、`.markdown`、`.txt`、`.pdf`、`.docx`、`.csv`、`.json`、`.py`、`.js`、`.ts`、`.html`、`.css`。
- 本地向量化：FastEmbed + `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，多语言模型，CPU 本地运行，不调用付费 Embedding API。
- Chroma 持久化：向量数据保存在 `backend/data/chroma`。
- RAG 问答：对用户问题进行向量检索，取 Top-K 片段作为上下文交给 Groq；提示模型基于资料回答并使用 `[来源 1]` 格式标注。
- 来源引用：每条回答保存检索来源，前端在回答下方显示来源文件名和片段编号。
- SQLite 保存会话、消息和知识库文档索引；兼容旧数据库并自动添加消息来源字段。

## 环境要求

- Windows 10/11
- Python 3.10–3.13（建议 3.11 或 3.12；如果使用 3.13，请确保依赖有对应 wheel）
- Node.js LTS + npm
- Groq API Key（仅负责生成回答；Embedding 完全本地免费）

## 1. 配置后端

打开 PowerShell：

```powershell
cd backend
```

复制 `backend/.env.example` 并重命名为 `.env`，填写自己的 Groq Key：

```env
LLM_PROVIDER=Groq
LLM_API_KEY=你的Groq_API_Key
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=openai/gpt-oss-120b
LLM_TIMEOUT=120
```

不要把 Key 写入 Vue 前端，不要提交 `.env`，不要在聊天或截图中公开 Key。若 Key 曾泄露，请先在 Groq 控制台撤销并重新创建。

## 2. 安装 Python 依赖

推荐使用 Python 3.11 或 3.12 创建干净环境：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

若电脑没有 Python 3.12，可先运行 `py -0p` 查看已安装版本，再将 `-3.12` 改成对应版本，例如 `-3.13`。首次安装 Chroma/FastEmbed 相关依赖可能需要一些时间。

## 3. 启动后端

在 `backend` 目录、虚拟环境已激活的 PowerShell 中运行：

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

浏览器打开 <http://127.0.0.1:8000/docs> 可查看接口。健康检查：<http://127.0.0.1:8000/api/health>。

## 4. 启动前端

再打开第二个 PowerShell 窗口：

```powershell
cd frontend
npm install
npm run dev
```

访问 <http://127.0.0.1:5173>。

## 5. 使用 RAG

1. 点击右上角“知识库管理”。
2. 点击“上传知识文档”，选择 Markdown、TXT、PDF 或 DOCX 文件（单个文件不超过 15 MB）。
3. 首次上传时，FastEmbed 会自动下载 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` 模型。下载完成后，模型保存在本机缓存中，后续无需重复下载。
4. 等待提示“已加入知识库”，可看到切分出的文本片段数量。
5. 关闭知识库管理面板，在输入框下方勾选“使用知识库检索”。
6. 提出与资料相关的问题。回答会在相关内容处使用 `[来源 1]` 标记，并在回答下方列出引用文件及片段编号。
7. 在知识库管理中可以删除文档；删除操作会同时移除对应 Chroma 向量和 SQLite 文档记录。

不勾选“使用知识库检索”时，聊天仍按普通 Groq 对话工作。

## 6. RAG 请求链路

```text
上传文件
  -> 文件文本解析（Markdown/TXT/PDF/DOCX 等）
  -> 按字符窗口切分并保留重叠
  -> FastEmbed 本地生成多语言向量
  -> Chroma 持久化保存向量与元数据

用户提问
  -> 本地 Embedding 查询向量
  -> Chroma Top-K 相似度检索
  -> 检索片段 + 对话上下文 -> FastAPI -> Groq Chat Completions
  -> SSE 流式回答（含 [来源 N]）
  -> SQLite 保存问答及引用元数据
```

## 7. 关键接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 后端健康检查 |
| GET | `/api/knowledge/documents` | 知识库文档列表 |
| POST | `/api/knowledge/documents` | 上传并向量化文档（multipart/form-data） |
| DELETE | `/api/knowledge/documents/{doc_id}` | 删除文档及向量 |
| POST | `/api/conversations/{id}/messages/stream` | 普通或 RAG 流式问答，`use_knowledge_base` 控制是否检索 |
| GET | `/api/conversations/{id}/messages` | 历史消息及来源 |

Swagger：<http://127.0.0.1:8000/docs>

## 8. 常见问题

- **第一次上传文档很慢：** 正在下载本地 Embedding 模型。首次需要网络，成功后模型缓存在本机。
- **Embedding 模型下载失败：** 检查 Hugging Face 网络访问；可设置 `HF_ENDPOINT` 为可访问的镜像站后重启后端。不要关闭 TLS 证书验证。
- **`ModuleNotFoundError: chromadb` / `fastembed`：** 确认当前 PowerShell 激活的是项目 `.venv`，并在 `backend` 目录重新运行 `python -m pip install -r requirements.txt`。
- **PDF 没有提取出文字：** 扫描版 PDF 需要 OCR，本版本不包含 OCR；请先将其转换为可选中文本的 PDF 或 TXT/Markdown。
- **没有来源：** 检查是否已上传文档、是否勾选“使用知识库检索”，并确认问题与资料内容相关。
- **回答没有按来源引用：** 模型可能没有严格遵循提示；检查回答下方的来源卡片，它们表示实际检索到的片段。
- **Groq 额度或 Key 错误：** RAG Embedding 不收费，但最终生成回答仍使用 Groq API，受 Groq 当前账户额度和限额约束。

## 项目边界与说明

- 本项目实现的是单用户本地知识库，没有账号隔离和多租户权限控制。
- 文本型 PDF 支持直接提取；扫描图片 PDF 暂不支持 OCR。
- 本地 Embedding 免费运行，但首次下载模型需要网络和磁盘空间。
- Chroma 数据、SQLite 数据和上传文档索引均位于 `backend/data`，请自行备份；不要把个人敏感文件上传到不可信环境。
