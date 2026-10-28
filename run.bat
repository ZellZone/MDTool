@echo off
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo 找不到 Python，請先安裝 Python 3。
  pause
  exit /b 1
)

echo [1/2] 安裝 Python 依賴...
python -m pip install -r requirements.txt -q
if errorlevel 1 (
  echo Python 依賴安裝失敗
  pause
  exit /b 1
)

where npm >nul 2>nul
if not errorlevel 1 (
  if not exist "node_modules\@mermaid-js\mermaid-cli" (
    echo [2/2] 安裝 Mermaid CLI（首次較久）...
    call npm install --silent
  ) else (
    echo [2/2] Mermaid CLI 已就緒
  )
) else (
  echo 警告：找不到 npm，Mermaid 將改嘗試線上渲染。
)

echo 啟動 MDTool...
python run.py
if errorlevel 1 pause
