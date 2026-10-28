"""反向：架構 / 流程圖片 → Mermaid 草稿（OCR + 位置推斷）。"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

from PIL import Image


@dataclass
class _OcrBox:
    text: str
    cx: float
    cy: float
    x1: float
    y1: float
    x2: float
    y2: float


def _escape_label(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace('"', "'")
    # Mermaid 節點文字避免破壞語法
    for ch in ("[", "]", "(", ")", "{", "}", "|", ";", "#"):
        text = text.replace(ch, " ")
    return re.sub(r"\s+", " ", text).strip() or "節點"


def _ocr_boxes(image: Image.Image) -> list[_OcrBox]:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "缺少 OCR 元件。請執行：pip install rapidocr-onnxruntime"
        ) from exc

    # RapidOCR 吃 numpy / path / bytes；用 RGB numpy
    import numpy as np

    rgb = image.convert("RGB")
    arr = np.array(rgb)
    engine = RapidOCR()
    result, _ = engine(arr)
    if not result:
        return []

    boxes: list[_OcrBox] = []
    for item in result:
        # item: [box, text, score] ; box = 4 points
        box, text, score = item[0], item[1], item[2]
        if score is not None and float(score) < 0.45:
            continue
        text = str(text).strip()
        if not text or len(text) > 80:
            continue
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        # 過大區塊多半是標題整段，仍保留
        boxes.append(
            _OcrBox(
                text=text,
                cx=(x1 + x2) / 2,
                cy=(y1 + y2) / 2,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
            )
        )
    return boxes


def _merge_nearby(boxes: list[_OcrBox], y_tol: float, x_gap: float) -> list[_OcrBox]:
    """合併同一列、水平相近的文字為同一節點。"""
    if not boxes:
        return []
    ordered = sorted(boxes, key=lambda b: (b.cy, b.cx))
    merged: list[_OcrBox] = []
    used = [False] * len(ordered)

    for i, b in enumerate(ordered):
        if used[i]:
            continue
        group = [b]
        used[i] = True
        for j in range(i + 1, len(ordered)):
            if used[j]:
                continue
            o = ordered[j]
            same_line = abs(o.cy - b.cy) <= y_tol
            close = o.x1 - max(g.x2 for g in group) <= x_gap
            if same_line and close:
                group.append(o)
                used[j] = True
        group.sort(key=lambda g: g.cx)
        text = " ".join(g.text for g in group)
        x1 = min(g.x1 for g in group)
        y1 = min(g.y1 for g in group)
        x2 = max(g.x2 for g in group)
        y2 = max(g.y2 for g in group)
        merged.append(
            _OcrBox(text=text, cx=(x1 + x2) / 2, cy=(y1 + y2) / 2, x1=x1, y1=y1, x2=x2, y2=y2)
        )
    return merged


def _node_id(index: int) -> str:
    # A, B, ... Z, A1, B1...
    if index < 26:
        return chr(ord("A") + index)
    return f"{chr(ord('A') + (index % 26))}{index // 26}"


def _choose_direction(boxes: list[_OcrBox]) -> str:
    if len(boxes) < 2:
        return "TD"
    xs = [b.cx for b in boxes]
    ys = [b.cy for b in boxes]
    return "LR" if (max(xs) - min(xs)) > (max(ys) - min(ys)) * 1.15 else "TD"


def _connect(boxes: list[_OcrBox], direction: str) -> list[tuple[int, int]]:
    """依方向連到「最近的下一個」節點，產生草稿連線。"""
    edges: list[tuple[int, int]] = []
    n = len(boxes)
    for i, src in enumerate(boxes):
        best_j = None
        best_score = 1e18
        for j, dst in enumerate(boxes):
            if i == j:
                continue
            if direction == "TD":
                if dst.cy <= src.cy + 8:
                    continue
                dx = abs(dst.cx - src.cx)
                dy = dst.cy - src.cy
                # 偏離水平太多則降優先
                score = dy + dx * 1.35
            else:
                if dst.cx <= src.cx + 8:
                    continue
                dy = abs(dst.cy - src.cy)
                dx = dst.cx - src.cx
                score = dx + dy * 1.35
            if score < best_score:
                best_score = score
                best_j = j
        if best_j is not None:
            edges.append((i, best_j))

    # 去重、避免過密：每個來源只保留一條
    uniq: dict[int, int] = {}
    for a, b in edges:
        uniq.setdefault(a, b)
    return list(uniq.items())


def image_to_mermaid(image: Image.Image | bytes) -> str:
    """
    將流程 / 架構圖轉成 Mermaid flowchart 草稿。
    複雜圖可能需要手動微調連線與菱形判斷。
    """
    if isinstance(image, (bytes, bytearray)):
        image = Image.open(io.BytesIO(image))
    image = image.convert("RGB")

    boxes = _ocr_boxes(image)
    if not boxes:
        raise ValueError("圖片中沒有辨識到文字，請換較清晰的架構 / 流程圖。")

    # 依圖大小動態調整合併容忍
    y_tol = max(12.0, image.height * 0.025)
    x_gap = max(24.0, image.width * 0.04)
    nodes = _merge_nearby(boxes, y_tol=y_tol, x_gap=x_gap)
    if not nodes:
        raise ValueError("無法從圖片整理出節點。")

    # 太多碎字時只取較大區塊前 N 個（依面積）
    if len(nodes) > 40:
        nodes = sorted(nodes, key=lambda b: (b.x2 - b.x1) * (b.y2 - b.y1), reverse=True)[:40]

    direction = _choose_direction(nodes)
    if direction == "TD":
        nodes.sort(key=lambda b: (b.cy, b.cx))
    else:
        nodes.sort(key=lambda b: (b.cx, b.cy))

    edges = _connect(nodes, direction)
    lines = [
        "```mermaid",
        f"flowchart {direction}",
        "    %% 由圖片 OCR 產生的草稿，請檢查節點文字與連線",
    ]
    for i, node in enumerate(nodes):
        label = _escape_label(node.text)
        # 問句傾向判斷節點
        shape_l, shape_r = "[", "]"
        if any(q in label for q in ("?", "？", "是否", "確認", "通過")):
            shape_l, shape_r = "{", "}"
        lines.append(f"    {_node_id(i)}{shape_l}{label}{shape_r}")

    if edges:
        lines.append("")
        for a, b in edges:
            lines.append(f"    {_node_id(a)} --> {_node_id(b)}")
    else:
        # 保底：依序串起來
        lines.append("")
        for i in range(len(nodes) - 1):
            lines.append(f"    {_node_id(i)} --> {_node_id(i + 1)}")

    lines.append("```")
    return "\n".join(lines)
