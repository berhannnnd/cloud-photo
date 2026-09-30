#!/usr/bin/env python3
"""Resumable local orchestration for cloud-photo indexing.

Cloud access and model calls remain outside this script. The runner owns
stable manifests, deterministic batches, checkpoint state, and reports.
"""
from __future__ import annotations
import argparse, datetime as dt, json, pathlib, tempfile, sys
import os

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
            fh.flush()
            os.fsync(fh.fileno())
        pathlib.Path(tmp).replace(path)
    except Exception:
        pathlib.Path(tmp).unlink(missing_ok=True)
        raise


def atomic_json(path: pathlib.Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
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
        if not isinstance(row, dict): fail(f"manifest row must be an object: {row!r}")
        if row.get("schema_version") != SCHEMA: fail(f"invalid schema_version for {row.get('asset_id')}")
        asset_id = row.get("asset_id")
        if not asset_id or asset_id in seen: fail(f"duplicate or missing asset_id: {asset_id}")
        seen.add(asset_id)
        if not isinstance(row.get("source_ref"), dict): fail(f"missing source_ref: {asset_id}")
        for group in GROUPS:
            if not isinstance(row.get(group), dict): fail(f"missing {group}: {asset_id}")
        if not isinstance(row.get("index_state"), dict): fail(f"missing index_state: {asset_id}")
        if row["index_state"].get("status") not in STATUSES: fail(f"invalid status: {asset_id}")
    return rows


def checkpoint_path(manifest_path: pathlib.Path):
    return manifest_path.parent / "checkpoint.json"


def update_checkpoint(manifest_path: pathlib.Path, *, batch_id=None, applied_ids=()):
    rows = read_manifest(manifest_path)
    counts = {status: 0 for status in STATUSES}
    for row in rows:
        counts[row["index_state"]["status"]] += 1
    path = checkpoint_path(manifest_path)
    checkpoint = {}
    if path.exists():
        try:
            checkpoint = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"invalid checkpoint: {path}: {exc.msg}")
    checkpoint.update({
        "schema_version": SCHEMA,
        "updated_at": now(),
        "total": len(rows),
        "pending": counts["pending"],
        "completed": counts["complete"],
        "partial": counts["partial"],
        "error": counts["error"],
    })
    if batch_id:
        checkpoint["last_batch_id"] = batch_id
        checkpoint["last_batch_at"] = checkpoint["updated_at"]
    if applied_ids:
        prior = checkpoint.get("processed_asset_ids", [])
        checkpoint["processed_asset_ids"] = sorted(set(prior).union(applied_ids))
    atomic_json(path, checkpoint)
    return checkpoint


def listing_value(item, *keys):
    for key in keys:
        value = item.get(key)
        if value not in (None, ""): return value
    return None


def cmd_ingest(args):
    output = pathlib.Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    items = read_jsonl(pathlib.Path(args.input)); rows = []; seen = set(); skipped = 0
    prior = {}
    prior_path = output / "manifest.jsonl"
    if prior_path.exists() and not args.reset:
        prior = {row["asset_id"]: row for row in read_manifest(prior_path)}
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
        fresh = {
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
        }
        previous = prior.get(asset_id)
        if previous:
            old_hash = previous.get("index_state", {}).get("source_hash")
            new_hash = fresh["index_state"].get("source_hash")
            changed = bool(old_hash and new_hash and old_hash != new_hash)
            if not changed:
                # A repeated listing must not erase expensive labels already
                # produced by earlier batches. Refresh metadata while keeping
                # the existing tags and state for this same asset identity.
                fresh["thumbnail_tags"] = previous["thumbnail_tags"]
                fresh["vision_tags"] = previous["vision_tags"]
                fresh["index_state"] = previous["index_state"]
            else:
                fresh["index_state"]["error_code"] = None
                fresh["index_state"]["error_message"] = None
        rows.append(fresh)
    rows.sort(key=lambda row: row["asset_id"])
    atomic_jsonl(output / "manifest.jsonl", rows)
    checkpoint = update_checkpoint(output / "manifest.jsonl")
    checkpoint.update({"scan_id": args.scan_id, "scope": args.scope, "skipped": skipped})
    atomic_json(output / "checkpoint.json", checkpoint)
    print(json.dumps({"manifest": str(output / "manifest.jsonl"), "records": len(rows), "skipped": skipped, "scan_id": args.scan_id}, ensure_ascii=False))


def cmd_batch(args):
    if args.offset < 0 or args.limit <= 0:
        fail("offset must be non-negative and limit must be positive")
    rows = read_manifest(pathlib.Path(args.manifest))
    statuses = {status.strip() for status in args.statuses.split(",") if status.strip()}
    if not statuses.issubset(STATUSES):
        fail(f"invalid batch status: {sorted(statuses - STATUSES)}")
    # Offset is a cursor in the stable manifest order, rather than an offset
    # in the shrinking eligible list. This prevents completed earlier batches
    # from making the next cursor skip records.
    eligible = [(position, row) for position, row in enumerate(rows)
                if position >= args.offset and row["index_state"]["status"] in statuses]
    selected_pairs = eligible[:args.limit]
    selected = [row for _, row in selected_pairs]
    if not selected: print(json.dumps({"count": 0, "message": "no pending records"}, ensure_ascii=False)); return
    first_position = selected_pairs[0][0]
    last_position = selected_pairs[-1][0]
    batch_id = args.batch_id or f"batch-{first_position:06d}-{last_position:06d}"
    if args.output:
        atomic_jsonl(pathlib.Path(args.output), selected)
    request = {
        "schema_version": SCHEMA,
        "batch_id": batch_id,
        "count": len(selected),
        "assets": [{"asset_id": r["asset_id"], "source_ref": r["source_ref"], "path": r["source_ref"].get("path", "")} for r in selected],
        "next_offset": last_position + 1,
    }
    if args.request_output:
        atomic_json(pathlib.Path(args.request_output), request)
    print(json.dumps({"count": len(selected), "batch_id": batch_id, "asset_ids": [r["asset_id"] for r in selected], "output": args.output, "request_output": args.request_output, "next_offset": request["next_offset"]}, ensure_ascii=False))


def cmd_run_batch(args):
    """Close one externally downloaded batch without making cloud/API calls."""
    manifest_path = pathlib.Path(args.manifest)
    rows = read_manifest(manifest_path)
    by_id = {r["asset_id"]: r for r in rows}
    batch_rows = read_jsonl(pathlib.Path(args.batch))
    if any(not isinstance(row, dict) for row in batch_rows):
        fail("batch rows must be objects")
    batch_ids = [r.get("asset_id") for r in batch_rows]
    if any(not asset_id for asset_id in batch_ids):
        fail("batch contains a missing asset_id")
    if len(batch_ids) != len(set(batch_ids)):
        fail("batch contains duplicate asset_id")
    if any(asset_id not in by_id for asset_id in batch_ids):
        fail("batch contains an asset_id not present in manifest")
    downloads_path = pathlib.Path(args.downloads) if args.downloads else None
    downloads = read_jsonl(downloads_path) if downloads_path else []
    download_by_id = {}
    for item in downloads:
        asset_id = item.get("asset_id")
        if asset_id not in batch_ids:
            fail(f"download result is outside batch: {asset_id}")
        if asset_id in download_by_id:
            fail(f"duplicate download result: {asset_id}")
        download_by_id[asset_id] = item
    ready = []
    missing = []
    for asset_id in batch_ids:
        item = download_by_id.get(asset_id)
        local_path = item.get("local_path") if item else None
        resolved_path = None
        if local_path:
            resolved_path = pathlib.Path(local_path)
            if not resolved_path.is_absolute() and downloads_path:
                resolved_path = downloads_path.parent / resolved_path
        if (item and item.get("status", "ready") in {"ready", "downloaded", "complete"}
                and resolved_path and resolved_path.is_file() and resolved_path.stat().st_size > 0):
            ready.append({"asset_id": asset_id, "local_path": str(resolved_path), "path": by_id[asset_id]["source_ref"].get("path", "")})
        else:
            missing.append(asset_id)
    out_dir = pathlib.Path(args.output_dir or manifest_path.parent / "batches" / (args.batch_id or "current"))
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_jsonl(out_dir / "thumbnail_tasks.jsonl", ready)
    if args.labels:
        label_rows = read_jsonl(pathlib.Path(args.labels))
        label_ids = [row.get("asset_id") for row in label_rows if isinstance(row, dict)]
        if len(label_ids) != len(label_rows) or any(not asset_id for asset_id in label_ids):
            fail("label rows must contain asset_id")
        if len(label_ids) != len(set(label_ids)):
            fail("labels contain duplicate asset_id")
        outside = sorted(set(label_ids) - set(batch_ids))
        if outside:
            fail(f"labels contain asset_id outside batch: {outside}")
        apply_args = argparse.Namespace(manifest=str(manifest_path), labels=args.labels, report=args.report, batch_id=args.batch_id, output=None)
        cmd_apply(apply_args)
    else:
        update_checkpoint(manifest_path, batch_id=args.batch_id)
    result = {"batch_id": args.batch_id, "batch_count": len(batch_ids), "ready": len(ready), "missing": missing, "thumbnail_tasks": str(out_dir / "thumbnail_tasks.jsonl"), "next_step": "generate labels JSONL and run apply" if not args.labels else "batch applied"}
    print(json.dumps(result, ensure_ascii=False))


def cmd_apply(args):
    manifest_path = pathlib.Path(args.manifest); rows = read_manifest(manifest_path); by_id = {r["asset_id"]: r for r in rows}
    labels = read_jsonl(pathlib.Path(args.labels)); applied = 0; unknown = []
    seen_labels = set()
    for label in labels:
        if not isinstance(label, dict):
            fail("label rows must be objects")
        asset_id = label.get("asset_id")
        if not asset_id:
            fail("label is missing asset_id")
        if asset_id in seen_labels:
            fail(f"duplicate label asset_id: {asset_id}")
        seen_labels.add(asset_id)
        if asset_id not in by_id: unknown.append(asset_id); continue
        row = by_id[asset_id]
        for group in GROUPS:
            if group in label:
                if not isinstance(label[group], dict): fail(f"{asset_id}: {group} must be object")
                row[group].update(label[group])
        state = label.get("index_state") or {}
        if state.get("status") in STATUSES: row["index_state"]["status"] = state["status"]
        elif "thumbnail_tags" in label or "vision_tags" in label:
            # A label response containing one stage is recoverable progress;
            # an earlier stage may already be present in the manifest.
            has_thumbnail = bool(row.get("thumbnail_tags")) and any(
                value not in (None, "", []) for value in row["thumbnail_tags"].values()
            )
            has_vision = bool(row.get("vision_tags")) and any(
                value not in (None, "", []) for value in row["vision_tags"].values()
            )
            row["index_state"]["status"] = "complete" if has_thumbnail and has_vision else "partial"
        row["index_state"]["updated_at"] = now(); applied += 1
    atomic_jsonl(manifest_path, sorted(by_id.values(), key=lambda r: r["asset_id"]))
    update_checkpoint(manifest_path, batch_id=getattr(args, "batch_id", None), applied_ids=[label.get("asset_id") for label in labels if label.get("asset_id") in by_id])
    cmd_report(argparse.Namespace(manifest=str(manifest_path), output=args.report))
    print(json.dumps({"applied": applied, "unknown_asset_ids": unknown, "manifest": str(manifest_path)}, ensure_ascii=False))


def cmd_report(args):
    rows = read_manifest(pathlib.Path(args.manifest)); counts = {status: 0 for status in STATUSES}
    for row in rows: counts[row["index_state"]["status"]] += 1
    report = {"schema_version": SCHEMA, "generated_at": now(), "manifest": str(args.manifest), "total": len(rows), "counts": counts}
    if args.output: atomic_json(pathlib.Path(args.output), report)
    print(json.dumps(report, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="cloud-photo resumable index runner")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("ingest", help="convert cm-cloud file listing JSONL into a manifest")
    p.add_argument("--input", required=True); p.add_argument("--output-dir", required=True); p.add_argument("--scope", default="cloud"); p.add_argument("--provider", default="cm-cloud-manage"); p.add_argument("--scan-id", default="scan-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")); p.add_argument("--include-non-images", action="store_true"); p.add_argument("--reset", action="store_true", help="discard an existing manifest instead of preserving indexed labels"); p.set_defaults(func=cmd_ingest)
    p = sub.add_parser("batch", help="select a deterministic resumable batch")
    p.add_argument("--manifest", required=True); p.add_argument("--output"); p.add_argument("--request-output"); p.add_argument("--batch-id"); p.add_argument("--offset", type=int, default=0); p.add_argument("--limit", type=int, default=32); p.add_argument("--statuses", default="pending,partial,error"); p.set_defaults(func=cmd_batch)
    p = sub.add_parser("run-batch", help="verify an externally downloaded batch and advance checkpoint")
    p.add_argument("--manifest", required=True); p.add_argument("--batch", required=True); p.add_argument("--downloads"); p.add_argument("--labels"); p.add_argument("--batch-id"); p.add_argument("--output-dir"); p.add_argument("--report"); p.set_defaults(func=cmd_run_batch)
    p = sub.add_parser("apply", help="merge validated thumbnail/vision labels")
    p.add_argument("--manifest", required=True); p.add_argument("--labels", required=True); p.add_argument("--report"); p.add_argument("--batch-id"); p.set_defaults(func=cmd_apply)
    p = sub.add_parser("report", help="summarize manifest progress")
    p.add_argument("--manifest", required=True); p.add_argument("--output"); p.set_defaults(func=cmd_report)
    args = parser.parse_args()
    try: args.func(args)
    except ValueError as exc: print(f"error: {exc}", file=sys.stderr); return 2
    return 0

if __name__ == "__main__": raise SystemExit(main())
