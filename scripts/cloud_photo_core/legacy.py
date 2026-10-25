#!/usr/bin/env python3
"""Deterministic manifest validation, merge, and search for the cloud-photo skill."""
from __future__ import annotations
import argparse, json, pathlib, re, sys, tempfile

from .manifest import SCHEMA, GROUPS, fail, read_manifest, write_manifest, validate_record

def terms(query: str) -> list[str]: return [p for p in re.findall(r"[\w\u3400-\u9fff]+", query.casefold()) if p]
def searchable(record: dict) -> str: return json.dumps({key: record[key] for key in GROUPS}, ensure_ascii=False, sort_keys=True).casefold()

def read_json_records(path):
    from .storage import records
    return records(path)

def cmd_resolve_refs(args):
    from .assets import resolve
    from .storage import atomic
    result = resolve(read_json_records(args.items), read_json_records(args.listing))
    if args.output:
        atomic(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))

def cmd_init(args):
    path = pathlib.Path(args.output)
    if path.exists() and not args.force: fail(f"refusing to overwrite {path}; use --force")
    write_manifest(path, [])
    print(json.dumps({"manifest": str(path), "records": 0, "schema_version": SCHEMA}, ensure_ascii=False))

def cmd_validate(args):
    records = read_manifest(pathlib.Path(args.manifest))
    print(json.dumps({"manifest": args.manifest, "records": len(records), "valid": True, "schema_version": SCHEMA}, ensure_ascii=False))

def cmd_merge(args):
    base = read_manifest(pathlib.Path(args.base)) if pathlib.Path(args.base).exists() else []
    delta = read_manifest(pathlib.Path(args.delta)); merged = {r["asset_id"]: r for r in base}
    for record in delta: merged[record["asset_id"]] = record
    records = sorted(merged.values(), key=lambda r: r["asset_id"]); write_manifest(pathlib.Path(args.output), records)
    print(json.dumps({"manifest": args.output, "records": len(records), "replaced": len(delta)}, ensure_ascii=False))

def cmd_mode_detect(args):
    text = args.text
    index_words = ("索引", "扫描", "打标签", "建立照片库", "更新索引")
    organize_words = ("整理", "归类", "移动", "归档", "创建相册", "放到相册", "重命名")
    has_index = any(word in text for word in index_words)
    has_organize = any(word in text for word in organize_words)
    mode = "index" if has_index and not has_organize else "organize" if has_organize else "search"
    prerequisite = mode == "organize" and has_index
    print(json.dumps({"mode": mode, "index_prerequisite": prerequisite, "write_operations": False}, ensure_ascii=False))

def cmd_plan(args):
    if args.limit < 1: fail("limit must be positive")
    records = read_manifest(pathlib.Path(args.manifest)); wanted = terms(args.query)
    if not wanted: fail("query must contain at least one term")
    hits = []
    for record in records:
        hay = searchable(record); score = sum(hay.count(term) for term in wanted)
        if score: hits.append((score, record))
    hits.sort(key=lambda pair: (-pair[0], pair[1]["asset_id"]))
    candidates = [{"asset_id": r["asset_id"], "source_ref": r["source_ref"], "file_metadata": r["file_metadata"]} for _, r in hits[:args.limit]]
    actions = [{"asset_id": item["asset_id"], "action": "review_then_apply", "target": args.target} for item in candidates]
    print(json.dumps({"mode": "organize", "kind": "legacy-draft", "executable": False, "total": len(hits), "complete": len(candidates) == len(hits), "next_command": "query/group-plan", "query": args.query, "target": args.target, "candidates": candidates, "proposed_actions": actions, "needs_confirmation": True}, ensure_ascii=False, indent=2))

def cmd_dependency_status(args):
    path = pathlib.Path(args.path)
    meta = path / "_meta.json"
    if not meta.exists(): fail(f"dependency metadata not found: {meta}")
    try: data = json.loads(meta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc: fail(f"invalid dependency metadata: {exc.msg}")
    result = {"dependency": "@org-vt43r0t0/cm-cloud-manage", "installed_version": data.get("version"), "expected_version": args.expected, "compatible": (not args.expected or data.get("version") == args.expected), "path": str(path)}
    print(json.dumps(result, ensure_ascii=False))

def cmd_search(args):
    if args.limit < 1: fail("limit must be positive")
    records = read_manifest(pathlib.Path(args.manifest)); wanted = terms(args.query)
    if not wanted: fail("query must contain at least one term")
    hits = []
    for record in records:
        hay = searchable(record); score = sum(hay.count(term) for term in wanted)
        if score: hits.append((score, record))
    hits.sort(key=lambda pair: (-pair[0], pair[1]["asset_id"]))
    result = [{"score": score, "asset_id": record["asset_id"], "source_ref": record["source_ref"], "file_metadata": record["file_metadata"], "thumbnail_tags": record["thumbnail_tags"], "vision_tags": record["vision_tags"]} for score, record in hits[:args.limit]]
    print(json.dumps({"query": args.query, "terms": wanted, "count": len(result), "total": len(hits), "complete": len(result) == len(hits), "results": result}, ensure_ascii=False, indent=2))

def register(sub):
    p = sub.add_parser("init"); p.add_argument("--output", required=True); p.add_argument("--force", action="store_true"); p.set_defaults(func=cmd_init)
    p = sub.add_parser("validate"); p.add_argument("manifest"); p.set_defaults(func=cmd_validate)
    p = sub.add_parser("merge"); p.add_argument("--base", required=True); p.add_argument("--delta", required=True); p.add_argument("--output", required=True); p.set_defaults(func=cmd_merge)
    p = sub.add_parser("mode-detect"); p.add_argument("--text", required=True); p.set_defaults(func=cmd_mode_detect)
    p = sub.add_parser("plan"); p.add_argument("manifest"); p.add_argument("--query", required=True); p.add_argument("--target", required=True); p.add_argument("--limit", type=int, default=20); p.add_argument("--format", choices=("json",), default="json", help="accepted for CLI compatibility"); p.set_defaults(func=cmd_plan)
    p = sub.add_parser("dependency-status"); p.add_argument("--path", required=True); p.add_argument("--expected"); p.set_defaults(func=cmd_dependency_status)
    p = sub.add_parser("resolve-refs", help="resolve fresh cm-cloud fileRefs before a write")
    p.add_argument("--listing", required=True, help="fresh cm-cloud list JSON/JSONL")
    p.add_argument("--items", required=True, help="candidate items JSON/JSONL")
    p.add_argument("--output")
    p.set_defaults(func=cmd_resolve_refs)
    p = sub.add_parser("search"); p.add_argument("manifest"); p.add_argument("--query", required=True); p.add_argument("--limit", type=int, default=20); p.add_argument("--format", choices=("json",), default="json", help="accepted for CLI compatibility"); p.set_defaults(func=cmd_search)
