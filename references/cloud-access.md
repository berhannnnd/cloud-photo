# cloud-access 模块

该模块只负责访问边界，不实现中国移动云盘 API。所有云盘操作通过已安装的 `cm-cloud-manage` 完成：登录状态检查、目录分页、文件元数据、缩略图/临时图片引用和按文件 ID 重新读取。

## 输出给 photo-index 的最小记录

```json
{"asset_id":"cm:file-id","source_ref":{"provider":"cm-cloud-manage","file_id":"file-id","path":"/照片/2026/IMG.JPG"},"file_metadata":{}}
```

不要把访问令牌、cookie、二维码或临时下载 URL 写入 manifest。临时 URL 只在当前批次内使用，过期后按 `file_id` 重新取得。工作区目录建议：

```text
.cloud-photo/
  manifest.jsonl
  checkpoints/<scan-id>.json
  batches/<batch-id>.jsonl
  thumbnails/<asset-id>.<ext>
  reports/<scan-id>.json
```

访问模块的变更必须只影响 `packages/cloud-access/`，并保持上述输出契约不变。
