# 云盘索引产物

索引完成后可以把索引产物上传到中国移动云盘，但只上传到 2.0 的智能体专属目录，不改变原照片的位置。

## 目录布局

先通过 `cmcloud files list --rootScope dedicated` 取得真实专属根引用，再创建或复用 `.cloud-photo` 目录：

```text
<智能体专属目录>/.cloud-photo/
  manifest-<scan_id>.jsonl
  checkpoint-<scan_id>.json
  report-<scan_id>.json
```

`scan_id` 使用一次扫描的稳定 ID。每次更新生成新版本文件，不覆盖旧文件；这样可以在上传结果未知时保留可核对的历史版本。原照片仍以用户个人云中的原文件为事实来源，manifest 的 `source_ref.file_id` 指向原照片。

## 上传顺序

1. 本地完成批次合并和 schema 校验。
2. 取得或复用专属目录的真实 `dirRef`。
3. 由 `cmcloud files mkdir` 创建 `.cloud-photo`（不存在时）。
4. 使用 `cmcloud files upload` 依次上传 manifest、checkpoint 和报告。
5. 每个上传动作都走一次统一确认计划；结果未知时按 `operation.status` 核对，不重传。
6. 保存上传回执中的真实文件引用，下一轮优先读取最新 `manifest-*` 文件，并用 `scan_id` 和更新时间核对版本。

上传的索引文件不包含授权令牌、临时下载 URL 或图片二进制；只包含元数据、三类标签、稳定文件引用和处理状态。

## 读取策略

- 当前运行有本地 manifest 且版本未变化时，可直接使用本地缓存。
- 新会话或本地索引缺失时，从 `.cloud-photo` 目录读取最近一次完整 manifest。
- manifest 不完整或 schema 校验失败时，不把它当作全量索引；回退到 checkpoint 继续增量索引。
