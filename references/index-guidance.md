# index-guidance 模块（整理模式）

检索采用“索引过滤 → 候选复核 → 返回引用”的路径：

1. 解析用户条件为文件名/路径/日期/尺寸、缩略图标签和视觉标签三类条件。
2. 用确定性工具在 manifest 上过滤、排序和去重。默认优先完整记录，再按路径、时间和 `asset_id` 稳定排序。
3. 候选不足时扩大同义词和时间范围；候选足够时不要重新扫描云盘。
4. 需要“准确找出”时，只把候选图片逐张或小批交给多模态模型复核；模型只返回候选 `asset_id` 及是否匹配、简短理由。
5. 返回云盘 `source_ref`，需要打开或下载时再让 cloud-access 按 ID 取得最新引用。

检索结果不是索引事实的替代品。视觉复核结果默认只作为本次回答的筛选依据；用户确认要长期保存时，才把新标签写回 `vision_tags`，并产生新的 `source_hash`/更新时间。


## 整理计划输出

整理模式的第一阶段只输出计划，不直接写云盘：

```json
{
  "mode": "organize",
  "query": "猫的照片",
  "candidates": [{"asset_id": "cm:1", "source_ref": {"provider": "cm-cloud-manage", "file_id": "1"}}],
  "proposed_actions": [{"asset_id": "cm:1", "action": "add_to_album", "target": "猫"}],
  "needs_confirmation": true
}
```

只有用户确认计划后，才把 `proposed_actions` 转换为 `cm-cloud-manage` 的写操作；执行结果必须按文件 ID 对账并回写 manifest。
