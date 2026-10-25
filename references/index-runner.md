# 可恢复索引 runner

`index_runner.py` 预先实现索引编排；它不登录云盘、不拼接云盘 HTTP，也不调用模型。云盘清单和图片下载仍由 `cm-cloud-manage` 提供，模型输出以 JSONL 交给 runner 合并。

## 输入适配

runner 使用独立的逐行 JSONL 读取器。先从公开 CLI 的列表信封提取 `data.items`，补齐并规范化路径，将所需扫描范围的成员写成一行一个对象的清单；不能直接把完整信封或多行格式化 JSON 传给 ingest。下载回执也须映射回本批 asset_id，再写为下列 JSONL：

```json
{"asset_id":"cm:example","status":"downloaded","local_path":"/absolute/workspace/downloads/IMG.JPG"}
```

这里的 status 是 runner 的输入格式，不是云盘信封的顶层状态。映射只采用真实成功项和存在的本地文件；失败项不能伪装为 downloaded。当前尚无自动完成该投影的云盘 CLI 适配器。

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

- `ingest` 只保留图片（可用 `--include-non-images` 改变），首次以当前引用生成 asset_id。引用轮换时会尝试按唯一 `(provider, path)` 或 source_hash 复用旧 ID；路径缺失时当前代码会退化到名称，因此适配层须先补查路径，不能把这种匹配当可靠身份校验。输出已有 manifest 时保留同一资产的标签与状态，源哈希明确变化才重置；takenAt 当前尚未写入 file_metadata。完整身份和时间字段修正见 [接入设计](mclaw-integration.md)。确实从头重建时显式加 `--reset`。
- `batch` 按 manifest 的稳定顺序只选 `pending/partial/error`，`next_offset` 是原 manifest 行号游标，不是“当前未完成列表”的下标；因此前面批次完成后继续使用返回的 `next_offset` 不会跳过记录。需要重试较早失败项时从 `--offset 0` 重新取批次。
- `run-batch` 接收云盘 Skill 返回的下载结果，校验本地文件、生成缩略图任务清单，并推进 checkpoint；它不读取凭据、不调用云盘 API。
- `apply` 只接受三类标签，按 `asset_id` 合并；同批只允许每个资产出现一次。只提交一类派生标签时标记 `partial`，同时提交 `thumbnail_tags` 和 `vision_tags` 才默认标记 `complete`；未知资产不会写入，并记录已处理资产和批次。
- `report` 输出 pending、complete、partial、error 数量；进度和预览由宿主实际支持的媒体/任务通道交付，见 [preview.md](preview.md)。`preview_pack.py build` 只生成静态图片，不负责发送或客户端渲染。

模型侧只需为每条记录返回：

```json
{"asset_id":"cm:...","thumbnail_tags":{"scene_hints":["outdoor"]},"vision_tags":{"subjects":["cat"]}}
```

不要在 labels 文件中写入置信度或临时下载 URL。实际图片下载由宿主按 `*.download.json` 批次请求调用 `cm-cloud-manage`；把结果写成 `downloads.jsonl` 后运行 `run-batch`。每批完成后立即生成 labels 并调用 `apply`，不要等待整库下载完毕。不要另写全量扫描、批次切分或 checkpoint 脚本。
