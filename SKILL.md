---
name: cloud-photo
description: 在云盘中建立可持续更新的照片索引，或根据用户目标整理照片。自动区分“索引照片”和“整理照片”两种模式；通过 cm-cloud-manage 访问中国移动云盘，不把全部照片一次性发送给模型，也不使用 embedding。
---

# Cloud Photo

这是一个顶层 Skill，安装后同时提供三个协作模块：

1. **cloud-access**：发现云盘文件、读取元数据、取得缩略图或可访问的图片引用，并把结果写入工作区索引目录。
2. **photo-index**：对照片生成三类标签并维护 manifest：文件元数据、缩略图派生标签、多模态视觉标签。
3. **index-guidance**：把用户的自然语言条件转换成结构化检索条件，先查索引，再只把候选图片交给视觉模型复核。

三个模块可以在 `packages/` 下独立维护，但只能由本顶层 `SKILL.md` 作为可安装入口。模块之间通过 `references/manifest-schema.md` 定义的 JSONL 清单交换数据。

## 模式路由

先读取 [modes.md](references/modes.md) 判断用户意图：

- 用户说“索引、扫描、打标签、建立照片库”时，只走索引模式：扫描、打标签、写入 manifest，不执行云盘整理写操作。
- 用户说“整理、归类、移动、归档、创建相册”时，走整理模式：先检索和视觉复核，输出可审阅的预览计划，得到确认后才执行云盘写操作。
- 同时提出两种要求时，先补齐必要索引，再停在整理预览计划。

## 运行约束

- 使用 `cm-cloud-manage` 完成登录、列目录、读取文件和取得图片引用；不要复制或改写该 Skill 的源码。
- 大规模相册必须分批、可恢复地建立索引。每条记录都要有稳定的 `asset_id`、`source_ref` 和 `schema_version`。
- 不把整库图片放进一次模型请求；检索先在索引上过滤，随后只检查有限候选，必要时再逐张取得原图。
- 标签只使用三类：`file_metadata`、`thumbnail_tags`、`vision_tags`。不要加入 `confidence` 或 embedding 字段。
- 默认只读；移动、重命名、删除、建相册等写操作必须在用户明确要求后调用 `cm-cloud-manage` 的确认流程。
- 索引文件放在云盘智能体专属目录下的 `.cloud-photo/`；每次索引生成带 `scan_id` 的 manifest、checkpoint 和报告并上传，原始照片仍是云盘中的唯一事实来源。

## 工作流

1. 读取 [cloud-access.md](references/cloud-access.md)，确认当前云盘身份、工作区和可用的图片引用。
2. 读取 [manifest-schema.md](references/manifest-schema.md)，用 `scripts/cloud_photo.py validate` 检查或创建清单。
3. 首次或增量整理时读取 [photo-index.md](references/photo-index.md)，按游标扫描文件、生成缩略图标签，再按受控批次请求多模态视觉标签。
4. 用户提出“找照片”时读取 [index-guidance.md](references/index-guidance.md)，先运行本地检索，再对候选进行视觉复核。
5. 索引或整理完成后读取 [preview.md](references/preview.md) 和 [evidence-pack.md](references/evidence-pack.md)：用 `show_widget` 展示状态/计划，用 contact sheet 展示实际图片，用 `nexus.deliver_files` 交付清单和报告。
6. 每个阶段都保存 checkpoint；失败或超时只重试未完成的批次，不重放已经确认的云盘写操作。
7. 需要确认外部依赖时读取 [dependencies.md](references/dependencies.md)，运行 `dependency-status`；不要在索引任务中自动升级 `cm-cloud-manage`。

## Nexus 对话内展示流程

索引或整理完成后，必须把“做了什么”和“哪些图片对应哪些结果”展示在当前对话中：

1. 用普通文字给出真实数量和状态。
2. 调用 Nexus 内置 `show_widget`，展示候选照片、识别标签、原路径、目标相簿/目录和执行状态；widget 只做本地筛选/展开，不执行云盘写操作。
3. 将实际处理的照片生成 contact sheet，作为图片附件直接展示；需要细看时再附少量原图缩略图。
4. 用 `nexus.deliver_files` 交付整理报告、manifest 和 checkpoint。
5. 对每张图片优先展示稳定云盘链接；没有稳定链接时只展示云盘路径，不伪造 URL。`file_id` 仅保留在内部 manifest 和执行回执中，不在对话界面展示。

不要把 `yun.139.com` 登录页面嵌入 `show_widget`。`show_widget` 只承载静态结果预览，云盘读取和写入仍通过 `cm-cloud-manage 2.0.0` 完成。完整字段和交付文件见 [evidence-pack.md](references/evidence-pack.md)。

## 可执行索引流水线

索引模式优先使用 [index-runner.md](references/index-runner.md) 的预置 runner，不要临时编写全量扫描脚本：

1. `cm-cloud-manage` 输出云盘文件清单 JSONL。
2. `index_runner.py ingest` 过滤非图片并生成 pending manifest。
3. `index_runner.py batch` 生成有界批次、下载请求和下一批游标；宿主按批次取得图片或缩略图。
4. 宿主把下载结果交给 `index_runner.py run-batch`，由 runner 校验文件并生成缩略图任务清单。
5. 多模态模型返回三类标签 JSONL，`index_runner.py apply` 合并并更新 manifest/checkpoint。
6. `report` 生成进度，供 `show_widget` 实时展示；每批都可以独立上传和恢复。

索引模式必须优先使用 `index_runner.py`。如果 runner 已覆盖当前步骤，不得临时创建新的全量扫描、批次合并或 checkpoint 脚本；临时脚本只能处理尚未覆盖的云盘适配边界，并且结果必须回交 runner。

云盘登录、清单读取和图片取得仍由 `cm-cloud-manage` 完成；runner 不读取凭据，也不直接请求云盘 API。

## 配套工具

```text
python scripts/index_runner.py ingest --input cloud-listing.jsonl --output-dir .cloud-photo
python scripts/index_runner.py batch --manifest .cloud-photo/manifest.jsonl --output .cloud-photo/batch.jsonl --limit 32
python scripts/index_runner.py run-batch --manifest .cloud-photo/manifest.jsonl --batch .cloud-photo/batch.jsonl --downloads .cloud-photo/downloads.jsonl --batch-id batch-001
python scripts/index_runner.py report --manifest .cloud-photo/manifest.jsonl
python scripts/cloud_photo.py mode-detect --text "把我这里照片索引一下"
python scripts/cloud_photo.py init --output .cloud-photo/manifest.jsonl
python scripts/cloud_photo.py validate .cloud-photo/manifest.jsonl
python scripts/cloud_photo.py search .cloud-photo/manifest.jsonl --query "猫 户外"
python scripts/cloud_photo.py plan .cloud-photo/manifest.jsonl --query "猫" --target "猫相册"
python scripts/cloud_photo.py merge --base old.jsonl --delta batch.jsonl --output manifest.jsonl
```

工具只负责确定性格式校验、合并和检索；云盘登录、文件下载、缩略图生成和视觉模型调用仍由宿主与 `cm-cloud-manage` 按模块契约完成。
