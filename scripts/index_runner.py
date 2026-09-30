#!/usr/bin/env python3
"""Resumable local orchestration for cloud-photo indexing.

Cloud access and model calls remain outside this script. The runner owns
stable manifests, deterministic batches, checkpoint state, and reports.
"""
from __future__ import annotations
import argparse, datetime as dt, json, pathlib, tempfile, sys

SCHEMA = "cloud-photo/v1"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif", ".avif", ".bmp", ".tif", ".tiff"}
GROUPS = ("file_metadata", "thumbnail_tags", "vision_tags")
STATUSES = {"pending", "partial", "complete", "error"}


def fail(message: str):
    raise ValueError(message)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def atomic_jsonl(path: pathlib.Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        pathlib.Path(tmp).replace(path)
    except Exception:
        pathlib.Path(tmp).unlink(missing_ok=True)
        raise


def read_jsonl(path: pathlib.Path):
    if not path.exists(): fail(f"file not found: {path}")
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip(): continue
        try: rows.append(json.loads(line))
        except json.JSONDecodeError as exc: fail(f"{path}:{number}: invalid JSON: {exc.msg}")
    return rows


def read_manifest(path: pathlib.Path):
    rows = read_jsonl(path); seen = set()
    for row in rows:
        if row.get("schema_version") != SCHEMA: fail(f"invalid schema_version for {row.get('asset_id')}")
        asset_id = row.get("asset_id")
        if not asset_id or asset_id in seen: fail(f"duplicate or missing asset_id: {asset_id}")
        seen.add(asset_id)
        if not isinstance(row.get("index_state"), dict): fail(f"missing index_state: {asset_id}")
        if row["index_state"].get("status") not in STATUSES: fail(f"invalid status: {asset_id}")
    return rows


def listing_value(item, *keys):
    for key in keys:
        value = item.get(key)
        if value not in (None, ""): return value
    return None


def cmd_ingest(args):
    output = pathlib.Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    items = read_jsonl(pathlib.Path(args.input)); rows = []; seen = set(); skipped = 0
    for item in items:
        if not isinstance(item, dict): continue
        ref = listing_value(item, "fileRef", "file_id", "id")
        name = listing_value(item, "name", "file_name") or ""
        kind = str(listing_value(item, "type", "kind") or "file").lower()
        suffix = pathlib.Path(name).suffix.lower()
        mime = listing_value(item, "mime_type", "mimeType") or ""
        is_image = kind == "image" or mime.startswith("image/") or suffix in IMAGE_EXTS
        if not ref or (not is_image and not args.include_non_images):
            skipped += 1; continue
        asset_id = "cm:" + str(ref)
        if asset_id in seen: fail(f"duplicate source reference: {ref}")
        seen.add(asset_id)
        path = listing_value(item, "path", "namePath") or name
        rows.append({
            "schema_version": SCHEMA,
            "asset_id": asset_id,
            "source_ref": {"provider": args.provider, "file_id": str(ref), "path": path},
            "file_metadata": {
                "name": name, "mime_type": mime, "size_bytes": listing_value(item, "size", "size_bytes"),
                "modified_at": listing_value(item, "updatedAt", "modified_at"),
                "width": item.get("width"), "height": item.get("height"),
                "created_at": listing_value(item, "createdAt", "created_at"),
            },
            "thumbnail_tags": {"orientation": "", "dominant_colors": [], "scene_hints": [], "ocr_text": []},
            "vision_tags": {"subjects": [], "actions": [], "scene": [], "time": [], "people": [], "objects": []},
            "index_state": {"status": "pending", "updated_at": now(), "source_hash": listing_value(item, "source_hash", "hash")},
        })
    rows.sort(key=lambda row: row["asset_id"])
    atomic_jsonl(output / "manifest.jsonl", rows)
    checkpoint = {"schema_version": SCHEMA, "scan_id": args.scan_id, "updated_at": now(), "scope": args.scope, "total": len(rows), "pending": len(rows), "completed": 0, "partial": 0, "error": 0, "skipped": skipped}
    (output / "checkpoint.json").write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(output / "manifest.jsonl"), "records": len(rows), "skipped": skipped, "scan_id": args.scan_id}, ensure_ascii=False))


def cmd_batch(args):
    rows = read_manifest(pathlib.Path(args.manifest)); selected = [r for r in rows if r["index_state"]["status"] in set(args.statuses.split(","))]
    selected = selected[args.offset:args.offset + args.limit]
    if not selected: print(json.dumps({"count": 0, "message": "no pending records"}, ensure_ascii=False)); return
    if args.output:
        atomic_jsonl(pathlib.Path(args.output), selected)
    print(json.dumps({"count": len(selected), "asset_ids": [r["asset_id"] for r in selected], "output": args.output}, ensure_ascii=False))


def cmd_apply(args):
    manifest_path = pathlib.Path(args.manifest); rows = read_manifest(manifest_path); by_id = {r["asset_id"]: r for r in rows}
    labels = read_jsonl(pathlib.Path(args.labels)); applied = 0; unknown = []
    for label in labels:
        asset_id = label.get("asset_id")
        if asset_id not in by_id: unknown.append(asset_id); continue
        row = by_id[asset_id]
        for group in GROUPS:
            if group in label:
                if not isinstance(label[group], dict): fail(f"{asset_id}: {group} must be object")
                row[group].update(label[group])
        state = label.get("index_state") or {}
        if state.get("status") in STATUSES: row["index_state"]["status"] = state["status"]
        elif "vision_tags" in label or "thumbnail_tags" in label: row["index_state"]["status"] = "complete"
        row["index_state"]["updated_at"] = now(); applied += 1
    atomic_jsonl(manifest_path, sorted(by_id.values(), key=lambda r: r["asset_id"]))
    cmd_report(argparse.Namespace(manifest=str(manifest_path), output=args.report))
    print(json.dumps({"applied": applied, "unknown_asset_ids": unknown, "manifest": str(manifest_path)}, ensure_ascii=False))


def cmd_report(args):
    rows = read_manifest(pathlib.Path(args.manifest)); counts = {status: 0 for status in STATUSES}
    for row in rows: counts[row["index_state"]["status"]] += 1
    report = {"schema_version": SCHEMA, "generated_at": now(), "manifest": str(args.manifest), "total": len(rows), "counts": counts}
    if args.output: pathlib.Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="cloud-photo resumable index runner")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("ingest", help="convert cm-cloud file listing JSONL into a manifest")
    p.add_argument("--input", required=True); p.add_argument("--output-dir", required=True); p.add_argument("--scope", default="cloud"); p.add_argument("--provider", default="cm-cloud-manage"); p.add_argument("--scan-id", default="scan-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")); p.add_argument("--include-non-images", action="store_true"); p.set_defaults(func=cmd_ingest)
    p = sub.add_parser("batch", help="select a deterministic resumable batch")
    p.add_argument("--manifest", required=True); p.add_argument("--output"); p.add_argument("--offset", type=int, default=0); p.add_argument("--limit", type=int, default=32); p.add_argument("--statuses", default="pending,partial,error"); p.set_defaults(func=cmd_batch)
    p = sub.add_parser("apply", help="merge validated thumbnail/vision labels")
    p.add_argument("--manifest", required=True); p.add_argument("--labels", required=True); p.add_argument("--report"); p.set_defaults(func=cmd_apply)
    p = sub.add_parser("report", help="summarize manifest progress")
    p.add_argument("--manifest", required=True); p.add_argument("--output"); p.set_defaults(func=cmd_report)
    args = parser.parse_args()
    try: args.func(args)
    except ValueError as exc: print(f"error: {exc}", file=sys.stderr); return 2
    return 0

if __name__ == "__main__": raise SystemExit(main())
