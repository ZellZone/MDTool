@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  MDTool 打包（onedir / 無 UPX）
echo ========================================
echo.
echo 說明：
echo  - 使用資料夾版發行，不用單檔 onefile、不用 UPX，可降低誤判。
echo  - 未購買程式碼簽章時，SmartScreen 仍可能顯示「未知發行者」，
echo    這不是病毒；可選「其他資訊」^>「仍要執行」。
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo 找不到 Python。
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo 找不到 npm / Node.js。Mermaid 功能需要 Node.js。
  echo 請先安裝 https://nodejs.org/ 後再打包。
  pause
  exit /b 1
)

echo [1/5] 安裝 Python 打包依賴...
python -m pip install customtkinter pillow python-docx requests pywin32 numpy pyinstaller -q
if errorlevel 1 goto :fail
python -m pip install "rapidocr-onnxruntime" -q
if errorlevel 1 (
  echo 警告：rapidocr-onnxruntime 安裝失敗，圖片轉 Mermaid 可能無法使用。
)

echo [2/5] 確認 Mermaid CLI...
if not exist "node_modules\@mermaid-js\mermaid-cli" (
  call npm install
  if errorlevel 1 goto :fail
)

echo [3/5] 產生圖示...
python packaging\make_icon.py
if errorlevel 1 goto :fail

echo [4/5] PyInstaller 打包...
if exist "build" rmdir /s /q "build"
if exist "dist\MDTool" rmdir /s /q "dist\MDTool"
python -m PyInstaller --noconfirm --clean mdtool.spec
if errorlevel 1 goto :fail

echo [5/5] 複製 Mermaid 執行環境到發行目錄...
robocopy "node_modules" "dist\MDTool\node_modules" /MIR /NFL /NDL /NJH /NJS /nc /ns /np
if %ERRORLEVEL% GEQ 8 goto :fail
copy /y "package.json" "dist\MDTool\package.json" >nul
if exist "package-lock.json" copy /y "package-lock.json" "dist\MDTool\package-lock.json" >nul
REM 避免 bat 編碼造成中文檔名複製失敗
copy /y "packaging\使用說明.txt" "dist\MDTool\README_USAGE.txt" >nul
python -c "from pathlib import Path; p=Path('packaging')/'使用說明.txt'; t=p.read_text(encoding='utf-8') if p.exists() else 'See README_USAGE.txt'; Path('dist/MDTool/使用說明.txt').write_text(t, encoding='utf-8')"

echo.
echo 完成：dist\MDTool\MDTool.exe
echo 請整個資料夾一起分發。
echo.
if /I "%MDTOOL_BUILD_NOPAUSE%"=="1" exit /b 0
pause
exit /b 0

:fail
echo.
echo 打包失敗。
if /I "%MDTOOL_BUILD_NOPAUSE%"=="1" exit /b 1
pause
exit /b 1
