# index-guidance 模块（整理模式）

检索采用“索引过滤 → 图片预览 → 候选复核 → 返回引用”的路径：

1. 解析用户条件为文件名/路径/日期/尺寸、缩略图标签和视觉标签三类条件。
2. 用 `scripts/cloud_photo.py search` 或 `plan` 在 manifest 上过滤、排序和去重。默认优先完整记录，再按标签命中数、路径、时间和 `asset_id` 稳定排序。
3. 先为候选取得已有缩略图，生成图片网格并展示；文件名和路径只作为图片 caption/详情。
4. 候选不足时扩大同义词和时间范围；候选足够时不要重新扫描云盘。检索阶段不得另写全量 `find`/扫描脚本。
5. 需要“准确找出”时，只把候选图片逐张或小批交给多模态模型复核；模型只返回候选 `asset_id` 及是否匹配、简短理由。
6. 返回云盘路径或稳定链接，需要打开或下载时再让 cloud-access 按内部引用取得最新图片。

## 已验证的批量检索经验

真实运行中验证过的做法可以直接复用：

- 云盘目录不能只依赖一次递归 list；根目录发现子文件夹后，逐个补列子文件夹，并把结果统一交给 `ingest`。
- 下载按受控批次执行；下载结果先落成批次 JSONL，再由 `run-batch` 校验本地文件和生成缩略图任务。
- 缩略图处理结果先形成有序视觉复核队列；视觉模型只处理队列中的候选，不把整库图片放入一次请求。
- 检索优先读取已上传的 manifest、checkpoint 和 report；索引存在且未过期时不重新扫描云盘。
- 视觉复核结果必须通过 `index_runner.py apply` 合并，不能在临时脚本里直接改 manifest 或手写新的状态字段。

检索结果不是索引事实的替代品。视觉复核结果默认只作为本次回答的筛选依据；用户确认要长期保存时，才把新标签写回 `vision_tags`，并产生新的 `source_hash`/更新时间。


## 整理计划输出

整理模式的第一阶段只输出计划，不直接写云盘。对话中先展示候选图片网格，再展示计划：

```json
{
  "mode": "organize",
  "query": "猫的照片",
  "candidates": [{"asset_id": "cm:1", "source_ref": {"provider": "cm-cloud-manage", "path": "/照片/猫.jpg"}}],
  "proposed_actions": [{"asset_id": "cm:1", "action": "add_to_album", "target": "猫"}],
  "needs_confirmation": true
}
```

只有用户确认计划后，才把 `proposed_actions` 转换为 `cm-cloud-manage` 的写操作；执行结果必须按内部稳定引用对账并回写 manifest。用户可见结果只展示图片、路径和状态，不展示 `file_id`。
