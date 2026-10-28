"""產生簡單的應用程式圖示（避免空白/預設 exe 外觀）。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    out = Path(__file__).resolve().parent / "mdtool.ico"
    sizes = [16, 32, 48, 64, 128, 256]
    images: list[Image.Image] = []

    for size in sizes:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        margin = max(1, size // 12)
        # 深藍灰文件風方塊
        draw.rounded_rectangle(
            [margin, margin, size - margin - 1, size - margin - 1],
            radius=max(2, size // 8),
            fill=(45, 74, 98, 255),
        )
        # 白線模擬表格/流程
        stroke = max(1, size // 16)
        y1 = size // 3
        y2 = size * 2 // 3
        draw.line([(size // 4, y1), (size * 3 // 4, y1)], fill="white", width=stroke)
        draw.line([(size // 4, y2), (size * 3 // 4, y2)], fill="white", width=stroke)
        draw.rectangle(
            [size // 4, size // 2 - stroke, size // 4 + stroke * 2, size // 2 + stroke],
            fill="white",
        )
        images.append(img)

    images[0].save(out, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
