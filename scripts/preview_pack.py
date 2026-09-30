#!/usr/bin/env python3
"""Build small, persistent image preview sheets for cloud-photo results.

This tool deliberately writes image files instead of producing a large base64
blob. The host can attach each sheet or pass its path to the preview renderer.
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
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


def read_preview_index(path: pathlib.Path) -> dict:
    if not path.exists():
        fail(f"preview index not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("sheets"), list):
        fail("preview index must contain a sheets array")
    return value


def image_data_url(path: pathlib.Path) -> str:
    if not path.exists() or path.stat().st_size == 0:
        fail(f"preview image not found or empty: {path}")
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    if mime not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        fail(f"unsupported preview image type: {path}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_widget(args):
    """Write a self-contained visualize/show_widget HTML fragment.

    The fragment embeds bounded preview sheets as data URLs. It never points
    at workspace paths, localhost, or a temporary HTTP service, so it remains
    renderable after the source process exits.
    """
    index = read_preview_index(pathlib.Path(args.preview_index))
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    cards = []
    used = 0
    skipped = 0
    for number, sheet in enumerate(index["sheets"], start=1):
        if len(cards) >= args.max_sheets:
            skipped += 1
            continue
        raw_path = sheet.get("path")
        if not raw_path:
            skipped += 1
            continue
        path = pathlib.Path(raw_path)
        size = path.stat().st_size if path.exists() else 0
        if not size or used + size > args.max_total_bytes:
            skipped += 1
            continue
        cards.append(
            '<figure><img loading="lazy" src="%s" alt="照片预览第 %d 组"><figcaption>第 %d 组 · %d 张</figcaption></figure>'
            % (image_data_url(path), number, number, int(sheet.get("count") or 0))
        )
        used += size
    if not cards:
        fail("no preview sheets fit the widget size budget")
    note = ""
    if skipped:
        note = '<p class="note">已展示 %d 组预览；另有 %d 组因可视化大小上限未嵌入，请按批次继续展示。</p>' % (len(cards), skipped)
    fragment = """<style>
#cloud-photo-preview{font:13px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--nexus-text,#222)}
#cloud-photo-preview .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}
#cloud-photo-preview figure{margin:0;border:1px solid var(--nexus-border,#ddd);border-radius:8px;overflow:hidden;background:var(--nexus-surface,#fff)}
#cloud-photo-preview img{display:block;width:100%%;height:auto;max-height:360px;object-fit:contain;background:var(--nexus-background,#f7f7f7)}
#cloud-photo-preview figcaption{padding:5px 7px;color:var(--nexus-muted,#666)}
#cloud-photo-preview .note{margin:0 0 8px;color:var(--nexus-muted,#666)}
</style>
<section id="cloud-photo-preview" aria-label="照片预览">
%s
<div class="grid">%s</div>
</section>
""" % (note, "".join(cards))
    output.write_text(fragment, encoding="utf-8")
    print(json.dumps({"output": str(output), "sheets": len(cards), "skipped": skipped, "bytes": output.stat().st_size}, ensure_ascii=False))


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
    p = sub.add_parser("widget", help="Create a self-contained visualize/show_widget fragment")
    p.add_argument("--preview-index", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--max-sheets", type=int, default=6)
    p.add_argument("--max-total-bytes", type=int, default=600000)
    p.set_defaults(func=build_widget)
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
