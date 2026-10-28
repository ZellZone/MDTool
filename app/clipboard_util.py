"""Windows 剪貼簿工具：支援 HTML（可貼到 Word）與純文字。"""

from __future__ import annotations

import html
import re


def _build_cf_html(fragment: str) -> bytes:
    """組出 Word 可辨識的 CF_HTML（UTF-8 bytes）。"""
    fragment = fragment.strip()
    # 先用固定寬度 placeholder，再回填實際 byte offset
    header = (
        "Version:0.9\r\n"
        "StartHTML:{:010d}\r\n"
        "EndHTML:{:010d}\r\n"
        "StartFragment:{:010d}\r\n"
        "EndFragment:{:010d}\r\n"
    )
    prefix = header.format(0, 0, 0, 0)
    body = (
        "<html><body>\r\n"
        "<!--StartFragment-->"
        f"{fragment}"
        "<!--EndFragment-->\r\n"
        "</body></html>"
    )
    prefix_bytes = prefix.encode("utf-8")
    body_bytes = body.encode("utf-8")
    start_html = len(prefix_bytes)
    start_fragment = start_html + body_bytes.find(b"<!--StartFragment-->") + len(
        b"<!--StartFragment-->"
    )
    end_fragment = start_html + body_bytes.find(b"<!--EndFragment-->")
    end_html = start_html + len(body_bytes)
    prefix = header.format(start_html, end_html, start_fragment, end_fragment)
    return prefix.encode("utf-8") + body_bytes


def copy_html_and_text(html_fragment: str, plain_text: str | None = None) -> None:
    """同時放入 HTML 與純文字，方便貼到 Word / 一般編輯器。"""
    import win32clipboard

    if plain_text is None:
        plain_text = re.sub(r"<[^>]+>", "", html_fragment)
        plain_text = html.unescape(plain_text).strip()

    html_bytes = _build_cf_html(html_fragment)

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        cf_html_fmt = win32clipboard.RegisterClipboardFormat("HTML Format")
        win32clipboard.SetClipboardData(cf_html_fmt, html_bytes)
        win32clipboard.SetClipboardText(plain_text, win32clipboard.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()


def get_clipboard_text() -> str:
    """讀取剪貼簿純文字。"""
    import win32clipboard
    import win32con

    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            return data or ""
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_TEXT):
            data = win32clipboard.GetClipboardData(win32con.CF_TEXT)
            if isinstance(data, bytes):
                return data.decode("utf-8", errors="ignore")
            return data or ""
        return ""
    finally:
        win32clipboard.CloseClipboard()


def get_clipboard_html() -> str:
    """讀取剪貼簿 HTML（Word 複製表格常用）。"""
    import win32clipboard

    win32clipboard.OpenClipboard()
    try:
        fmt = win32clipboard.RegisterClipboardFormat("HTML Format")
        if not win32clipboard.IsClipboardFormatAvailable(fmt):
            return ""
        raw = win32clipboard.GetClipboardData(fmt)
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="ignore")
        else:
            text = str(raw)
    finally:
        win32clipboard.CloseClipboard()

    # CF_HTML 前面有 header，本體從 <html 或 StartFragment 後開始
    lower = text.lower()
    frag_start = lower.find("<!--startfragment-->")
    frag_end = lower.find("<!--endfragment-->")
    if frag_start >= 0 and frag_end > frag_start:
        return text[frag_start + len("<!--StartFragment-->") : frag_end]
    html_at = lower.find("<html")
    if html_at >= 0:
        return text[html_at:]
    table_at = lower.find("<table")
    if table_at >= 0:
        return text[table_at:]
    return text


def get_clipboard_image_png() -> bytes | None:
    """讀取剪貼簿圖片，回傳 PNG bytes。"""
    import io

    import win32clipboard
    import win32con
    from PIL import Image

    win32clipboard.OpenClipboard()
    try:
        # 優先 PNG
        try:
            cf_png = win32clipboard.RegisterClipboardFormat("PNG")
            if win32clipboard.IsClipboardFormatAvailable(cf_png):
                data = win32clipboard.GetClipboardData(cf_png)
                if data:
                    return bytes(data)
        except Exception:  # noqa: BLE001
            pass

        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_DIB):
            data = win32clipboard.GetClipboardData(win32con.CF_DIB)
            if not data:
                return None
            # DIB → BMP header + data
            dib = bytes(data)
            header = (
                b"BM"
                + (14 + len(dib)).to_bytes(4, "little")
                + (0).to_bytes(4, "little")
                + (14).to_bytes(4, "little")
            )
            image = Image.open(io.BytesIO(header + dib))
            out = io.BytesIO()
            image.save(out, format="PNG")
            return out.getvalue()
        return None
    finally:
        win32clipboard.CloseClipboard()


def copy_text(text: str) -> None:
    """複製純文字到剪貼簿。"""
    import win32clipboard

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()


def copy_image_png(png_bytes: bytes) -> None:
    """
    將 PNG 放到剪貼簿。
    - PNG 格式：保留透明背景（較新的 Word / PPT 可貼）
    - CF_DIB：白底備援，相容較舊程式
    """
    import io

    import win32clipboard
    import win32con
    from PIL import Image

    image = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    # DIB 不支援 alpha：合成到白底作為備援
    flat = Image.new("RGB", image.size, (255, 255, 255))
    flat.paste(image, mask=image.split()[-1])
    dib_buf = io.BytesIO()
    flat.save(dib_buf, format="BMP")
    dib_data = dib_buf.getvalue()[14:]

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        cf_png = win32clipboard.RegisterClipboardFormat("PNG")
        win32clipboard.SetClipboardData(cf_png, png_bytes)
        win32clipboard.SetClipboardData(win32con.CF_DIB, dib_data)
    finally:
        win32clipboard.CloseClipboard()
