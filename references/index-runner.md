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

- `ingest` 只保留图片（可用 `--include-non-images` 改变），按稳定文件引用生成 `pending` manifest 和 checkpoint。
- `batch` 按 `asset_id` 稳定排序，只选 `pending/partial/error`，同时生成给 `cm-cloud-manage` 使用的下载请求和下一批游标；中断后可用同一 manifest 继续。
- `run-batch` 接收云盘 Skill 返回的下载结果，校验本地文件、生成缩略图任务清单，并推进 checkpoint；它不读取凭据、不调用云盘 API。
- `apply` 只接受三类标签，按 `asset_id` 合并，默认在有标签时标记 `complete`；未知资产不会写入，并记录已处理资产和批次。
- `report` 输出 pending、complete、partial、error 数量，用于 `show_widget` 和交付报告。

模型侧只需为每条记录返回：

```json
{"asset_id":"cm:...","thumbnail_tags":{"scene_hints":["outdoor"]},"vision_tags":{"subjects":["cat"]}}
```

不要在 labels 文件中写入置信度或临时下载 URL。实际图片下载由宿主按 `*.download.json` 批次请求调用 `cm-cloud-manage`；把结果写成 `downloads.jsonl` 后运行 `run-batch`。每批完成后立即生成 labels 并调用 `apply`，不要等待整库下载完毕。不要另写全量扫描、批次切分或 checkpoint 脚本。
