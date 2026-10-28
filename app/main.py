"""MDTool GUI：Markdown 表格 → Word、Mermaid → 圖片。"""

from __future__ import annotations

import io
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from app.clipboard_util import (
    copy_html_and_text,
    copy_image_png,
    copy_text,
    get_clipboard_html,
    get_clipboard_image_png,
    get_clipboard_text,
)
from app.mermaid_converter import extract_mermaid_blocks, render_mermaid_png
from app.reverse_mermaid import image_to_mermaid
from app.reverse_table import convert_pasted_to_markdown
from app.table_converter import (
    parse_markdown_tables,
    save_tables_to_docx,
    tables_to_html,
    tables_to_plain,
)


SAMPLE = """# MDTool 範例

## 表格（複製後可貼到 Word）

| 項目 | 負責人 | 狀態 | 進度 |
| :--- | :----: | ---: | ---- |
| 需求分析 | 小明 | 完成 | 100% |
| UI 設計 | 小華 | 進行中 | 60% |
| 開發實作 | 小美 | 待開始 | 0% |

## Mermaid 流程圖

```mermaid
flowchart TD
    A[開始] --> B{需求確認?}
    B -->|是| C[設計]
    B -->|否| D[收集需求]
    D --> B
    C --> E[開發]
    E --> F[測試]
    F --> G{通過?}
    G -->|是| H[上線]
    G -->|否| E
    H --> I[結束]
```
"""


class MDToolApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("MDTool — Markdown 表格 / Mermaid 轉換")
        self.geometry("1180x720")
        self.minsize(900, 560)

        self._preview_image: ctk.CTkImage | None = None
        self._preview_pil: Image.Image | None = None
        self._last_png: bytes | None = None
        self._render_job = 0
        self._reverse_image_png: bytes | None = None
        self._reverse_image_preview: ctk.CTkImage | None = None
        self._reverse_image_pil: Image.Image | None = None
        self._reverse_table_html = ""
        self._last_reverse_md = ""
        self._rev_img_job = 0

        self._build_ui()
        self.editor.insert("1.0", SAMPLE)
        self._reset_preview_placeholders()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(14, 6))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="MDTool",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="正向：MD → 表格/圖片｜反向：貼上 Word 表格或架構圖 → Markdown",
            font=ctk.CTkFont(size=13),
            text_color=("gray40", "gray70"),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        # 左：編輯
        left = ctk.CTkFrame(self)
        left.grid(row=1, column=0, sticky="nsew", padx=(16, 8), pady=8)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="Markdown 輸入", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 4)
        )
        self.editor = ctk.CTkTextbox(left, font=ctk.CTkFont(family="Consolas", size=13), wrap="none")
        self.editor.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        left_btns = ctk.CTkFrame(left, fg_color="transparent")
        left_btns.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        ctk.CTkButton(
            left_btns,
            text="轉換",
            width=120,
            height=36,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.convert,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(left_btns, text="載入範例", width=100, command=self.load_sample).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(left_btns, text="清空", width=80, fg_color="gray40", command=self.clear_editor).pack(
            side="left"
        )

        # 右：預覽 + 操作
        right = ctk.CTkFrame(self)
        right.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=8)
        right.grid_rowconfigure(2, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right, text="預覽 / 輸出", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 4)
        )

        self.tabview = ctk.CTkTabview(right)
        self.tabview.grid(row=1, column=0, rowspan=2, sticky="nsew", padx=12, pady=(0, 8))
        self.tab_table = self.tabview.add("表格 → Word")
        self.tab_mermaid = self.tabview.add("Mermaid → 圖片")
        self.tab_rev_table = self.tabview.add("貼上表格 → MD")
        self.tab_rev_image = self.tabview.add("貼上圖片 → MD")

        # 表格分頁
        self.tab_table.grid_rowconfigure(0, weight=1)
        self.tab_table.grid_columnconfigure(0, weight=1)
        self.table_preview = ctk.CTkTextbox(
            self.tab_table, font=ctk.CTkFont(family="Consolas", size=12)
        )
        self.table_preview.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        table_btns = ctk.CTkFrame(self.tab_table, fg_color="transparent")
        table_btns.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 8))
        ctk.CTkButton(
            table_btns, text="複製表格（可貼到 Word）", command=self.copy_table
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            table_btns, text="另存 .docx", fg_color="#1f6aa5", command=self.save_docx
        ).pack(side="left")

        # Mermaid 分頁
        self.tab_mermaid.grid_rowconfigure(0, weight=1)
        self.tab_mermaid.grid_columnconfigure(0, weight=1)
        self.mermaid_canvas = ctk.CTkScrollableFrame(self.tab_mermaid)
        self.mermaid_canvas.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._set_mermaid_preview(text="請按左側「轉換」產生 Mermaid 圖片預覽")

        mermaid_btns = ctk.CTkFrame(self.tab_mermaid, fg_color="transparent")
        mermaid_btns.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 8))
        ctk.CTkButton(mermaid_btns, text="複製圖片", command=self.copy_mermaid_image).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(
            mermaid_btns, text="另存 PNG", fg_color="#1f6aa5", command=self.save_mermaid_png
        ).pack(side="left")

        # 反向：表格 → MD
        self.tab_rev_table.grid_rowconfigure(1, weight=1)
        self.tab_rev_table.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self.tab_rev_table,
            text="從 Word / Excel 複製表格後貼上（或按下方從剪貼簿讀取）",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
        self.reverse_table_input = ctk.CTkTextbox(
            self.tab_rev_table, font=ctk.CTkFont(family="Consolas", size=12)
        )
        self.reverse_table_input.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        rev_table_btns = ctk.CTkFrame(self.tab_rev_table, fg_color="transparent")
        rev_table_btns.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 8))
        ctk.CTkButton(
            rev_table_btns, text="從剪貼簿貼上", command=self.paste_table_from_clipboard
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            rev_table_btns,
            text="轉成 Markdown",
            font=ctk.CTkFont(weight="bold"),
            command=self.convert_table_to_md,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            rev_table_btns, text="複製 MD", fg_color="#1f6aa5", command=self.copy_reverse_table_md
        ).pack(side="left")

        # 反向：圖片 → Mermaid MD
        self.tab_rev_image.grid_rowconfigure(1, weight=1)
        self.tab_rev_image.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self.tab_rev_image,
            text="貼上架構 / 流程圖（OCR 產生 Mermaid 草稿，複雜圖請再微調）",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
        self.reverse_image_canvas = ctk.CTkScrollableFrame(self.tab_rev_image)
        self.reverse_image_canvas.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self.reverse_image_label = ctk.CTkLabel(
            self.reverse_image_canvas, text="尚未載入圖片", justify="left"
        )
        self.reverse_image_label.pack(expand=True, fill="both", padx=8, pady=8)
        rev_img_btns = ctk.CTkFrame(self.tab_rev_image, fg_color="transparent")
        rev_img_btns.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 8))
        ctk.CTkButton(
            rev_img_btns, text="從剪貼簿貼上圖片", command=self.paste_image_from_clipboard
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(rev_img_btns, text="開啟圖片", command=self.open_reverse_image).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(
            rev_img_btns,
            text="轉成 Mermaid",
            font=ctk.CTkFont(weight="bold"),
            command=self.convert_image_to_md,
        ).pack(side="left")

        self.status = ctk.CTkLabel(
            self,
            text="就緒 — 編輯完成後按「轉換」",
            anchor="w",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray65"),
        )
        self.status.grid(row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 10))

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def _set_mermaid_preview(
        self, text: str = "", image: Image.Image | None = None
    ) -> None:
        """重建預覽內容，避免 CTkLabel 殘留失效的 image 參考。"""
        for child in self.mermaid_canvas.winfo_children():
            child.destroy()
        self._preview_image = None
        self._preview_pil = None

        if image is not None:
            # 保留 PIL 物件，防止被 GC
            self._preview_pil = image.copy()
            self._preview_image = ctk.CTkImage(
                light_image=self._preview_pil,
                dark_image=self._preview_pil,
                size=(self._preview_pil.width, self._preview_pil.height),
            )
            ctk.CTkLabel(
                self.mermaid_canvas,
                image=self._preview_image,
                text="",
            ).pack(padx=8, pady=8)
            if text:
                ctk.CTkLabel(self.mermaid_canvas, text=text, justify="left").pack(
                    padx=8, pady=(0, 8)
                )
            return

        ctk.CTkLabel(self.mermaid_canvas, text=text or " ", justify="left").pack(
            expand=True, fill="both", padx=8, pady=8
        )

    def _reset_preview_placeholders(self) -> None:
        self._last_png = None
        self.table_preview.delete("1.0", "end")
        self.table_preview.insert(
            "1.0",
            "尚未轉換。\n\n請在左側輸入 Markdown 後按「轉換」。\n\n表格格式範例：\n"
            "| 欄位A | 欄位B |\n| --- | --- |\n| 值1 | 值2 |",
        )
        self._set_mermaid_preview(text="請按左側「轉換」產生 Mermaid 圖片預覽")
        self._set_status("就緒 — 編輯完成後按「轉換」")

    def load_sample(self) -> None:
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", SAMPLE)
        self._reset_preview_placeholders()
        self._set_status("已載入範例 — 請按「轉換」")

    def clear_editor(self) -> None:
        self.editor.delete("1.0", "end")
        self._reset_preview_placeholders()

    def _get_text(self) -> str:
        return self.editor.get("1.0", "end-1c")

    def convert(self) -> None:
        """手動轉換：更新表格預覽，若有 Mermaid 則渲染圖片。"""
        text = self._get_text().strip()
        if not text:
            messagebox.showinfo("提示", "請先輸入 Markdown 內容。")
            return

        tables = parse_markdown_tables(text)
        blocks = extract_mermaid_blocks(text)

        if tables:
            preview = tables_to_plain(tables)
            info = f"偵測到 {len(tables)} 個表格\n\n{preview}"
            self.table_preview.delete("1.0", "end")
            self.table_preview.insert("1.0", info)
        else:
            self.table_preview.delete("1.0", "end")
            self.table_preview.insert(
                "1.0",
                "尚未偵測到 Markdown 表格。\n\n格式範例：\n"
                "| 欄位A | 欄位B |\n| --- | --- |\n| 值1 | 值2 |",
            )

        if not tables and not blocks:
            self._last_png = None
            self._set_mermaid_preview(text="尚未偵測到表格或 Mermaid 區塊")
            self._set_status("找不到可轉換的內容")
            messagebox.showinfo("提示", "沒有偵測到 Markdown 表格或 Mermaid 區塊。")
            return

        if blocks:
            self._set_status(f"表格 {len(tables)} 個 · Mermaid {len(blocks)} 個 — 渲染中…")
            self.render_mermaid(switch_tab=True)
        else:
            self._last_png = None
            self._set_mermaid_preview(text="尚未偵測到 Mermaid 區塊")
            self.tabview.set("表格 → Word")
            self._set_status(f"轉換完成：表格 {len(tables)} 個 · Mermaid 0 個")

    def copy_table(self) -> None:
        tables = parse_markdown_tables(self._get_text())
        if not tables:
            messagebox.showinfo("提示", "沒有找到 Markdown 表格。")
            return
        try:
            copy_html_and_text(tables_to_html(tables), tables_to_plain(tables))
            self._set_status(f"已複製 {len(tables)} 個表格到剪貼簿 — 到 Word 按 Ctrl+V 即可貼成表格")
            messagebox.showinfo(
                "已複製",
                f"已複製 {len(tables)} 個表格。\n\n請到 Word / docx 文件中按 Ctrl+V 貼上。",
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("複製失敗", str(exc))

    def save_docx(self) -> None:
        tables = parse_markdown_tables(self._get_text())
        if not tables:
            messagebox.showinfo("提示", "沒有找到 Markdown 表格。")
            return
        path = filedialog.asksaveasfilename(
            title="另存 DOCX",
            defaultextension=".docx",
            filetypes=[("Word 文件", "*.docx")],
            initialfile="table.docx",
        )
        if not path:
            return
        try:
            save_tables_to_docx(tables, path)
            self._set_status(f"已儲存：{path}")
            messagebox.showinfo("完成", f"已儲存到：\n{path}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("儲存失敗", str(exc))

    def render_mermaid(self, switch_tab: bool = False) -> None:
        blocks = extract_mermaid_blocks(self._get_text())
        if not blocks:
            self._set_mermaid_preview(text="尚未偵測到 Mermaid 區塊")
            self._last_png = None
            return

        # 目前預覽第一個區塊；多個時狀態列提示
        source = blocks[0].source
        job_id = self._render_job = self._render_job + 1
        self._set_mermaid_preview(text="渲染中，請稍候…")
        if switch_tab:
            self.tabview.set("Mermaid → 圖片")

        def worker() -> None:
            try:
                png = render_mermaid_png(source)
                err = None
            except Exception as exc:  # noqa: BLE001
                png = None
                err = str(exc)
            self.after(0, lambda: self._on_mermaid_done(job_id, png, err, len(blocks)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_mermaid_done(
        self, job_id: int, png: bytes | None, err: str | None, block_count: int
    ) -> None:
        if job_id != self._render_job:
            return
        if err or not png:
            self._last_png = None
            self._set_mermaid_preview(text=f"渲染失敗：\n{err or '未知錯誤'}")
            self._set_status("Mermaid 渲染失敗")
            return

        self._last_png = png
        image = Image.open(io.BytesIO(png)).convert("RGBA")
        # 適應預覽區寬度
        max_w = max(self.mermaid_canvas.winfo_width() - 40, 480)
        if image.width > max_w:
            ratio = max_w / image.width
            image = image.resize(
                (int(image.width * ratio), int(image.height * ratio)),
                Image.Resampling.LANCZOS,
            )
        note = f"（共 {block_count} 個區塊，目前顯示第 1 個）" if block_count > 1 else ""
        self._set_mermaid_preview(text=note, image=image)
        self._set_status(f"Mermaid 渲染完成 {note}".strip())

    def copy_mermaid_image(self) -> None:
        if not self._last_png:
            messagebox.showinfo("提示", "請先按「轉換」成功產生 Mermaid 圖片。")
            return
        try:
            copy_image_png(self._last_png)
            self._set_status("圖片已複製到剪貼簿 — 可貼到 Word / PPT")
            messagebox.showinfo("已複製", "圖片已複製，可貼到 Word 或 PowerPoint。")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("複製失敗", str(exc))

    def save_mermaid_png(self) -> None:
        if not self._last_png:
            messagebox.showinfo("提示", "請先按「轉換」成功產生 Mermaid 圖片。")
            return
        path = filedialog.asksaveasfilename(
            title="另存 PNG",
            defaultextension=".png",
            filetypes=[("PNG 圖片", "*.png")],
            initialfile="mermaid.png",
        )
        if not path:
            return
        Path(path).write_bytes(self._last_png)
        self._set_status(f"已儲存：{path}")
        messagebox.showinfo("完成", f"已儲存到：\n{path}")

    # ----- 反向：表格 / 圖片 → Markdown -----

    def _send_to_editor(self, md: str, status: str) -> None:
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", md)
        self._last_reverse_md = md
        self._set_status(status)

    def paste_table_from_clipboard(self) -> None:
        try:
            html = get_clipboard_html()
            text = get_clipboard_text()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("讀取失敗", str(exc))
            return
        show = text.strip()
        if not show and html:
            show = "（剪貼簿含 HTML 表格，已就緒，請按「轉成 Markdown」）"
        if not show:
            messagebox.showinfo("提示", "剪貼簿沒有文字或表格，請先從 Word / Excel 複製。")
            return
        self.reverse_table_input.delete("1.0", "end")
        self.reverse_table_input.insert("1.0", show)
        self._reverse_table_html = html
        self._set_status("已從剪貼簿貼上表格內容")

    def convert_table_to_md(self) -> None:
        text = self.reverse_table_input.get("1.0", "end-1c")
        html = getattr(self, "_reverse_table_html", "") or ""
        # 若使用者是直接 Ctrl+V 進輸入框，再補抓一次剪貼簿 HTML
        if not html:
            try:
                html = get_clipboard_html()
            except Exception:  # noqa: BLE001
                html = ""
        try:
            md = convert_pasted_to_markdown(text=text, html=html)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("轉換失敗", str(exc))
            return
        self._send_to_editor(md, "表格已轉成 Markdown（已放到左側）")
        messagebox.showinfo("完成", "已轉成 Markdown，並放到左側編輯區。")

    def copy_reverse_table_md(self) -> None:
        md = getattr(self, "_last_reverse_md", "") or self.editor.get("1.0", "end-1c").strip()
        if not md:
            messagebox.showinfo("提示", "請先轉成 Markdown。")
            return
        try:
            copy_text(md)
            self._set_status("Markdown 已複製")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("複製失敗", str(exc))

    def _show_reverse_image(self, png: bytes) -> None:
        self._reverse_image_png = png
        image = Image.open(io.BytesIO(png)).convert("RGBA")
        max_w = max(self.reverse_image_canvas.winfo_width() - 40, 420)
        if image.width > max_w:
            ratio = max_w / image.width
            image = image.resize(
                (int(image.width * ratio), int(image.height * ratio)),
                Image.Resampling.LANCZOS,
            )
        self._reverse_image_pil = image
        self._reverse_image_preview = ctk.CTkImage(
            light_image=image, dark_image=image, size=(image.width, image.height)
        )
        for child in self.reverse_image_canvas.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            self.reverse_image_canvas, image=self._reverse_image_preview, text=""
        ).pack(padx=8, pady=8)

    def paste_image_from_clipboard(self) -> None:
        try:
            png = get_clipboard_image_png()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("讀取失敗", str(exc))
            return
        if not png:
            messagebox.showinfo("提示", "剪貼簿沒有圖片，請先複製架構 / 流程圖。")
            return
        self._show_reverse_image(png)
        self._set_status("已貼上圖片，可按「轉成 Mermaid」")

    def open_reverse_image(self) -> None:
        path = filedialog.askopenfilename(
            title="開啟架構 / 流程圖",
            filetypes=[
                ("圖片", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif"),
                ("所有檔案", "*.*"),
            ],
        )
        if not path:
            return
        png = Path(path).read_bytes()
        # 統一成 PNG bytes
        image = Image.open(io.BytesIO(png)).convert("RGBA")
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        self._show_reverse_image(buf.getvalue())
        self._set_status(f"已載入：{path}")

    def convert_image_to_md(self) -> None:
        if not self._reverse_image_png:
            messagebox.showinfo("提示", "請先貼上或開啟圖片。")
            return
        self._set_status("圖片辨識中（OCR）…")
        png = self._reverse_image_png
        job = getattr(self, "_rev_img_job", 0) + 1
        self._rev_img_job = job

        def worker() -> None:
            try:
                md = image_to_mermaid(png)
                err = None
            except Exception as exc:  # noqa: BLE001
                md = None
                err = str(exc)
            self.after(0, lambda: self._on_image_to_md_done(job, md, err))

        threading.Thread(target=worker, daemon=True).start()

    def _on_image_to_md_done(self, job: int, md: str | None, err: str | None) -> None:
        if job != getattr(self, "_rev_img_job", 0):
            return
        if err or not md:
            self._set_status("圖片轉 Mermaid 失敗")
            messagebox.showerror("轉換失敗", err or "未知錯誤")
            return
        self._send_to_editor(md, "圖片已轉成 Mermaid 草稿（已放到左側，請檢查連線）")
        messagebox.showinfo(
            "完成",
            "已轉成 Mermaid 草稿並放到左側。\n複雜架構圖請再手動微調節點與箭頭。",
        )


def main() -> None:
    # 確保從專案根目錄執行時可 import app
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    app = MDToolApp()
    app.mainloop()


if __name__ == "__main__":
    main()
