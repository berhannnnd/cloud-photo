# Photo manifest schema

清单采用 JSONL，一行一个照片资产。根对象必须包含以下字段：

```json
{
  "schema_version": "cloud-photo/v1",
  "asset_id": "stable-id",
  "source_ref": {"provider": "cm-cloud-manage", "file_id": "<current-fileRef>", "path": "/照片/IMG_0001.JPG"},
  "file_metadata": {
    "name": "IMG_0001.JPG", "mime_type": "image/jpeg", "size_bytes": 1234,
    "modified_at": "2026-09-30T08:00:00Z", "width": 4032, "height": 3024,
    "created_at": "2026-09-29T08:00:00Z"
  },
  "thumbnail_tags": {
    "orientation": "landscape", "dominant_colors": ["green"],
    "scene_hints": ["outdoor"], "ocr_text": []
  },
  "vision_tags": {
    "subjects": ["cat"], "actions": ["sitting"], "scene": ["garden"],
    "time": ["day"], "people": [], "objects": ["flower"]
  },
  "index_state": {"status": "complete", "updated_at": "2026-09-30T08:01:00Z", "source_hash": "sha256:..."}
}
```

`asset_id` 用于本地索引身份。现有 v1 的 `source_ref.file_id` 是兼容字段，runner 会把云盘 `fileRef` 存入其中；它不保证是永久业务 ID。当前云盘引用会过期且跨调用变化，长期映射与刷新要求见 [cloud-access.md](cloud-access.md)。不要为了取得原始 ID 读取云盘内部台账。

`file_metadata`、`thumbnail_tags` 和 `vision_tags` 是唯一允许的标签分组。未能取得的值使用空数组、空字符串或 `null`，不要猜测。拍摄时间与上传时间必须区分；当前 ingest 尚未保留云盘 takenAt，接入分类前需补齐。`index_state.status` 可为 `pending`、`partial`、`complete` 或 `error`；错误写入 `index_state.error_code` 和 `index_state.error_message`，不得把错误记录伪装成完成。

工具会拒绝未知顶层字段、未知标签分组、缺少稳定身份、重复 `asset_id`、非法 JSONL 或不符合类型的值。
