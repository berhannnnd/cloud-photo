# 对话内图片预览

照片展示优先使用 Nexus 原生工作区 Markdown 图片链路。它会把 `.cloud-photo/` 下的相对路径解析为带权限的 inline preview URL，图片由 Nexus 读取，模型只传短路径，不搬运图片二进制。

如果必须用 `visualize`/`show_widget`，使用 `scripts/preview_server.py` 管理共享 relay。relay 只启动一次，多个对话通过同一个 `service-id` 和持久 `state-dir` 注册各自的 `session-id` 与 token；图片 URL 按 token 映射到该会话的 workspace。每次对话都可以直接调用 `start`，它会先复用运行中的服务，再注册当前会话，不要另起固定端口。

## 硬性规则

- 只要用户要求查找、分类、整理或预览照片，回复中必须先出现实际图片；文件名、路径、标签、统计和报告只能作为辅助信息。
- 预览文件必须落盘到当前 workspace 的 `.cloud-photo/`，不能只放在 `/tmp`。下载完成后先复制到该目录，再生成画廊。
- 使用 `scripts/preview_pack.py markdown` 从 `preview-index.json` 生成一批 Markdown 图片，默认最多 6 张；把生成文件的内容原样放入当前回复。
- Markdown 图片链接必须是 `.cloud-photo/...` 工作区相对路径。禁止 `file://`、未受本 Skill 管理的 `localhost`/`127.0.0.1`、绝对路径、临时下载 URL 和手工 Base64。
- 每批最多 6 张；更多结果按 `--sheet-offset 1`、`2` 继续生成，不把大量图片拼进一次回复。
- 需要用 `show_widget` 放图片时，先执行：

```text
python scripts/preview_server.py start \
  --root "$WORKSPACE" \
  --state-dir "$WORKSPACE/.cloud-photo/runtime/relay" \
  --service-id cloud-photo \
  --session-id "$SESSION_ID"
```

读取该 JSON 输出中的 `url`、`token` 和 `session_id`，再执行：

```text
python scripts/preview_pack.py widget \
  --preview-index .cloud-photo/organize/preview/preview-index.json \
  --output .cloud-photo/organize/preview/widget.html \
  --image-base-url "$RELAY_URL" \
  --image-token "$RELAY_TOKEN" \
  --workspace-root "$WORKSPACE"
```

把生成的 HTML 交给 `show_widget`。组件接受成功不能证明图片已加载；图片显示后也不要自动关闭服务或注销 session，服务默认留给其他对话复用。只有用户明确要求注销当前 session 时才执行 `stop --session-id`；只有用户明确要求关闭服务、确认没有活动 session 时才执行 `stop-service --confirm-close`。服务失效时先运行 `status`，再重新 `start`，不要使用 `pkill`、固定端口或任意 `http.server`。

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
5. 需要统计或计划卡片时，再加载 `visualize` Skill 并调用 `show_widget`；如果已经使用 relay widget 展示图片，可以在同一个 widget 中放轻量状态，但不增加图片字节或未经限制的候选数量。
6. 用 `nexus.deliver_files` 交付 manifest、checkpoint、报告和完整 contact sheet；文件卡片不能代替正文图片。

## 失败处理

如果工作区图片 URL 无法取得，先报告图片预览未完成并重新物化/检查图片；不能用文件名列表、文件卡片或“已生成 contact sheet”冒充图片已展示。停止中转服务或清理 `/tmp` 不应影响已经落盘的 `.cloud-photo/` 图片。

整理结果按“图片 → 一句结论 → 路径/标签/状态”的顺序展示。用户可见内容不显示 `file_id`；稳定云盘链接只有在实际返回且仍有效时才提供。
