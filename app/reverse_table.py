"""反向：Word / Excel / HTML / TSV 表格 → Markdown。"""

from __future__ import annotations

import csv
import html as html_lib
import io
import re
from html.parser import HTMLParser

from app.table_converter import MdTable


class _TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            self._in_cell = True
        elif tag == "br" and self._in_cell and self._cell is not None:
            self._cell.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            text = html_lib.unescape("".join(self._cell))
            text = re.sub(r"[ \t]+\n", "\n", text)
            text = re.sub(r"\n[ \t]+", "\n", text)
            text = re.sub(r"[ \t]{2,}", " ", text).strip()
            text = text.replace("|", "\\|").replace("\n", "<br>")
            self._row.append(text)
            self._cell = None
            self._in_cell = False
        elif tag == "tr" and self._table is not None and self._row is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None

    def handle_data(self, data: str) -> None:
        if self._in_cell and self._cell is not None:
            self._cell.append(data)


def _grid_to_md_table(grid: list[list[str]]) -> MdTable | None:
    if not grid:
        return None
    width = max(len(r) for r in grid)
    if width == 0:
        return None
    norm = [r + [""] * (width - len(r)) for r in grid]
    headers = norm[0]
    rows = norm[1:] if len(norm) > 1 else []
    return MdTable(headers=headers, rows=rows, aligns=["left"] * width)


def parse_html_tables(html_text: str) -> list[MdTable]:
    """從 HTML（含 Word 複製內容）解析表格。"""
    if not html_text or "<table" not in html_text.lower():
        return []
    parser = _TableHTMLParser()
    try:
        parser.feed(html_text)
        parser.close()
    except Exception:  # noqa: BLE001
        return []
    tables: list[MdTable] = []
    for grid in parser.tables:
        table = _grid_to_md_table(grid)
        if table:
            tables.append(table)
    return tables


def parse_delimited_table(text: str) -> list[MdTable]:
    """解析 Tab / CSV / 多空白分隔的表格文字。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    # 已是 Markdown 表格就交給既有解析（此處只做分隔文字）
    if re.search(r"^\|.+\|\s*$", text, re.M) and re.search(r"^\|?\s*[-:| ]+\|", text, re.M):
        return []

    lines = [ln for ln in text.split("\n") if ln.strip() != ""]
    if len(lines) < 1:
        return []

    # 優先 Tab（Excel / Word 貼上常見）
    if any("\t" in ln for ln in lines):
        grid = [ln.split("\t") for ln in lines]
        table = _grid_to_md_table([[c.strip() for c in row] for row in grid])
        return [table] if table else []

    # CSV
    if any("," in ln for ln in lines) and sum(ln.count(",") for ln in lines) >= len(lines) - 1:
        try:
            reader = csv.reader(io.StringIO("\n".join(lines)))
            grid = [[c.strip() for c in row] for row in reader]
            table = _grid_to_md_table(grid)
            return [table] if table else []
        except Exception:  # noqa: BLE001
            pass

    # 兩個以上空白當分隔
    if any(re.search(r"\s{2,}", ln) for ln in lines):
        grid = [re.split(r"\s{2,}", ln.strip()) for ln in lines]
        table = _grid_to_md_table(grid)
        return [table] if table else []

    return []


def table_to_markdown(table: MdTable) -> str:
    """單一表格轉 GFM Markdown。"""
    def esc(cell: str) -> str:
        return cell.replace("\n", "<br>")

    headers = [esc(h) for h in table.headers]
    sep = []
    for align in table.aligns:
        if align == "center":
            sep.append(":---:")
        elif align == "right":
            sep.append("---:")
        else:
            sep.append("---")
    while len(sep) < len(headers):
        sep.append("---")
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(sep[: len(headers)]) + " |",
    ]
    for row in table.rows:
        cells = [esc(c) for c in row]
        if len(cells) < len(headers):
            cells.extend([""] * (len(headers) - len(cells)))
        lines.append("| " + " | ".join(cells[: len(headers)]) + " |")
    return "\n".join(lines)


def tables_to_markdown(tables: list[MdTable]) -> str:
    return "\n\n".join(table_to_markdown(t) for t in tables)


def convert_pasted_to_markdown(text: str = "", html: str = "") -> str:
    """綜合 HTML / 純文字，轉成 Markdown 表格字串。"""
    tables: list[MdTable] = []
    if html:
        tables.extend(parse_html_tables(html))
    if not tables and text:
        tables.extend(parse_delimited_table(text))
    if not tables:
        raise ValueError("沒有辨識到表格。請從 Word / Excel 複製表格後再試。")
    return tables_to_markdown(tables)
