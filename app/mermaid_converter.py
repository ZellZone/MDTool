"""Mermaid 流程圖擷取與轉圖片。"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image

from app.paths import app_root

# 黑白文件風：黑線 / 黑字；節點與標籤內保留白底，畫布背景透明
_BW_MERMAID_CONFIG = {
    "theme": "base",
    "themeVariables": {
        "background": "transparent",
        "mainBkg": "#ffffff",
        "primaryColor": "#ffffff",
        "primaryTextColor": "#000000",
        "primaryBorderColor": "#000000",
        "secondaryColor": "#ffffff",
        "secondaryTextColor": "#000000",
        "secondaryBorderColor": "#000000",
        "tertiaryColor": "#ffffff",
        "tertiaryTextColor": "#000000",
        "tertiaryBorderColor": "#000000",
        "lineColor": "#000000",
        "textColor": "#000000",
        "titleColor": "#000000",
        "edgeLabelBackground": "#ffffff",
        "clusterBkg": "#ffffff",
        "clusterBorder": "#000000",
        "actorBkg": "#ffffff",
        "actorBorder": "#000000",
        "actorTextColor": "#000000",
        "actorLineColor": "#000000",
        "signalColor": "#000000",
        "signalTextColor": "#000000",
        "labelBoxBkgColor": "#ffffff",
        "labelBoxBorderColor": "#000000",
        "labelTextColor": "#000000",
        "loopTextColor": "#000000",
        "noteBkgColor": "#ffffff",
        "noteTextColor": "#000000",
        "noteBorderColor": "#000000",
        "nodeBorder": "#000000",
        "nodeTextColor": "#000000",
    },
    "flowchart": {
        "htmlLabels": False,
        "curve": "linear",
    },
}


_FENCE_RE = re.compile(
    r"```(?:mermaid)?\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)

_MERMAID_START = re.compile(
    r"^\s*(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram"
    r"|erDiagram|journey|gantt|pie|mindmap|timeline|gitGraph|C4Context)\b",
    re.MULTILINE | re.IGNORECASE,
)

@dataclass
class MermaidBlock:
    source: str
    index: int


def extract_mermaid_blocks(text: str) -> list[MermaidBlock]:
    """從文字中擷取 Mermaid 區塊（優先 ```mermaid fence）。"""
    blocks: list[MermaidBlock] = []
    for idx, match in enumerate(_FENCE_RE.finditer(text)):
        body = match.group(1).strip()
        if not body:
            continue
        fence_header = text[max(0, match.start() - 20) : match.start() + 20].lower()
        if "mermaid" in fence_header or _MERMAID_START.search(body):
            blocks.append(MermaidBlock(source=body, index=idx))

    if blocks:
        return blocks

    stripped = text.strip()
    if stripped and _MERMAID_START.search(stripped):
        return [MermaidBlock(source=stripped, index=0)]
    return []


def _local_mmdc() -> list[str] | None:
    """回傳可執行的 mmdc 命令列（優先專案 / 發行目錄的 node_modules）。"""
    root = app_root()
    cli_js = root / "node_modules" / "@mermaid-js" / "mermaid-cli" / "src" / "cli.js"
    node = shutil.which("node")
    # 直接用 node + cli.js，打包後比 .cmd wrapper 更穩
    if node and cli_js.exists():
        return [node, str(cli_js)]

    local = root / "node_modules" / ".bin" / ("mmdc.cmd" if os.name == "nt" else "mmdc")
    if local.exists():
        return [str(local)]
    which = shutil.which("mmdc")
    if which:
        return [which]
    npx = shutil.which("npx")
    if npx:
        return [npx, "--yes", "@mermaid-js/mermaid-cli"]
    return None


def _remove_outer_background(image: Image.Image, threshold: int = 245) -> Image.Image:
    """
    只去掉「與畫面邊緣相連」的近白色背景，方塊 / 標籤內的白底會保留。
    """
    from collections import deque

    img = image.convert("RGBA")
    pixels = img.load()
    width, height = img.size

    def is_background(x: int, y: int) -> bool:
        r, g, b, a = pixels[x, y]
        if a < 12:
            return True
        return r >= threshold and g >= threshold and b >= threshold

    visited = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def try_enqueue(x: int, y: int) -> None:
        idx = y * width + x
        if visited[idx] or not is_background(x, y):
            return
        visited[idx] = 1
        queue.append((x, y))

    for x in range(width):
        try_enqueue(x, 0)
        try_enqueue(x, height - 1)
    for y in range(height):
        try_enqueue(0, y)
        try_enqueue(width - 1, y)

    while queue:
        x, y = queue.popleft()
        pixels[x, y] = (255, 255, 255, 0)
        if x > 0:
            try_enqueue(x - 1, y)
        if x + 1 < width:
            try_enqueue(x + 1, y)
        if y > 0:
            try_enqueue(x, y - 1)
        if y + 1 < height:
            try_enqueue(x, y + 1)

    return img


def _to_bw_png(png_bytes: bytes) -> bytes:
    """轉成黑白 PNG：外圍去背，節點 / 標籤內白底保留。"""
    image = _remove_outer_background(Image.open(io.BytesIO(png_bytes)))
    r, g, b, a = image.split()
    gray = Image.merge("RGB", (r, g, b)).convert("L")
    # 灰階 RGB + 原 alpha：透明區維持透明，方塊內仍不透明
    image = Image.merge("RGBA", (gray, gray, gray, a))
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()



def _render_with_mmdc(source: str, timeout: float = 90.0) -> bytes:
    cmd_base = _local_mmdc()
    if not cmd_base:
        raise RuntimeError("找不到 mermaid-cli（請先執行 npm install）")

    with tempfile.TemporaryDirectory(prefix="mdtool_mmd_") as tmp:
        tmp_path = Path(tmp)
        in_file = tmp_path / "diagram.mmd"
        out_file = tmp_path / "diagram.png"
        config_file = tmp_path / "config.json"
        in_file.write_text(source, encoding="utf-8")
        config_file.write_text(
            json.dumps(_BW_MERMAID_CONFIG, ensure_ascii=False), encoding="utf-8"
        )

        cmd = [
            *cmd_base,
            "-i",
            str(in_file),
            "-o",
            str(out_file),
            "-c",
            str(config_file),
            "-b",
            "transparent",
            "-s",
            "2",
        ]
        # Windows 下 npx/mmdc 需 shell=False；隱藏 console 視窗
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(app_root()),
            creationflags=creationflags,
        )
        if proc.returncode != 0 or not out_file.exists():
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(detail or f"mmdc 失敗（exit {proc.returncode}）")
        data = out_file.read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("mmdc 輸出不是有效的 PNG")
        return data


def _encode_kroki(source: str) -> str:
    compressed = zlib.compress(source.encode("utf-8"), 9)
    return base64.urlsafe_b64encode(compressed).decode("ascii")


def _encode_mermaid_ink(source: str) -> str:
    state = json.dumps(
        {
            "code": source,
            "mermaid": {
                "theme": "base",
                "themeVariables": _BW_MERMAID_CONFIG["themeVariables"],
            },
        }
    )
    compressed = zlib.compress(state.encode("utf-8"), 9)
    return "pako:" + base64.urlsafe_b64encode(compressed).decode("ascii")


def _render_online(source: str, timeout: float = 20.0) -> bytes:
    errors: list[str] = []

    try:
        encoded = _encode_kroki(source)
        url = f"https://kroki.io/mermaid/png/{encoded}"
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200 and resp.content[:8] == b"\x89PNG\r\n\x1a\n":
            return resp.content
        errors.append(f"Kroki HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Kroki: {exc}")

    try:
        encoded = _encode_mermaid_ink(source)
        url = f"https://mermaid.ink/img/{encoded}"
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200 and resp.content[:8] == b"\x89PNG\r\n\x1a\n":
            return resp.content
        errors.append(f"mermaid.ink HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"mermaid.ink: {exc}")

    raise RuntimeError("；".join(errors) if errors else "線上渲染失敗")


def render_mermaid_png(source: str, timeout: float = 90.0) -> bytes:
    """
    將 Mermaid 原始碼渲染成 PNG bytes。
    優先本機 mermaid-cli，失敗再嘗試線上服務。
    """
    source = source.strip()
    if not source:
        raise ValueError("Mermaid 內容是空的")

    errors: list[str] = []

    try:
        return _to_bw_png(_render_with_mmdc(source, timeout=timeout))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"本機 mmdc: {exc}")

    try:
        return _to_bw_png(_render_online(source, timeout=min(20.0, timeout)))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"線上: {exc}")

    raise RuntimeError(
        "無法渲染 Mermaid 圖片。\n"
        "請確認已執行 npm install（安裝 @mermaid-js/mermaid-cli）。\n"
        + "\n".join(errors)
    )
