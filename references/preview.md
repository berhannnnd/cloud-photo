# 对话内预览

整理结果的完整展示规范见 [evidence-pack.md](evidence-pack.md)。

索引和整理都应给用户一个可见结果，但预览与持久产物分开处理。

## 推荐组件

### `show_widget`：即时状态和计划预览

调用 Nexus 内置 `show_widget`，生成一个自包含、只读的 HTML fragment，适合展示：

- 当前扫描阶段：发现、缩略图标签、视觉标签、上传索引
- 已完成、partial、error 的数量
- 三类标签的统计和示例
- 整理模式的候选照片、目标相簿/目录和拟执行动作
- “等待确认”的整理计划

这个 widget 只负责当前回复的视觉展示，不保存状态，也不直接调用云盘。所有按钮只能改变 widget 内的筛选或展开状态，不能绕过 `cm-cloud-manage` 的确认流程。

### `nexus.deliver_files`：交付可追溯文件

把 `manifest-<scan_id>.jsonl`、`checkpoint-<scan_id>.json` 和 `report-<scan_id>.json` 登记为当前轮次的 deliverable artifact。用户可以从对话产物入口打开或下载；这比把完整 JSONL 贴进消息更适合大索引。

### 图片附件 / contact sheet：查看真实样本

需要证明视觉标签确实对应照片时，只展示少量代表性缩略图：

- 优先将缩略图物化到当前 workspace 后作为图片附件交付。
- 如果需要一张总览图，生成带 `asset_id`、文件名、目标相簿/目录和主要标签的 contact sheet，再作为图片附件交付。
- 整理结果按“候选 → 目标 → 状态”展示；完整字段和链接放入整理报告。
- 不把一万张原图放进一次消息，也不把带权限的临时云盘 URL 直接塞进 widget；临时 URL 过期或 iframe 无法携带账号授权时，按 `file_id` 重新取得图片。

## 推荐的索引完成回复

同一条回复可以包含：

1. 一句文字总结（扫描范围和状态）。
2. 一个 `show_widget`：进度、标签分布、少量示例。
3. `nexus.deliver_files`：manifest、checkpoint、报告。
4. 必要时附上 contact sheet。

`show_widget` 的工具回执只表示已接受，不证明客户端已经渲染；文字结果仍必须给出可核对的状态和文件产物链接。
