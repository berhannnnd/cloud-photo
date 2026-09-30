#!/usr/bin/env python3
"""Deterministic manifest validation, merge, and search for the cloud-photo skill."""
from __future__ import annotations
import argparse, json, pathlib, re, sys, tempfile

SCHEMA = "cloud-photo/v1"
GROUPS = {"file_metadata", "thumbnail_tags", "vision_tags"}
STATUSES = {"pending", "partial", "complete", "error"}
REQUIRED = {"schema_version", "asset_id", "source_ref", "file_metadata", "thumbnail_tags", "vision_tags", "index_state"}

def fail(message: str) -> None: raise ValueError(message)

def validate_record(obj: object, line: int = 0) -> dict:
    if not isinstance(obj, dict): fail(f"line {line}: record must be an object")
    unknown = set(obj) - REQUIRED; missing = REQUIRED - set(obj)
    if unknown: fail(f"line {line}: unknown fields: {sorted(unknown)}")
    if missing: fail(f"line {line}: missing fields: {sorted(missing)}")
    if obj["schema_version"] != SCHEMA: fail(f"line {line}: schema_version must be {SCHEMA}")
    if not isinstance(obj["asset_id"], str) or not obj["asset_id"].strip(): fail(f"line {line}: asset_id must be non-empty")
    if not isinstance(obj["source_ref"], dict): fail(f"line {line}: source_ref must be an object")
    for key in ("provider", "file_id"):
        if not isinstance(obj["source_ref"].get(key), str) or not obj["source_ref"][key]: fail(f"line {line}: source_ref.{key} required")
    for group in GROUPS:
        if not isinstance(obj[group], dict): fail(f"line {line}: {group} must be an object")
        for key, value in obj[group].items():
            if not isinstance(key, str): fail(f"line {line}: {group} keys must be strings")
            if not isinstance(value, (str, int, float, bool, list)) and value is not None: fail(f"line {line}: invalid value in {group}.{key}")
            if isinstance(value, list) and not all(isinstance(x, (str, int, float, bool)) or x is None for x in value): fail(f"line {line}: invalid list in {group}.{key}")
    state = obj["index_state"]
    if not isinstance(state, dict): fail(f"line {line}: index_state must be an object")
    if state.get("status") not in STATUSES: fail(f"line {line}: index_state.status must be one of {sorted(STATUSES)}")
    return obj

def read_manifest(path: pathlib.Path) -> list[dict]:
    records, seen = [], set()
    if not path.exists(): fail(f"manifest not found: {path}")
    with path.open(encoding="utf-8") as fh:
        for number, raw in enumerate(fh, 1):
            if not raw.strip(): continue
            try: obj = json.loads(raw)
            except json.JSONDecodeError as exc: fail(f"line {number}: invalid JSON: {exc.msg}")
            record = validate_record(obj, number)
            if record["asset_id"] in seen: fail(f"line {number}: duplicate asset_id {record['asset_id']}")
            seen.add(record["asset_id"]); records.append(record)
    return records

def write_manifest(path: pathlib.Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            for record in records: fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            fh.flush()
        pathlib.Path(tmp).replace(path)
    except Exception:
        pathlib.Path(tmp).unlink(missing_ok=True); raise

def terms(query: str) -> list[str]: return [p for p in re.findall(r"[\w\u3400-\u9fff]+", query.casefold()) if p]
def searchable(record: dict) -> str: return json.dumps(record, ensure_ascii=False, sort_keys=True).casefold()

def read_json_records(path: pathlib.Path) -> list[dict]:
    """Read JSON/JSONL produced by cm-cloud without assuming one envelope."""
    if not path.exists(): fail(f"input not found: {path}")
    raw = path.read_text(encoding="utf-8")
    if not raw.strip(): return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        # cm-cloud may prefix a JSON receipt with auth/diagnostic lines. Parse
        # the first complete JSON value before falling back to JSONL.
        value = None
        for marker in ("{", "["):
            start = raw.find(marker)
            if start < 0: continue
            try:
                value, _ = json.JSONDecoder().raw_decode(raw[start:])
                break
            except json.JSONDecodeError:
                continue
        if value is not None:
            raw = json.dumps(value, ensure_ascii=False)
        else:
            rows = []
            for number, line in enumerate(raw.splitlines(), 1):
                if not line.strip(): continue
                try: item = json.loads(line)
                except json.JSONDecodeError as exc: fail(f"{path}:{number}: invalid JSON: {exc.msg}")
                rows.append(item)
            return rows
    if isinstance(value, list): return value
    if isinstance(value, dict):
        data = value.get("data")
        if isinstance(data, dict) and isinstance(data.get("items"), list): return data["items"]
        for key in ("items", "results", "candidates", "assets"):
            if isinstance(value.get(key), list): return value[key]
        return [value]
    fail(f"{path}: expected JSON object, array, or JSONL")

def cmd_resolve_refs(args):
    """Resolve current cloud refs immediately before a write operation.

    A name-only match is accepted only when unique. Ambiguous/missing records
    remain explicit so callers cannot accidentally copy the wrong photo.
    """
    listing = [item for item in read_json_records(pathlib.Path(args.listing)) if isinstance(item, dict)]
    requested = [item for item in read_json_records(pathlib.Path(args.items)) if isinstance(item, dict)]
    by_path: dict[str, list[dict]] = {}; by_name: dict[str, list[dict]] = {}
    for item in listing:
        ref = item.get("fileRef") or item.get("file_id") or item.get("id")
        if not ref: continue
        name = str(item.get("name") or item.get("file_name") or "")
        path = str(item.get("path") or item.get("namePath") or "")
        if path: by_path.setdefault(path, []).append(item)
        if name: by_name.setdefault(name, []).append(item)
    resolved = []; counts = {"resolved": 0, "ambiguous": 0, "missing": 0}
    for item in requested:
        wanted_path = str(item.get("path") or (item.get("source_ref") or {}).get("path") or "")
        wanted_name = str(item.get("name") or (item.get("file_metadata") or {}).get("name") or pathlib.Path(wanted_path).name)
        matches = by_path.get(wanted_path, []) if wanted_path else []
        if not matches: matches = by_name.get(wanted_name, []) if wanted_name else []
        if len(matches) == 1:
            current = matches[0]
            resolved.append({"asset_id": item.get("asset_id"), "status": "resolved", "name": current.get("name"), "path": current.get("path") or current.get("namePath") or wanted_path, "fileRef": current.get("fileRef") or current.get("file_id") or current.get("id")})
            counts["resolved"] += 1
        elif len(matches) > 1:
            resolved.append({"asset_id": item.get("asset_id"), "status": "ambiguous", "name": wanted_name, "path": wanted_path, "candidates": [m.get("fileRef") or m.get("file_id") or m.get("id") for m in matches]})
            counts["ambiguous"] += 1
        else:
            resolved.append({"asset_id": item.get("asset_id"), "status": "missing", "name": wanted_name, "path": wanted_path})
            counts["missing"] += 1
    output = {"schema_version": "cloud-photo/ref-resolution/v1", "counts": counts, "items": resolved}
    if args.output:
        target = pathlib.Path(args.output); target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))

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
    records = read_manifest(pathlib.Path(args.manifest)); wanted = terms(args.query)
    if not wanted: fail("query must contain at least one term")
    hits = []
    for record in records:
        hay = searchable(record); score = sum(hay.count(term) for term in wanted)
        if score: hits.append((score, record))
    hits.sort(key=lambda pair: (-pair[0], pair[1]["asset_id"]))
    candidates = [{"asset_id": r["asset_id"], "source_ref": r["source_ref"], "file_metadata": r["file_metadata"]} for _, r in hits[:args.limit]]
    actions = [{"asset_id": item["asset_id"], "action": "review_then_apply", "target": args.target} for item in candidates]
    print(json.dumps({"mode": "organize", "query": args.query, "target": args.target, "candidates": candidates, "proposed_actions": actions, "needs_confirmation": True}, ensure_ascii=False, indent=2))

def cmd_dependency_status(args):
    path = pathlib.Path(args.path)
    meta = path / "_meta.json"
    if not meta.exists(): fail(f"dependency metadata not found: {meta}")
    try: data = json.loads(meta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc: fail(f"invalid dependency metadata: {exc.msg}")
    result = {"dependency": "@org-vt43r0t0/cm-cloud-manage", "installed_version": data.get("version"), "expected_version": args.expected, "compatible": (not args.expected or data.get("version") == args.expected), "path": str(path)}
    print(json.dumps(result, ensure_ascii=False))

def cmd_search(args):
    records = read_manifest(pathlib.Path(args.manifest)); wanted = terms(args.query)
    if not wanted: fail("query must contain at least one term")
    hits = []
    for record in records:
        hay = searchable(record); score = sum(hay.count(term) for term in wanted)
        if score: hits.append((score, record))
    hits.sort(key=lambda pair: (-pair[0], pair[1]["asset_id"]))
    result = [{"score": score, "asset_id": record["asset_id"], "source_ref": record["source_ref"], "file_metadata": record["file_metadata"], "thumbnail_tags": record["thumbnail_tags"], "vision_tags": record["vision_tags"]} for score, record in hits[:args.limit]]
    print(json.dumps({"query": args.query, "terms": wanted, "count": len(result), "results": result}, ensure_ascii=False, indent=2))

def main():
    parser = argparse.ArgumentParser(description="cloud-photo manifest tool"); sub = parser.add_subparsers(dest="command", required=True)
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
    args = parser.parse_args()
    try: args.func(args)
    except ValueError as exc: print(f"error: {exc}", file=sys.stderr); return 2
    return 0

if __name__ == "__main__": raise SystemExit(main())
