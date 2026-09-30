# 对话内预览

`visualize`/`show_widget` 只负责在对话 iframe 中执行已经提交的 HTML fragment；它不启动、保活或代理本机图片服务。任何依赖 `http.server`、固定端口、`localhost` 或 `127.0.0.1` 的方案都属于已废弃的调试方案，不能进入最终回复。

图片优先规则见 [image-first-preview.md](image-first-preview.md)。用户要求查看图片时必须展示原图；本文件中的所有状态卡、文件名卡片和交付文件都不能替代实际图片展示。

分类图片展示是硬性完成条件。数量、路径、标签和报告都可以省略，分类后的图片不能省略。

整理结果的完整展示规范见 [evidence-pack.md](evidence-pack.md)。

索引和整理都应给用户一个可见结果，但预览与持久产物分开处理。

## 推荐组件

### 图片网格 / contact sheet：第一视觉内容

检索或整理结果先展示实际原图；候选很多时按批次展示。contact sheet 只做总览。每格以图片为主，文件名只作短 caption；路径、标签和状态放到展开详情或图片下方。没有实际图片时不能用文件名 chip 代替，必须先补取原图或报告预览失败。

预览图片必须先物化到 workspace 的 `.cloud-photo/` 持久目录并做存在性检查；只存在于 `/tmp` 的文件不能直接作为预览依赖。

最终回复还要做图片体积检查：原图用于按需查看，widget 内嵌降采样预览；预览组过大时拆批或降低尺寸/质量，不能把原图 base64 直接塞进组件。

本地绝对路径不能直接写成 Markdown 图片链接。必须先用图片读取/原生媒体附件能力把文件内容交给对话客户端；否则会出现空白区域或破损图片图标。

同样不能把 `localhost`、`127.0.0.1` 或 workspace 本地 HTTP 服务地址写进 widget。它们只在 Agent 进程所在主机可见，客户端无法加载。

本地 HTTP 服务可以短暂用于生成或调试，但不能把它的 `localhost`/`127.0.0.1` 地址放进 `show_widget`。图片必须先落盘到当前 workspace 的 `.cloud-photo/`，再以内嵌且有大小上限的 `data:image/...` 放入自包含可视化，或由图片读取工具返回原生图片附件；服务停止、端口失效或临时目录清理不能让已经交付的预览失效。`deliver_files` 只能提供持久化文件卡片，不能代替正文中的图片附件。

推荐用 `scripts/preview_pack.py widget` 把 `preview-index.json` 中的持久化小图打包为自包含 HTML fragment，再把 fragment 原样交给 `show_widget`。该命令按总字节数和组数截断，超出部分分批生成；它不会启动服务，也不会在 fragment 中留下工作区路径。

`preview-index.json` 中的相对图片路径按索引文件所在目录解析，因此从另一工作目录生成 widget 也不会丢图。内嵌图片使用 eager 加载；`show_widget` 返回 accepted 仍只代表载荷被接收，仍应通过原生图片附件或客户端可见结果确认实际渲染。

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

需要证明视觉标签确实对应照片时，必须展示少量代表性缩略图：

- 优先将缩略图物化到当前 workspace 后作为图片附件交付。
- 如果需要一张总览图，生成带短文件名 caption、目标相簿/目录和主要标签的 contact sheet，再作为图片附件直接展示；`asset_id` 不放在用户可见 caption 中。
- 整理结果按“候选 → 目标 → 状态”展示；完整字段和链接放入整理报告。
- 不把一万张原图放进一次消息，也不把带权限的临时云盘 URL 直接塞进 widget；临时 URL 过期或 iframe 无法携带账号授权时，由 cloud-access 使用内部文件引用重新取得图片。

## 推荐的索引完成回复

同一条回复应按以下顺序包含：

1. contact sheet 或实际缩略图网格（先让用户看到图）。
2. 一句文字总结（扫描范围和状态）。
3. 一个 `show_widget`：进度、标签分布、图片候选和详情。
4. `nexus.deliver_files`：manifest、checkpoint、报告和完整 contact sheet。

`show_widget` 的工具回执只表示已接受，不证明客户端已经渲染；文字结果仍必须给出可核对的状态和文件产物链接。

如果没有实际的 `show_widget` 调用和回执，不能只根据“已生成 base64/contact sheet”声称预览完成。用户中断、payload 过大或组件调用失败时，应明确标记预览未完成并重新发起小批次渲染。
