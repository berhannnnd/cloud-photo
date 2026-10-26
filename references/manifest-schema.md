# Photo manifest schema

清单采用 JSONL，一行一个照片资产。根对象必须包含以下字段：

```json
{
  "schema_version": "cloud-photo/v1",
  "asset_id": "stable-id",
  "source_ref": {"provider": "cm-cloud-manage", "file_id": "<current-fileRef>", "path": "/照片/IMG_0001.JPG", "ref_observed_at": "2026-09-30T08:00:00+00:00"},
  "file_metadata": {
    "name": "IMG_0001.JPG", "mime_type": "image/jpeg", "size_bytes": 1234,
    "modified_at": "2026-09-30T08:00:00Z", "width": 4032, "height": 3024,
    "created_at": "2026-09-29T08:00:00Z", "taken_at": "2026-09-28T10:00:00+08:00"
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

派生字段（均在 file_metadata 下，缺失为 null 或不出现）：

| 字段 | 来源 | 说明 |
| --- | --- | --- |
| `folder` | ingest，云盘规范路径 | 父目录，根目录为 `/` |
| `capture_device` / `capture_device_evidence` / `capture_device_basis` | ingest/apply 规则推断 | phone/camera/capture；未知为 null，basis 为 rule-inference |
| `save_channel` / `save_channel_evidence` / `save_channel_basis` | ingest/apply 规则推断 | screenshot/wechat/qq/download；与设备独立，不证明传输历史 |
| `source_kind` / `source_evidence` | ingest 与 apply 时由 `provenance.py` 重算 | 见 [照片来源](photo-index.md#照片来源)；兼容旧查询，新查询使用拆分字段；未命中规则为 null |
| `camera_make` / `camera_model` / `software` | media-prepare，EXIF | 原样保存，去除空白 |
| `gps_lat` / `gps_lon` / `gps_source` | media-prepare，EXIF GPS | 十进制度，保留 6 位；方向必须为 N/S 与 E/W，度分秒须有限且范围合法；(0,0)、不完整和越界值丢弃 |
| `geo_cell_3` / `geo_cell_4` / `geo_cell_5` | 由 GPS 计算的 geohash 前缀 | 不同精度网格，尺寸随纬度变化；不代表城市/景点边界 |

`asset_id` 用于本地索引身份。现有 v1 的 `source_ref.file_id` 是兼容字段，runner 会把云盘 `fileRef` 存入其中；它不保证是永久业务 ID。当前云盘引用会过期且跨调用变化，长期映射与刷新要求见 [cloud-access.md](cloud-access.md)。不要为了取得原始 ID 读取云盘内部台账。

`file_metadata`、`thumbnail_tags` 和 `vision_tags` 是唯一允许的标签分组。未能取得的值使用空数组、空字符串或 `null`，不要猜测。拍摄时间与上传时间必须区分；ingest 保留云盘 takenAt 为 taken_at；media-prepare 可补 EXIF 时间，缺时区须保留为本地时钟。`index_state.status` 可为 `pending`、`partial`、`complete` 或 `error`；错误写入 `index_state.error_code` 和 `index_state.error_message`，不得把错误记录伪装成完成。

工具会拒绝未知顶层字段、未知标签分组、缺少稳定身份、重复 `asset_id`、非法 JSONL 或不符合类型的值。

本地 asset_id 首次导入时独立生成，不由临时 fileRef 直接组成。源大小/修改时间/哈希变化会使旧标签失效。file_metadata.sha256 仅来自真实本地原图；index_state 可保存 vision_source、vision_revision。
