---
name: cloud-photo
description: 通过中国移动云盘 cm-cloud-manage Skill 索引、检索和整理照片。用于直接找图后整理、基于已有结果自由归类、对搜索结果继续筛选；维护本地标签与候选计划，按公开 CLI 的实际能力创建相册、故事或复制到目录。
---

# Cloud Photo

## 接入边界

面向 Mclaw / OpenClaw，通过 `cm-cloud-manage` 的**公开 CLI**访问云盘。先检查实际安装包的 `capabilities` 与相关命令 `schema`，入口和能力清单见 [cm-cloud-api.md](references/cm-cloud-api.md)。云盘鉴权、资源引用、写计划和操作回执由该 Skill 管理。

不直连 Mclaw/OpenClaw 业务后端，不调用云盘包内部 `adapter_*.py`，不读取它的凭据或内部引用台账。宿主提供执行环境、用户隔离的持久目录、模型图片能力和媒体发送通道；版本号不代表照片业务能力已经接通。

当前本包的可执行能力：manifest 校验/合并、关键词候选、单目标计划草案、索引批次/checkpoint、引用匹配辅助、静态预览图片。持久结果集、结构化筛选、自动分类、精选去重和 CLI 执行适配器**尚未实现**。下文是编排规则，不能把设计中的模块或命令当作现成工具。

## 能力判断

- 云盘 2.0.2 的 `files.search` 支持文件名、类型、后缀、地点/标签、时间、大小；`keyword` 是文件名包含匹配，不能承接自然语言语义搜图。
- 云盘可新建相册并加图、追加已有相册、以指定图片创建故事。选择哪些照片、怎样分组由 cloud-photo 完成。
- 没有公开人物识别、语义召回、质量精选、内容相似去重、`fileIdList` 限定搜索或持久结果集接口。缺少数据时说明未知；可对授权范围内的候选下载并补标签，不承诺全库召回或可靠人物识别。
- 云盘文件读取可覆盖授权个人云；文件夹写入只能落在智能体专属目录及子目录，使用复制保留原图。相册操作使用独立的 album 能力。
- 搜索和整理分开授权。用户只要求找图或筛选时不建册；已明确授权的整理按确定范围推进，并满足底层计划确认契约，不伪造确认或重复索要已满足的授权。

## 三种入口

| 用户意图 | 处理 |
| --- | --- |
| 找去年旅行照片，按月建相册 | 解析条件 → 取得候选 → 补充必要标签 → 筛选/分组 → 相册计划 |
| 把刚才的照片按类型或人物整理 | 绑定上一完整结果集合 → 校验标签 → 按指定或自动规则分组 |
| 这些里排除截图，只留清晰的 | 在当前集合内部生成子集，保存排除/未知；不自动建相册 |
| 扫描、更新照片索引 | 维护 manifest/checkpoint，不改变照片归属 |

详细路由见 [modes.md](references/modes.md)。“这些/刚才/上一批”必须对应真实清单与范围；没有完整清单时恢复来源，不从几张预览图猜全集。

## 搜索、筛选与整理

1. 拆分时间、地点、人物、内容/类型、格式、来源及目标。明确拍摄时间与上传时间；人物姓名需要用户提供的身份映射，不能从外观猜姓名。
2. 用公开 `files.search/list` 取得候选，按 `page.complete` 和 `page.nextCursor` 保存完整分页。内容检索可结合已有本地标签或候选视觉复核；`cloud_photo.py search` 只是关键词召回，默认前 20 条，不能当作满足全部条件的结果。
3. 持久保存完整候选、查询范围和来源。`fileRef` 是短期受控引用，不能当永久 fileId 或跨调用比较键。当前 v1 manifest 的 `source_ref.file_id` 实际可能存的是 fileRef；续接和刷新方式见 [cloud-access.md](references/cloud-access.md)。
4. 二次筛选输出必须是输入集合的子集；放宽早期条件要回到覆盖被排除照片的父集合。无公开范围内搜索接口时，在本地集合上处理，不悄悄全库重搜。缺失字段保留 unknown，按需补查或复核。
5. 分组时保存维度、命名、同图多组/互斥策略和未知项归属。自动分类依据实际标签分布；质量精选与内容相似去重必须有算法或逐图复核证据。按 ID 去重仅消除重复记录。
6. 固定输入集合、规则、目标与计划版本。用公开 `album.create/add` 创建或追加相册，`album.create --kind story` 创建指定选图故事，`files.mkdir/copy` 复制到专属目录。多个写动作使用底层 `orchestrate`，遵守参数数量、步骤长度和确认契约。设计见 [mclaw-integration.md](references/mclaw-integration.md)。
7. 空集合不建空册/目录。按 CLI 顶层状态、`operationRef`、`nextAction` 与逐项回执恢复；受理、处理中、部分成功、未知不能报告为全部完成。成功项不重放，建册成功加图失败只恢复加图。回执规范见 [evidence-pack.md](references/evidence-pack.md)。

当前 `cloud_photo.py plan` 只生成草案，不执行这些云端动作。没有实际执行器时，明确已完成到哪一步。

## 本地索引与展示

按 [cloud-access](references/cloud-access.md) → [photo-index](references/photo-index.md) → [index-guidance](references/index-guidance.md) 分工，使用现有 runner 完成 ingest → batch → run-batch → apply → report。只补充缺失标签，已有有效索引不重复扫描。三类标签和格式见 [manifest-schema.md](references/manifest-schema.md)；不新建 embedding 库，不写臆测置信度。

`{baseDir}` 指本 Skill 安装目录，`{cmSkillDir}` 指云盘 Skill 安装目录；用户状态写入宿主分配的持久 `.cloud-photo/`，安装目录与数据目录分开。预览使用宿主支持的媒体能力，见 [preview.md](references/preview.md)；本地文件存在不代表客户端已展示。

## 当前可执行命令

```text
python3 {baseDir}/scripts/index_runner.py ingest --input cloud-listing.jsonl --output-dir .cloud-photo
python3 {baseDir}/scripts/index_runner.py batch --manifest .cloud-photo/manifest.jsonl --output .cloud-photo/batch.jsonl --limit 32
python3 {baseDir}/scripts/index_runner.py run-batch --manifest .cloud-photo/manifest.jsonl --batch .cloud-photo/batch.jsonl --downloads .cloud-photo/downloads.jsonl --batch-id batch-001
python3 {baseDir}/scripts/index_runner.py report --manifest .cloud-photo/manifest.jsonl
python3 {baseDir}/scripts/cloud_photo.py validate .cloud-photo/manifest.jsonl
python3 {baseDir}/scripts/cloud_photo.py search .cloud-photo/manifest.jsonl --query "猫"
python3 {baseDir}/scripts/cloud_photo.py plan .cloud-photo/manifest.jsonl --query "猫" --target "猫相册"
python3 {baseDir}/scripts/preview_pack.py build --items candidates.json --thumbnail-dir .cloud-photo/thumbnails --output .cloud-photo/preview
```

runner 的列表/下载输入需先按 [index-runner.md](references/index-runner.md) 转成逐条 JSONL，不能直接传原始 CLI 信封。它使用独立逐行读取器；`cloud_photo.py resolve-refs` 使用的通用 `read_json_records` 则存在多行 JSONL 截断问题，修复前该命令仅使用规范 JSON 数组/单个信封作匹配辅助。`mode-detect` 只是关键词路由提示。通用接入设计见 [接入契约](references/mclaw-integration.md)。
