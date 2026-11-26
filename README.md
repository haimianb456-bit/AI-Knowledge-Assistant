# AI Knowledge Assistant — Vue 3 + FastAPI + Groq + RAG

一个基于 Vue 3、FastAPI 和 Groq API 构建的 AI 智能对话与本地知识库问答系统。支持多会话管理、Markdown 内容渲染、文档上传、本地 Embedding、Chroma 向量检索，以及基于检索结果的增强生成（RAG）。

项目在原有 AI 对话功能上扩展了完整的本地 RAG 流程，使用户能够上传自己的文档，并通过自然语言提问获取基于文档内容的回答和来源引用。

**GitHub：** https://github.com/haimianb456-bit/AI-Knowledge-Assistant

---

## 1. 项目介绍

传统大模型对话通常依赖模型自身已有的知识，无法直接理解用户本地的私有文档。本项目通过 RAG（Retrieval-Augmented Generation，检索增强生成）技术，将本地文档转换为向量数据，在用户提问时检索相关内容，并将检索结果作为上下文交给大模型生成回答。

项目采用前后端分离架构：

- 前端使用 Vue 3 构建交互界面。
- 后端使用 FastAPI 提供 REST API 和 SSE 流式响应。
- 使用 Groq API 提供大模型文本生成能力。
- 使用 FastEmbed 在本地完成文本向量化。
- 使用 Chroma 持久化存储和检索向量。
- 使用 SQLite 保存会话、消息和知识库文档信息。

**项目设计目标：** 在不依赖付费 Embedding API 的情况下，实现一个可以本地运行、支持个人文档检索和来源引用的 AI 知识库问答系统。

## 2. 核心功能

### AI 对话

- 支持创建、切换和删除对话会话。
- 保存历史消息，支持连续上下文交流。
- 使用 SSE 实现模型回答的流式输出。
- 支持停止生成。
- 支持普通大模型对话和 RAG 知识库问答两种模式。

### Markdown 内容展示

- 支持标题、段落、列表和表格。
- 支持引用块和代码块。
- 支持代码语法高亮。
- 支持代码复制。

### 知识库管理

- 支持上传、查看和删除知识库文档。
- 支持 Markdown、TXT、PDF、DOCX 等格式。
- 单个文件最大支持 15 MB。
- 上传文档后自动解析文本并进行分块。
- 展示文档信息和文本分块数量。

支持的文件扩展名：

`.md`、`.markdown`、`.txt`、`.pdf`、`.docx`、`.csv`、`.json`、`.py`、`.js`、`.ts`、`.html`、`.css`

### 本地 RAG 检索

- 使用 FastEmbed 加载多语言 Embedding 模型。
- 在本地 CPU 环境完成文本向量化。
- 使用 Chroma 持久化存储文档向量。
- 根据用户问题进行相似度检索。
- 将 Top-K 相关文本片段注入模型上下文。
- 回答中支持 `[来源 1]` 格式的引用标记。
- 在回答下方展示来源文件和对应文本片段编号。

### 数据持久化

- SQLite 保存会话、消息和知识库文档索引。
- Chroma 保存文档向量及对应元数据。
- 支持删除知识库文档及其对应向量数据。

## 3. 技术栈

| 技术分类 | 使用技术 | 主要用途 |
|---|---|---|
| 前端框架 | Vue 3 | 页面与组件开发 |
| 前端构建 | Vite | 开发服务器与项目构建 |
| HTTP 请求 | Axios | 前后端接口通信 |
| Markdown | markdown-it | Markdown 内容解析 |
| 代码高亮 | highlight.js | 代码块语法高亮 |
| 安全处理 | DOMPurify | Markdown HTML 内容净化 |
| 后端框架 | FastAPI | REST API 开发 |
| 异步服务 | Uvicorn | ASGI 服务运行 |
| 流式响应 | SSE | 模型回答实时输出 |
| 大模型服务 | Groq API | 文本生成 |
| Embedding | FastEmbed | 本地文本向量化 |
| Embedding 模型 | paraphrase-multilingual-MiniLM-L12-v2 | 多语言语义向量表示 |
| 向量数据库 | Chroma | 向量持久化与相似度检索 |
| 关系型数据库 | SQLite | 会话、消息及文档索引存储 |
| 文档解析 | pypdf、python-docx | PDF、DOCX 文本提取 |

## 4. 系统架构

```text
                 Vue 3 前端
                      |
             Axios / SSE 请求
                      |
                 FastAPI 后端
                      |
          +-----------+-----------+
          |                       |
      对话管理                知识库管理
          |                       |
      SQLite 数据库           文档上传
          |                       |
      历史消息管理             文本解析
                                  |
                               文本分块
                                  |
                         FastEmbed 本地向量化
                                  |
                             Chroma
                          持久化向量库
                                  |
用户问题 ----------------> 向量检索
                                  |
                             Top-K 片段
                                  |
                          构建 RAG 上下文
                                  |
                             Groq API
                                  |
                             SSE 流式输出
                                  |
                         Markdown 内容展示
                                  |
                            来源引用展示
```

## 5. RAG 核心处理流程

### 5.1 文档入库流程

1. 用户在前端上传知识库文档。
2. FastAPI 接收文件并校验文件类型和大小。
3. 根据文件格式提取文本内容。
4. 按 Markdown 标题和段落边界进行初步切分，再按照字符窗口和重叠长度生成文本片段。
5. 使用 FastEmbed 在本地将文本片段转换为向量。
6. 将向量、原始文本和文档元数据保存到 Chroma。
7. 将文档名称、文件类型和分块数量保存到 SQLite。

### 5.2 用户提问流程

1. 用户输入问题并启用知识库检索。
2. 使用相同的 Embedding 模型将问题转换为查询向量。
3. 在 Chroma 中执行 Top-K 相似度检索。
4. 获取相关文本片段及其来源元数据。
5. 将检索结果与对话上下文组合成 RAG Prompt。
6. 调用 Groq API 生成回答。
7. 通过 SSE 将回答内容逐步返回前端。
8. 保存回答及引用来源，并在前端展示来源信息。

### 5.3 来源引用

检索结果会保留以下信息：

- 原始文档名称。
- 文本片段编号。
- 检索到的文本内容。
- 向量检索距离。

系统将检索片段组织为带编号的上下文，提示模型在回答相关内容时使用 `[来源 1]`、`[来源 2]` 等标记。

前端同时展示检索来源卡片，便于用户查看回答所依据的文档。

## 6. 项目目录

```text
AI-Knowledge-Assistant/
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py          # 环境变量与应用配置
│   │   ├── database.py        # SQLite 数据库操作
│   │   ├── llm.py             # 大模型请求与流式生成
│   │   ├── main.py            # FastAPI 应用入口及接口
│   │   ├── rag.py             # 文档解析、分块、Embedding 和检索
│   │   └── schemas.py         # 请求数据模型
│   │
│   ├── data/                  # 本地运行数据
│   ├── requirements.txt       # Python 依赖
│   └── start_backend_windows.bat
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── chat.js        # 前端 API 请求
│   │   ├── App.vue            # 主页面及交互
│   │   ├── main.js             # 前端入口
│   │   └── style.css          # 页面样式
│   │
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.js
│   └── start_frontend_windows.bat
│
├── .gitignore
└── README.md
```

## 7. 环境要求

- Windows 10 / 11
- Python 3.11 或 3.12（推荐）
- Node.js LTS
- npm
- 可用的 Groq API Key

说明：

- Groq API 用于生成回答。
- Embedding 在本地运行，不需要购买 Embedding API。
- 首次运行需要下载 Embedding 模型，之后可以使用本机缓存。
- 本地向量数据和 SQLite 数据保存在 `backend/data` 目录。

## 8. 本地运行

### 8.1 克隆项目

```bash
git clone https://github.com/haimianb456-bit/AI-Knowledge-Assistant.git

cd AI-Knowledge-Assistant
```

### 8.2 配置后端环境变量

进入后端目录：

```powershell
cd backend
```

复制 `.env.example` 并重命名为 `.env`，填写自己的 Groq API Key：

```env
LLM_PROVIDER=Groq
LLM_API_KEY=你的Groq_API_Key
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=openai/gpt-oss-120b
LLM_TIMEOUT=120
```

注意：

- API Key 仅放在后端 `.env` 文件中。
- 不要将真实 API Key 写入 Vue 前端代码。
- 不要将 `.env` 上传到 GitHub。
- 如果密钥已经泄露，请及时撤销并重新生成。

### 8.3 安装后端依赖

建议使用 Python 3.11 或 3.12 创建虚拟环境：

```powershell
py -3.12 -m venv .venv

.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip

python -m pip install -r requirements.txt
```

如果电脑没有 Python 3.12，可以使用：

```powershell
py -0p
```

查看已安装的 Python 版本，再将 `-3.12` 替换成实际版本。

### 8.4 启动后端

确保当前位于 `backend` 目录，并且已经激活虚拟环境：

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

后端启动后：

- API 地址：`http://127.0.0.1:8000`
- Swagger 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/health`

### 8.5 启动前端

重新打开一个 PowerShell 窗口，进入项目的前端目录：

```powershell
cd frontend

npm install

npm run dev
```

浏览器访问：

```text
http://127.0.0.1:5173
```

至此，前后端均已启动。

## 9. 使用说明

1. 打开系统，创建一个新对话。
2. 点击知识库管理入口。
3. 上传 Markdown、TXT、PDF 或 DOCX 文档。
4. 等待系统完成文本解析、分块和向量化。
5. 上传成功后，可以在知识库列表中查看文档及文本片段数量。
6. 关闭知识库管理面板，在聊天输入框下方勾选“使用知识库检索”。
7. 输入与上传文档相关的问题。
8. 查看模型生成的回答及回答下方的来源信息。
9. 可以在知识库管理面板中删除不再需要的文档。

如果不启用知识库检索，系统仍然可以作为普通 AI 对话助手使用。

## 10. 主要 API 接口

| 请求方法 | 接口路径 | 功能 |
|---|---|---|
| GET | `/api/health` | 服务健康检查 |
| GET | `/api/conversations` | 获取会话列表 |
| POST | `/api/conversations` | 创建会话 |
| GET | `/api/conversations/{id}/messages` | 获取会话消息 |
| DELETE | `/api/conversations/{id}` | 删除会话 |
| GET | `/api/knowledge/documents` | 获取知识库文档列表 |
| POST | `/api/knowledge/documents` | 上传并向量化文档 |
| DELETE | `/api/knowledge/documents/{doc_id}` | 删除文档及其向量 |
| POST | `/api/conversations/{id}/messages` | 普通或 RAG 问答 |
| POST | `/api/conversations/{id}/messages/stream` | 普通或 RAG 流式问答 |

完整接口参数及响应结构可以通过 Swagger 查看：

`http://127.0.0.1:8000/docs`

## 11. 关键技术实现

### 本地 Embedding

使用 FastEmbed 加载多语言 Embedding 模型，在本地 CPU 环境完成文本向量化。

优点：

- 不需要额外购买 Embedding API。
- 用户文档向量化在本机完成。
- 减少对外部 Embedding 服务的依赖。

### Chroma 向量检索

使用 Chroma PersistentClient 创建持久化向量集合，并采用余弦距离进行相似度检索。

向量数据包含文档 ID、文件名称和文本片段编号等元数据，便于检索结果追溯和文档删除。

### 文本分块

系统优先根据 Markdown 标题和段落边界切分文本，再使用字符窗口控制分块长度，并保留相邻文本重叠内容，以减少切分造成的上下文信息丢失。

### RAG Prompt 构建

将检索到的相关文本片段按照来源编号组织成上下文，提示大模型优先依据检索资料回答。当检索资料不足时，应明确说明资料不足，避免伪造知识库引用。

### SSE 流式输出

后端通过 FastAPI StreamingResponse 返回 `text/event-stream` 数据，前端逐步接收模型生成内容，实现类似主流 AI 对话产品的实时输出体验。

## 12. 常见问题

**Q1：第一次上传文档为什么比较慢？**

首次使用时需要下载本地 Embedding 模型。下载完成后会使用本机缓存，后续不需要重复下载。

**Q2：Embedding 是否收费？**

本项目使用本地 FastEmbed，不需要调用付费 Embedding API。但首次下载模型需要网络。

**Q3：Groq API 是否完全免费？**

Groq API 的使用受其账户套餐、额度和速率限制影响。本项目不能保证模型生成服务永久免费。

**Q4：为什么 PDF 上传后没有提取出内容？**

当前使用 pypdf 提取 PDF 文本，不包含 OCR 功能。扫描图片型 PDF 需要先进行 OCR 处理，或转换成可选择文本的 PDF。

**Q5：为什么模型没有显示来源引用？**

请确认已经上传知识库文档，并启用了“使用知识库检索”。如果检索内容不足，模型可能无法给出有效引用。回答下方的来源卡片展示实际检索到的文本片段。

**Q6：删除知识库文档会发生什么？**

系统会删除对应 Chroma 向量数据，并删除 SQLite 中的文档索引记录。

## 13. 项目说明与当前限制

- 当前版本面向单用户本地运行，尚未实现用户登录、权限隔离和多租户管理。
- 当前版本不包含扫描版 PDF 的 OCR 处理。
- 当前 RAG 采用向量相似度检索，尚未实现 BM25 混合检索、重排序模型和复杂查询改写。
- 本地 Embedding 不产生 API 调用费用，但模型首次下载需要网络。
- 模型回答依赖 Groq API，受其服务可用性和账户额度影响。
- 本地 SQLite 数据、Chroma 向量库和相关运行数据需要自行备份。

---

## License

目前项目未指定开源许可证。未经明确授权，请勿将其作为可自由商用或再分发的软件。
