# 本地索引流水线

状态位于宿主用户持久工作区。Python 负责存储与批次，模型负责视觉标签，云盘 Skill 负责原文件读取。

## 1. 扫描与导入

扫描用户指定目录时使用 `--source list`，filters.json 为 `{"folderRef":"<真实目录引用>","pageSize":100}`，只读取该目录直接成员。目录路径由公开列表回执提供，无需逐图查详情。子目录需要明确另行扫描；递归时仍按实际详情确认路径。

全库或条件搜索使用默认 `--source search`，filters.json 示例：`{"typeList":["1"],"pageSize":100}`。可以增加云盘支持的时间/目录等公开条件；按实际 schema 使用，不能假定 search 有目录参数。

```bash
python3 scripts/cloud_photo.py cloud-scan --skill-dir "$CM_SKILL" --filters filters.json --output "$STATE/scan.json"
# 若达到页数预算或中断，保持身份/条件不变续接
python3 scripts/cloud_photo.py cloud-scan --skill-dir "$CM_SKILL" --filters filters.json --output "$STATE/scan.json" --resume
python3 scripts/index_runner.py ingest --input "$STATE/scan.json" --output-dir "$STATE" --scope personal-images
```

scan 每页保存进度；搜索模式逐项 info 补路径，避免详情重新签发引用导致错误关联。当前采用逐图详情调用，吞吐量取决于云盘网络；大库应分明确范围。失败/未完成信封不能直接 ingest。旧 JSONL 清单依然支持，调用方负责证明其范围与完整性。

ingest 使用本地随机 asset_id，引用轮换时只在唯一规范路径与文件指纹一致时保留身份。同名不合并，哈希相同但路径不同不合并。已知文件发生大小/修改时间或哈希变化时重置标签。增量导入保留未出现的旧成员，不把分页遗漏当删除；--reset 用于明确重建选定范围。不同账号/范围需不同工作区。

## 2. 取图与本地处理

```bash
python3 scripts/index_runner.py batch --manifest "$STATE/manifest.jsonl" --output "$STATE/batch.jsonl" --request-output "$STATE/batch.request.json" --batch-id batch-001 --limit 16
python3 scripts/cloud_photo.py cloud-download --skill-dir "$CM_SKILL" --batch "$STATE/batch.jsonl" --directory "$STATE/downloads" --output "$STATE/downloads.jsonl"
python3 scripts/cloud_photo.py media-index --manifest "$STATE/manifest.jsonl" --batch "$STATE/batch.jsonl" --downloads "$STATE/downloads.jsonl" --directory "$STATE/media/batch-001"
```

media-index 对固定 batch 校验 asset_id、缺失成员、文件存在性、非空、已知大小、解码与已有 SHA-256；成功和失败一起写回 manifest/checkpoint，输出 index-report.json 与仅失败成员的 retry.batch.jsonl。批次最多 100 项。不要用临时脚本按文件存在判断成功，或无条件 touch 完成标记。

已有本地原文件也可使用 `{"asset_id":"...","status":"local","local_path":"/绝对路径"}` 输入 media-index（或只提取不写索引的 media-prepare）；此时标记 content_source=local-file，不能据此宣称云端下载成功或云端字节已校验。

download 最多 100 项，按回执 itemIndex 关联原成员，不按返回的新 fileRef 或文件名猜测。默认 fail 防止覆盖已有文件；失败或空文件不会成为视觉任务；local_counts 表示本地实际可用文件数，provider_status 保留上游状态。上游报成功但缺成员时，本地结果降为 PARTIAL/FAILED。media-prepare 生成 768 像素边界缩略图、尺寸、方向、原图 SHA-256、可用 EXIF 拍摄时间、相机型号、GPS 与地理网格及视觉任务；不自动识别场景、人脸、OCR 或质量。不能解码的 HEIC 等格式记录失败，须先配置解码能力。

## 3. 模型标签与恢复

宿主模型读取 vision.tasks.jsonl 中实际缩略图，按 [标签规范](photo-index.md) 生成 vision.labels.jsonl。通过用户授权的宿主图片能力运行，不配置第二套模型密钥。

```bash
python3 scripts/index_runner.py apply --manifest "$STATE/manifest.jsonl" --labels "$STATE/vision.labels.jsonl" --batch-id batch-001
python3 scripts/index_runner.py report --manifest "$STATE/manifest.jsonl" --output "$STATE/report.json"
```

batch 只选 pending/partial/error。下一批 offset 使用命令实际返回的 next_offset；重试较早失败项从 offset 0 开始。apply 校验三类字段并记录标签来源/版本、元数据来源和错误码；成功恢复时清除旧错误，非法状态拒绝整批写入，不明资产不会写入。已有索引的相应标签可用于局部检索，不需等全库完成；必须说明实际覆盖范围。run-batch 仍兼容外部下载映射，提交 labels 时仅允许本批真实可读取成员。

本地状态默认不上传。用户明确要求备份时才按 [cloud-artifacts.md](cloud-artifacts.md) 操作。

空文件和部分失败的恢复步骤见 [取图失败恢复](recovery-and-enrichment.md#取图失败恢复)。
