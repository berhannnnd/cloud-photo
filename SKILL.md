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
- 索引文件放在云盘工作区的隐藏目录（建议 `.cloud-photo/`），并可同步一个人类可读的导出文件；原始照片仍是云盘中的唯一事实来源。

## 工作流

1. 读取 [cloud-access.md](references/cloud-access.md)，确认当前云盘身份、工作区和可用的图片引用。
2. 读取 [manifest-schema.md](references/manifest-schema.md)，用 `scripts/cloud_photo.py validate` 检查或创建清单。
3. 首次或增量整理时读取 [photo-index.md](references/photo-index.md)，按游标扫描文件、生成缩略图标签，再按受控批次请求多模态视觉标签。
4. 用户提出“找照片”时读取 [index-guidance.md](references/index-guidance.md)，先运行本地检索，再对候选进行视觉复核。
5. 每个阶段都保存 checkpoint；失败或超时只重试未完成的批次，不重放已经确认的云盘写操作。
6. 需要确认外部依赖时读取 [dependencies.md](references/dependencies.md)，运行 `dependency-status`；不要在索引任务中自动升级 `cm-cloud-manage`。

## 配套工具

```text
python scripts/cloud_photo.py mode-detect --text "把我这里照片索引一下"
python scripts/cloud_photo.py init --output .cloud-photo/manifest.jsonl
python scripts/cloud_photo.py validate .cloud-photo/manifest.jsonl
python scripts/cloud_photo.py search .cloud-photo/manifest.jsonl --query "猫 户外"
python scripts/cloud_photo.py plan .cloud-photo/manifest.jsonl --query "猫" --target "猫相册"
python scripts/cloud_photo.py merge --base old.jsonl --delta batch.jsonl --output manifest.jsonl
```

工具只负责确定性格式校验、合并和检索；云盘登录、文件下载、缩略图生成和视觉模型调用仍由宿主与 `cm-cloud-manage` 按模块契约完成。
