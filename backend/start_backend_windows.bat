@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo 已创建 backend\.env，请先编辑并填写 LLM_API_KEY（Groq API Key）。
  notepad ".env"
)
if not exist ".venv\Scripts\python.exe" (
  echo 正在优先使用 Python 3.13 创建虚拟环境...
  py -3.13 -m venv .venv
  if errorlevel 1 (
    echo 未找到 Python 3.13，尝试 Python 3.12...
    py -3.12 -m venv .venv
  )
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install --prefer-binary -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
goto end
:failed
echo 启动失败，请检查 Python 安装、网络连接和错误提示。
:end
pause
