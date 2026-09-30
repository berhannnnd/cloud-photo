# 可恢复索引 runner

`index_runner.py` 预先实现索引编排；它不登录云盘、不拼接云盘 HTTP，也不调用模型。云盘清单和图片下载仍由 `cm-cloud-manage` 提供，模型输出以 JSONL 交给 runner 合并。

## 阶段

```bash
python3 scripts/index_runner.py ingest \
  --input cloud-listing.jsonl \
  --output-dir .cloud-photo \
  --scope dedicated:/drive

python3 scripts/index_runner.py batch \
  --manifest .cloud-photo/manifest.jsonl \
  --output .cloud-photo/batches/batch-001.jsonl \
  --request-output .cloud-photo/batches/batch-001.download.json \
  --batch-id batch-001 \
  --limit 32

python3 scripts/index_runner.py run-batch \
  --manifest .cloud-photo/manifest.jsonl \
  --batch .cloud-photo/batches/batch-001.jsonl \
  --downloads .cloud-photo/batches/batch-001.downloads.jsonl \
  --batch-id batch-001 \
  --output-dir .cloud-photo/batches/batch-001

python3 scripts/index_runner.py apply \
  --manifest .cloud-photo/manifest.jsonl \
  --labels .cloud-photo/batches/batch-001.labels.jsonl \
  --report .cloud-photo/reports/batch-001.json

python3 scripts/index_runner.py report \
  --manifest .cloud-photo/manifest.jsonl \
  --output .cloud-photo/reports/latest.json
```

- `ingest` 只保留图片（可用 `--include-non-images` 改变），按稳定文件引用生成 manifest 和 checkpoint。云盘 `fileRef` 轮换时，若当前清单能唯一匹配旧记录的 `(provider, path)` 或 `source_hash`，会沿用旧 `asset_id` 并只更新当前 `file_id`；无法唯一匹配时不会猜测合并。输出目录已有 manifest 时，默认保留同一 `asset_id` 已完成的三类标签和状态，只刷新云盘元数据；源哈希明确变化才重置该条记录。确实要从头重建时显式加 `--reset`。
- `batch` 按 manifest 的稳定顺序只选 `pending/partial/error`，`next_offset` 是原 manifest 行号游标，不是“当前未完成列表”的下标；因此前面批次完成后继续使用返回的 `next_offset` 不会跳过记录。需要重试较早失败项时从 `--offset 0` 重新取批次。
- `run-batch` 接收云盘 Skill 返回的下载结果，校验本地文件、生成缩略图任务清单，并推进 checkpoint；它不读取凭据、不调用云盘 API。
- `apply` 只接受三类标签，按 `asset_id` 合并；同批只允许每个资产出现一次。只提交一类派生标签时标记 `partial`，同时提交 `thumbnail_tags` 和 `vision_tags` 才默认标记 `complete`；未知资产不会写入，并记录已处理资产和批次。
- `report` 输出 pending、complete、partial、error 数量；展示时先用 `scripts/preview_pack.py markdown` 生成每批最多 6 张的 `.cloud-photo/...` 工作区图片画廊并放入回复。需要在 `show_widget` 中展示图片时，先通过 `preview_server.py start` 复用共享 relay 并注册当前 session，再用 `preview_pack.py widget` 生成 relay URL；结构化进度和标签分布可放在同一个 widget，但只有确认图片实际渲染后才算完成，并同步写入交付报告。

模型侧只需为每条记录返回：

```json
{"asset_id":"cm:...","thumbnail_tags":{"scene_hints":["outdoor"]},"vision_tags":{"subjects":["cat"]}}
```

不要在 labels 文件中写入置信度或临时下载 URL。实际图片下载由宿主按 `*.download.json` 批次请求调用 `cm-cloud-manage`；把结果写成 `downloads.jsonl` 后运行 `run-batch`。每批完成后立即生成 labels 并调用 `apply`，不要等待整库下载完毕。不要另写全量扫描、批次切分或 checkpoint 脚本。
