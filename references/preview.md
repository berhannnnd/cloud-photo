# 对话内图片预览

照片展示使用 Nexus 原生工作区 Markdown 图片链路。它会把 `.cloud-photo/` 下的相对路径解析为带权限的 inline preview URL，图片由 Nexus 读取，模型只传短路径，不搬运图片二进制。

## 硬性规则

- 只要用户要求查找、分类、整理或预览照片，回复中必须先出现实际图片；文件名、路径、标签、统计和报告只能作为辅助信息。
- 预览文件必须落盘到当前 workspace 的 `.cloud-photo/`，不能只放在 `/tmp`。下载完成后先复制到该目录，再生成画廊。
- 使用 `scripts/preview_pack.py markdown` 从 `preview-index.json` 生成一批 Markdown 图片，默认最多 6 张；把生成文件的内容原样放入当前回复。
- Markdown 图片链接必须是 `.cloud-photo/...` 工作区相对路径。禁止 `file://`、`localhost`、`127.0.0.1`、绝对路径、临时下载 URL 和手工 Base64。
- 每批最多 6 张；更多结果按 `--sheet-offset 1`、`2` 继续生成，不把大量图片拼进一次回复。
- `show_widget` 只展示数量、标签分布、候选到目标的结构化状态或整理计划，不承载照片，也不作为图片文件服务器。只有图片 Markdown 真正出现在回复中，才算完成图片预览。

## 标准流程

1. 用 `cm-cloud-manage` 取得实际候选照片或持久化缩略图，并复制到 `.cloud-photo/`。
2. 检查每个引用存在、非空且为图片格式。
3. 运行：

```text
python scripts/preview_pack.py markdown \
  --preview-index .cloud-photo/organize/preview/preview-index.json \
  --output .cloud-photo/organize/preview/gallery-01.md
```

4. 读取 `gallery-01.md`，把其中的 Markdown 原样放入回复；文件名和云盘路径放在图片下方。
5. 需要统计或计划卡片时，再加载 `visualize` Skill 并调用一次 `show_widget`。图片展示和状态卡分开。
6. 用 `nexus.deliver_files` 交付 manifest、checkpoint、报告和完整 contact sheet；文件卡片不能代替正文图片。

## 失败处理

如果工作区图片 URL 无法取得，先报告图片预览未完成并重新物化/检查图片；不能用文件名列表、文件卡片或“已生成 contact sheet”冒充图片已展示。停止中转服务或清理 `/tmp` 不应影响已经落盘的 `.cloud-photo/` 图片。

整理结果按“图片 → 一句结论 → 路径/标签/状态”的顺序展示。用户可见内容不显示 `file_id`；稳定云盘链接只有在实际返回且仍有效时才提供。
