# MDTool

Markdown 小工具：把表格貼進 Word，把 Mermaid 流程圖轉成圖片。

## 功能

1. **Markdown 表格 → Word**
   - 解析 GFM 表格
   - 按「複製表格（可貼到 Word）」後，到 `.docx` / Word 按 `Ctrl+V`，會貼成真正的表格
   - 也可「另存 .docx」

2. **Mermaid → 圖片**
   - 支援 ` ```mermaid ` 程式碼區塊，或直接貼 flowchart 語法
   - 預覽 PNG，可複製到剪貼簿或另存檔案
   - 預設用本機 `@mermaid-js/mermaid-cli` 渲染（不依賴外網）

3. **反向：貼上表格 → Markdown**
   - 從 Word / Excel 複製表格，到「貼上表格 → MD」轉回 GFM 表格

4. **反向：架構 / 流程圖 → Mermaid**
   - 貼上或開啟圖片，OCR 產生 Mermaid 草稿（複雜圖請再微調連線）

## 使用方式

雙擊或在終端機執行：

```bat
run.bat
```

手動安裝：

```bat
pip install -r requirements.txt
npm install
python run.py
```

## 需求

- Windows
- Python 3.10+
- Node.js / npm（建議，用於本機 Mermaid 渲染）

## 打包成執行檔

```bat
build.bat
```

產出在 `dist\MDTool\`（**資料夾版**，請整包分發）：

- 使用 PyInstaller **onedir**（非單檔）
- **關閉 UPX** 壓縮
- 附檔案版本資訊與圖示

這樣可降低被防毒誤判的機率。  
若未購買程式碼簽章憑證，Windows SmartScreen 仍可能顯示「未知發行者」——選「其他資訊 → 仍要執行」即可，這與病毒無關。

執行打包版時，目標電腦需已安裝 [Node.js](https://nodejs.org/)（Mermaid 轉圖用）。
