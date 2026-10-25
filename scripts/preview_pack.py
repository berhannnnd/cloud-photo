#!/usr/bin/env python3
"""Build static contact-sheet files for host-managed media delivery.

This helper does not upload media, send messages, or render a frontend.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
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


def resolve_path(value: str | pathlib.Path, *, base_dir: pathlib.Path) -> pathlib.Path:
    """Resolve paths recorded by a producer without depending on its cwd."""
    path = pathlib.Path(value)
    if path.is_absolute():
        return path
    candidate = base_dir / path
    if candidate.exists():
        return candidate
    return path


def safe_asset_filename(asset_id: str) -> str:
    # Cloud references can contain separators or characters that are awkward
    # in a workspace filename. Keep the mapping deterministic and flat.
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", asset_id)
    return value or "asset"


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
    if args.max_bytes <= 0 or args.columns <= 0 or args.rows <= 0 or args.tile <= 0:
        fail("max-bytes, columns, rows and tile must be positive")
    if args.columns * args.rows > 6:
        fail("a contact sheet may contain at most 6 photos; use columns*rows <= 6")
    items_path = pathlib.Path(args.items).resolve()
    items = read_items(items_path)
    output = pathlib.Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    thumb_dir = pathlib.Path(args.thumbnail_dir).resolve()
    valid = []
    missing = []
    for item in items:
        if not isinstance(item, dict):
            missing.append({"asset_id": None, "thumbnail": "", "error": "item must be an object"})
            continue
        asset_id = item.get("asset_id")
        if not asset_id:
            raise ValueError("each preview item must contain asset_id")
        thumb = item.get("thumbnail")
        if thumb:
            path = resolve_path(str(thumb), base_dir=items_path.parent)
        else:
            path = thumb_dir / f"{safe_asset_filename(str(asset_id))}.jpg"
        if not path.is_file() or path.stat().st_size == 0:
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
    p.add_argument("--columns", type=int, default=3)
    p.add_argument("--rows", type=int, default=2)
    p.add_argument("--tile", type=int, default=240)
    p.add_argument("--caption", type=int, default=22)
    p.add_argument("--caption-chars", type=int, default=24)
    p.add_argument("--font-size", type=int, default=11)
    p.add_argument("--max-bytes", type=int, default=120000)
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
