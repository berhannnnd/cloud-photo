"""Canonical manifest validation and atomic JSONL writes."""
import json, os, pathlib, tempfile

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
            os.fsync(fh.fileno())
        pathlib.Path(tmp).replace(path)
    except Exception:
        pathlib.Path(tmp).unlink(missing_ok=True); raise
