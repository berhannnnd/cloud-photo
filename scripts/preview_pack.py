#!/usr/bin/env python3
"""Build persistent, bounded image previews for cloud-photo results.

The default ``markdown`` command emits short workspace-relative Markdown image
links. Nexus resolves those links through its authenticated workspace preview
endpoint, so the model does not copy image bytes and no sidecar HTTP service is
needed. The legacy ``widget`` command remains available only for an explicitly
requested self-contained visualize fragment; normal photo replies must use
``markdown``.
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import pathlib
import re
import sys
from urllib.parse import quote

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


def read_preview_index(path: pathlib.Path) -> dict:
    if not path.exists():
        fail(f"preview index not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("sheets"), list):
        fail("preview index must contain a sheets array")
    return value


def workspace_relative_path(path: pathlib.Path, workspace_root: pathlib.Path | None) -> str:
    """Return a workspace-relative path safe for Nexus Markdown image loading."""
    resolved = path.resolve()
    root = workspace_root.resolve() if workspace_root else None
    if root is None:
        for parent in (resolved, *resolved.parents):
            if parent.name == ".cloud-photo":
                root = parent.parent
                break
    if root is None:
        fail(f"preview image is outside a workspace: {path}")
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        fail(f"preview image is outside the workspace root: {path}")
    if not relative.parts or relative.parts[0] != ".cloud-photo":
        fail(f"preview image must be under .cloud-photo: {path}")
    return "/".join(relative.parts)


def markdown_destination(path: str) -> str:
    """Use angle brackets so spaces in photo names remain one Markdown URL."""
    return f"<{path}>" if any(char.isspace() for char in path) else path


def build_markdown(args):
    """Write a compact workspace Markdown gallery for one preview batch.

    ``sheet`` is the default layout because Nexus renders each Markdown image
    as a full-width card. A single contact sheet keeps a six-photo result
    compact and readable; ``individual`` remains available when the user asks
    to inspect each image separately.
    """
    index_path = pathlib.Path(args.preview_index).resolve()
    index = read_preview_index(index_path)
    sheets = index["sheets"]
    if args.sheet_offset < 0 or args.sheet_offset >= len(sheets):
        fail(f"sheet-offset {args.sheet_offset} is outside the preview index ({len(sheets)} sheets)")
    if args.max_items <= 0:
        fail("max-items must be positive")
    sheet = sheets[args.sheet_offset]
    items = [item for item in (sheet.get("items") or []) if isinstance(item, dict)]
    if len(items) > args.max_items:
        fail(f"preview sheet contains {len(items)} photos; max-items is {args.max_items}")
    workspace_root = pathlib.Path(args.workspace_root).resolve() if args.workspace_root else None
    if workspace_root is None:
        for parent in (index_path, *index_path.parents):
            if parent.name == ".cloud-photo":
                workspace_root = parent.parent
                break
    if workspace_root is None:
        fail(f"cannot infer workspace root from preview index: {index_path}")

    lines = [f"### 照片预览第 {args.sheet_offset + 1} 组", ""]
    rendered = 0
    if args.layout == "sheet":
        raw_sheet = sheet.get("path")
        if not raw_sheet:
            fail("preview sheet has no path")
        sheet_path = resolve_path(raw_sheet, base_dir=index_path.parent)
        if not sheet_path.is_absolute():
            sheet_path = workspace_root / sheet_path
        if not sheet_path.exists() or sheet_path.stat().st_size == 0:
            fail(f"preview sheet not found or empty: {sheet_path}")
        relative = workspace_relative_path(sheet_path, workspace_root)
        lines.append(f"![照片预览第 {args.sheet_offset + 1} 组]({markdown_destination(relative)})")
        lines.append("")
        rendered = len(items)
    else:
        for item in items:
            raw = item.get("preview_image") or item.get("thumbnail")
            if not raw:
                continue
            image_path = resolve_path(raw, base_dir=index_path.parent)
            if not image_path.exists() or image_path.stat().st_size == 0:
                continue
            relative = workspace_relative_path(image_path, workspace_root)
            name = str(item.get("name") or image_path.name).replace("[", "\\[").replace("]", "\\]")
            source_path = str(item.get("path") or "").strip()
            lines.append(f"![{name}]({markdown_destination(relative)})")
            if source_path:
                lines.append(f"`{name}` · {source_path}")
            lines.append("")
            rendered += 1
    if rendered == 0:
        fail("no renderable preview images in the selected sheet")

    if args.layout == "sheet":
        lines.append("图片对应路径：")
        for number, item in enumerate(items, start=1):
            name = str(item.get("name") or "未命名图片")
            source_path = str(item.get("path") or "").strip()
            if source_path:
                lines.append(f"{number}. `{name}` · {source_path}")
            else:
                lines.append(f"{number}. `{name}`")
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "sheet": args.sheet_offset + 1,
        "photos": rendered,
        "layout": args.layout,
        "transport": "workspace-markdown-image",
    }, ensure_ascii=False))


def image_data_url(path: pathlib.Path) -> str:
    if not path.exists() or path.stat().st_size == 0:
        fail(f"preview image not found or empty: {path}")
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    if mime not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        fail(f"unsupported preview image type: {path}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_widget(args):
    """Write one bounded, self-contained visualize/show_widget HTML fragment.

    The fragment embeds bounded preview sheets as data URLs. It never points
    at workspace paths, localhost, or a temporary HTTP service, so it remains
    renderable after the source process exits. Nexus rejects ``widget_code``
    over 256 KiB UTF-8 or inline image data over 192 KiB; the limits here are
    enforced before the fragment reaches ``show_widget``.
    """
    index = read_preview_index(pathlib.Path(args.preview_index))
    index_path = pathlib.Path(args.preview_index).resolve()
    if args.max_sheets != 1:
        fail("one visualize call may contain exactly one contact sheet; use a new turn for the next batch")
    if args.max_total_bytes <= 0 or args.max_widget_bytes <= 0 or args.max_items <= 0:
        fail("max-total-bytes, max-widget-bytes and max-items must be positive")
    if args.sheet_offset < 0:
        fail("sheet-offset must be non-negative")
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    cards = []
    selected_counts = []
    used = 0
    skipped = 0
    sheets = index["sheets"]
    if args.sheet_offset >= len(sheets):
        fail(f"sheet-offset {args.sheet_offset} is outside the preview index ({len(sheets)} sheets)")
    selected_sheets = sheets[args.sheet_offset:args.sheet_offset + args.max_sheets]
    skipped = max(0, len(sheets) - args.sheet_offset - len(selected_sheets))
    for number, sheet in enumerate(selected_sheets, start=args.sheet_offset + 1):
        raw_path = sheet.get("path")
        if not raw_path:
            skipped += 1
            continue
        path = resolve_path(raw_path, base_dir=index_path.parent)
        size = path.stat().st_size if path.exists() else 0
        count = int(sheet.get("count") or 0)
        if count > args.max_items:
            fail(
                f"preview sheet {number} contains {count} photos; rebuild with at most {args.max_items} photos per sheet"
            )
        if not size:
            skipped += 1
            continue
        data_url = image_data_url(path)
        # Count the actual serialized UTF-8 payload, not the JPEG bytes. The
        # base64 expansion and the data URL prefix are part of widget_code.
        encoded_size = len(data_url.encode("utf-8"))
        if used + encoded_size > args.max_total_bytes:
            skipped += 1
            continue
        cards.append(
            '<figure><img loading="eager" decoding="async" src="%s" alt="照片预览第 %d 组"><figcaption>第 %d 组 · %d 张</figcaption></figure>'
            % (data_url, number, number, count)
        )
        selected_counts.append(count)
        used += encoded_size
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
    widget_bytes = len(fragment.encode("utf-8"))
    if widget_bytes > args.max_widget_bytes:
        fail(
            f"widget_code is {widget_bytes} bytes; split the preview into another turn or lower preview quality (limit {args.max_widget_bytes})"
        )
    output.write_text(fragment, encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "sheets": len(cards),
        "photos": sum(selected_counts),
        "skipped": skipped,
        "image_payload_bytes": used,
        "widget_bytes": widget_bytes,
        "limits": {
            "max_items": args.max_items,
            "max_total_bytes": args.max_total_bytes,
            "max_widget_bytes": args.max_widget_bytes,
        },
    }, ensure_ascii=False))


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
    p.add_argument("--tile", type=int, default=160)
    p.add_argument("--caption", type=int, default=22)
    p.add_argument("--caption-chars", type=int, default=24)
    p.add_argument("--font-size", type=int, default=11)
    p.add_argument("--max-bytes", type=int, default=80000)
    p.add_argument("--quality", type=int, default=55)
    p.set_defaults(func=build)
    p = sub.add_parser("widget", help="Create one bounded visualize/show_widget fragment")
    p.add_argument("--preview-index", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--max-sheets", type=int, default=1)
    p.add_argument("--sheet-offset", type=int, default=0,
                   help="zero-based contact-sheet offset for the next bounded widget (default: 0)")
    p.add_argument("--max-items", type=int, default=6)
    p.add_argument("--max-total-bytes", type=int, default=192 * 1024,
                   help="hard ceiling for serialized image data URLs (default: 192 KiB)")
    p.add_argument("--max-widget-bytes", type=int, default=256 * 1024,
                   help="hard ceiling for complete UTF-8 widget_code (default: 256 KiB)")
    p.set_defaults(func=build_widget)
    p = sub.add_parser("markdown", help="Create one native Nexus workspace image gallery")
    p.add_argument("--preview-index", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--sheet-offset", type=int, default=0)
    p.add_argument("--max-items", type=int, default=6)
    p.add_argument("--layout", choices=("sheet", "individual"), default="sheet",
                   help="compact contact sheet (default) or one Markdown image per item")
    p.add_argument("--workspace-root", help="workspace root; inferred from .cloud-photo when omitted")
    p.set_defaults(func=build_markdown)
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
