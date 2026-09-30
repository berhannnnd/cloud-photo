#!/usr/bin/env python3
"""Build small, persistent image preview sheets for cloud-photo results.

This tool deliberately writes image files instead of producing a large base64
blob. The host can attach each sheet or pass its path to the preview renderer.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - depends on host runtime
    Image = ImageDraw = ImageFont = None


def fail(message: str) -> None:
    raise ValueError(message)


def read_items(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        fail(f"items file not found: {path}")
    if path.suffix.lower() == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            value = value.get("items") or value.get("candidates") or []
        if not isinstance(value, list):
            fail("items JSON must be an array or an object containing items")
        return value
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_font(size: int):
    if ImageFont is None:
        return None
    for name in ("/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if pathlib.Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def save_small(sheet, path: pathlib.Path, max_bytes: int, quality: int):
    current = quality
    while current >= 25:
        sheet.save(path, format="JPEG", quality=current, optimize=True)
        if path.stat().st_size <= max_bytes:
            return current
        current -= 5
    sheet.save(path, format="JPEG", quality=25, optimize=True)
    return 25


def build(args):
    if Image is None:
        fail("Pillow is required for preview-pack; use the host image runtime")
    items = read_items(pathlib.Path(args.items))
    output = pathlib.Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    thumb_dir = pathlib.Path(args.thumbnail_dir)
    valid = []
    missing = []
    for item in items:
        asset_id = item.get("asset_id")
        thumb = item.get("thumbnail") or str(thumb_dir / f"{asset_id.replace(':', '_')}.jpg")
        path = pathlib.Path(thumb)
        if not path.exists() or path.stat().st_size == 0:
            missing.append({"asset_id": asset_id, "thumbnail": str(path)})
            continue
        valid.append({**item, "thumbnail": str(path)})
    cols = max(1, args.columns)
    per_sheet = cols * max(1, args.rows)
    font = load_font(args.font_size)
    sheets = []
    for offset in range(0, len(valid), per_sheet):
        chunk = valid[offset:offset + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * args.tile, rows * (args.tile + args.caption)), "white")
        draw = ImageDraw.Draw(sheet)
        for index, item in enumerate(chunk):
            x = (index % cols) * args.tile
            y = (index // cols) * (args.tile + args.caption)
            try:
                image = Image.open(item["thumbnail"]).convert("RGB")
                image.thumbnail((args.tile - 4, args.tile - 4))
                sheet.paste(image, (x + (args.tile - image.width) // 2, y + (args.tile - image.height) // 2))
            except Exception:
                draw.rectangle((x, y, x + args.tile, y + args.tile), fill="#eeeeee")
                draw.text((x + 5, y + args.tile // 2), "IMAGE ERROR", fill="#b00020", font=font)
            caption = str(item.get("name") or item.get("path") or item.get("asset_id") or "")[:args.caption_chars]
            draw.text((x + 4, y + args.tile + 2), caption, fill="#222222", font=font)
        number = offset // per_sheet + 1
        path = output / f"sheet-{number:02d}.jpg"
        quality = save_small(sheet, path, args.max_bytes, args.quality)
        sheets.append({"path": str(path), "count": len(chunk), "bytes": path.stat().st_size, "quality": quality, "items": chunk})
    index = {"schema_version": "cloud-photo/preview-v1", "sheets": sheets, "missing": missing, "total": len(items), "renderable": len(valid)}
    (output / "preview-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "sheets": len(sheets), "renderable": len(valid), "missing": len(missing), "preview_index": str(output / "preview-index.json")}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Create bounded persistent preview sheets")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build")
    p.add_argument("--items", required=True, help="JSON array/object or JSONL of candidate records")
    p.add_argument("--thumbnail-dir", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--columns", type=int, default=4)
    p.add_argument("--rows", type=int, default=3)
    p.add_argument("--tile", type=int, default=160)
    p.add_argument("--caption", type=int, default=22)
    p.add_argument("--caption-chars", type=int, default=24)
    p.add_argument("--font-size", type=int, default=11)
    p.add_argument("--max-bytes", type=int, default=80000)
    p.add_argument("--quality", type=int, default=55)
    p.set_defaults(func=build)
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
