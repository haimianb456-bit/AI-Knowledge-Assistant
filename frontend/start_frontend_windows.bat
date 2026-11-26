@echo off
chcp 65001 >nul
cd /d "%~dp0"
npm install
if errorlevel 1 goto failed
npm run dev
goto end
:failed
echo 前端启动失败，请检查 Node.js/npm 安装及网络连接。
:end
pause
