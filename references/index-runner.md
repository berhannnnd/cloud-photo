# 本地索引流水线

状态位于宿主用户持久工作区。Python 负责存储与批次，模型负责视觉标签，云盘 Skill 负责原文件读取。

## 1. 扫描与导入

filters.json 示例：`{"typeList":["1"],"pageSize":100}`。可以增加云盘支持的时间/目录等公开条件；按实际 schema 使用，不能假定 search 有目录参数。

```bash
python3 scripts/cloud_photo.py cloud-scan --skill-dir "$CM_SKILL" --filters filters.json --output "$STATE/scan.json"
# 若达到页数预算或中断，保持身份/条件不变续接
python3 scripts/cloud_photo.py cloud-scan --skill-dir "$CM_SKILL" --filters filters.json --output "$STATE/scan.json" --resume
python3 scripts/index_runner.py ingest --input "$STATE/scan.json" --output-dir "$STATE" --scope personal-images
```

scan 每页保存进度；逐项 info 补路径，避免详情重新签发引用导致错误关联。当前采用逐图详情调用，吞吐量取决于云盘网络；大库应分明确范围。失败/未完成信封不能直接 ingest。旧 JSONL 清单依然支持，调用方负责证明其范围与完整性。

ingest 使用本地随机 asset_id，引用轮换时只在唯一规范路径与文件指纹一致时保留身份。同名不合并，哈希相同但路径不同不合并。已知文件发生大小/修改时间或哈希变化时重置标签。增量导入保留未出现的旧成员，不把分页遗漏当删除；--reset 用于明确重建选定范围。不同账号/范围需不同工作区。

## 2. 取图与本地处理

```bash
python3 scripts/index_runner.py batch --manifest "$STATE/manifest.jsonl" --output "$STATE/batch.jsonl" --request-output "$STATE/batch.request.json" --batch-id batch-001 --limit 16
python3 scripts/cloud_photo.py cloud-download --skill-dir "$CM_SKILL" --batch "$STATE/batch.jsonl" --directory "$STATE/downloads" --output "$STATE/downloads.jsonl"
python3 scripts/cloud_photo.py media-prepare --downloads "$STATE/downloads.jsonl" --directory "$STATE/media/batch-001"
python3 scripts/index_runner.py apply --manifest "$STATE/manifest.jsonl" --labels "$STATE/media/batch-001/metadata.labels.jsonl"
```

download 最多 100 项，按回执 itemIndex 关联原成员，不按返回的新 fileRef 或文件名猜测。默认 fail 防止覆盖已有文件；失败项不会成为视觉任务。media-prepare 生成 768 像素边界缩略图、尺寸、方向、原图 SHA-256、可用 EXIF 拍摄时间及视觉任务；不自动识别场景、人脸、OCR 或质量。不能解码的 HEIC 等格式记录失败，须先配置解码能力。

## 3. 模型标签与恢复

宿主模型读取 vision.tasks.jsonl 中实际缩略图，按 [标签规范](photo-index.md) 生成 vision.labels.jsonl。通过用户授权的宿主图片能力运行，不配置第二套模型密钥。

```bash
python3 scripts/index_runner.py apply --manifest "$STATE/manifest.jsonl" --labels "$STATE/vision.labels.jsonl" --batch-id batch-001
python3 scripts/index_runner.py report --manifest "$STATE/manifest.jsonl" --output "$STATE/report.json"
```

batch 只选 pending/partial/error。下一批 offset 使用命令实际返回的 next_offset；重试较早失败项从 offset 0 开始。apply 校验三类字段并记录标签来源/版本，不明资产不会写入。已有索引的相应标签可用于局部检索，不需等全库完成；必须说明实际覆盖范围。run-batch 仍兼容外部下载映射，提交 labels 时仅允许本批真实可读取成员。

本地状态默认不上传。用户明确要求备份时才按 [cloud-artifacts.md](cloud-artifacts.md) 操作。
