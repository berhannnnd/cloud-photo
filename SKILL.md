---
name: cloud-photo
description: 通过中国移动云盘 Skill 获取照片，在本地建立内容标签索引，按自然语言条件搜索、继续筛选并分类整理到相簿、故事或目录。用于云盘照片索引与整理，不用于一般文件管理。
---

# Cloud Photo

## 分工

宿主模型理解意图、看图生成标签和解释结果；Python 负责完整集合、确定性筛选、分组和操作恢复；`cm-cloud-manage` 负责鉴权及云端读写。无需云端语义搜索接口，不新建向量库。索引质量取决于实际看过的图片与标签覆盖，不能把文件名匹配当画面识别。

运行要求：**Python >= 3.10；图片处理需 Pillow >= 9.1**，按 `requirements.txt` 安装。先读 [依赖与运行环境](references/dependencies.md)，用 `environment-check` 验证实际解释器与工作区。`{baseDir}` 为本 Skill 安装目录，`{cmSkillDir}` 为云盘 Skill 安装目录。状态写入宿主分配的用户持久工作区，`--owner` 来自宿主身份；不能让聊天内容替换其他用户身份。CLI 的 owner 分区不是操作系统权限隔离。

## 按任务读取

| 请求 | 执行路径 | 参考 |
| --- | --- | --- |
| 扫描、建立或更新索引 | cloud-scan → ingest → batch → cloud-download → media-prepare → 模型标签 → apply | [索引流程](references/index-runner.md)、[标签规范](references/photo-index.md) |
| 找照片 | 意图转 QuerySpec → query → result-show → 必要的候选复核 | [查询与结果集](references/index-guidance.md) |
| “这些里面……” | 使用原 result ID → refine/select/dedupe，近似画面用 similar-candidates → review-show → 视觉复核 → select | [查询与结果集](references/index-guidance.md) |
| 按时间、类型、人物整理 | 固定 result → group-plan → plan-show → cloud-prepare → 展示底层计划 → cloud-execute | [整理与执行](references/organizing.md) |
| 查看进度、恢复任务 | 查看本地 checkpoint/结果/计划，cloud-status 查询原 operation | [回执与恢复](references/evidence-pack.md) |

长任务进度、跨会话恢复与候选内补标见 [恢复与补标](references/recovery-and-enrichment.md)；需要客户端图片与跨会话交互时按 [宿主验收](references/mclaw-integration.md) 验证。

完整架构与模块位置见 [architecture.md](references/architecture.md)。不需要一次加载所有文档。

## 关键执行规则

- 获取照片先用真实公开 CLI。读取失败、权限不足、未知状态均不能记成空集合或成功；下载失败不生成内容标签。首次业务遇到授权问题交给云盘 Skill 的授权流程，不读取凭据或调用内部 adapter。
- 自然语言由模型转为明确字段、同义词和 all/any/not 条件，再交代码执行。时间写成绝对范围并说明时区；拍摄时间缺失不能用上传时间替代。没有标签的字段进入 unknown；模型不能替未知项补猜测。
- 检索前用 index_runner report 查看所需字段覆盖；处理 complete、清单 complete 和云端执行 SUCCESS 分别解释。整理结束按公开成员列表回读对账；回读未完成需明确说明。
- query 保存全部匹配成员；result-show 的分页仅影响展示。“这些/刚才”绑定实际 result ID。refine 是父结果子集；放宽条件回到适当祖先或重新查明确范围，不能在已缩小的集合中假装恢复被排除成员。
- 本地 asset_id 与短期 fileRef 分离。过期引用用新详情清单进行 refresh-refs；仅路径和大小/修改时间一致的唯一候选可续接。这是保守匹配，不等于上游永久 ID。路径复用、改名或信息不足需核对，不按同名自动绑定。
- 模型只根据实际图片生成标签；具体人物身份须用户确认映射。代码提供 SHA-256 精确去重和 dHash 相似候选；候选不等于重复，精选和主观质量由宿主视觉复核后显式 select，不能把字节去重说成相似去重。
- 查图、筛选和生成本地计划不改云盘。执行整理只在用户已要求该动作时推进，并遵守底层真实计划确认契约。cloud-execute 的 CONFIRM 只能在用户确认所展示计划后传入。
- 多写动作编译为同一底层 orchestrate 计划，所有目标和分组可审阅。未知或部分成功不重提原写请求；cloud-status 只查原操作。无公开取消/撤销时，不把本地改条件说成云端取消。
- 原图保留，目录整理使用复制，目标由云盘校验须在专属目录；相簿/故事使用独立能力。故事超过上限不能截断，要求明确选图或拆分。
- 图片通过 [宿主媒体通道](references/preview.md) 展示；本地生成预览文件不等于用户已看到。索引默认本地保存，[云端备份](references/cloud-artifacts.md)仅在用户要求时进行。

## 入口

```bash
python3 "{baseDir}/scripts/cloud_photo.py" --help
python3 "{baseDir}/scripts/index_runner.py" --help
python3 "{baseDir}/scripts/preview_pack.py" --help
```

新流程使用 query/refine/group-plan。兼容命令 search 是关键词候选，plan 是旧单目标草案；两者都不代替完整结果集或云端执行。字段见 [manifest-schema.md](references/manifest-schema.md)，云盘参数见 [cm-cloud-api.md](references/cm-cloud-api.md)。
