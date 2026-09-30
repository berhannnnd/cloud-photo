# 图片优先预览

图片是检索和整理结果本身。用户先看到实际图片，再看到文件名、云盘路径和标签；文件名列表、路径列表、文件卡片或状态卡都不能替代图片。

## 展示方式

1. 取得原图或受控缩略图，并把需要展示的副本落盘到当前 workspace 的 `.cloud-photo/`。
2. 通过 `scripts/preview_pack.py markdown` 生成工作区相对 Markdown 图片画廊：

```text
python scripts/preview_pack.py markdown \
  --preview-index .cloud-photo/organize/preview/preview-index.json \
  --output .cloud-photo/organize/preview/gallery-01.md
```

3. 将输出 Markdown 原样放进对话。默认只放一张 `![照片预览](.cloud-photo/.../sheet-01.jpg)`，下方用编号列出对应路径；Nexus 负责鉴权和 inline 读取。路径必须是工作区相对路径。
4. 每批生成一张最多包含 6 张照片的 contact sheet。候选更多时按批次展示，先展示当前命中的类别，再继续下一批；用户明确要逐张查看时才加 `--layout individual`。
5. 图片下方可补充短文件名、云盘路径、标签和“候选/目标/状态”。用户可见内容不显示 `file_id`。

缩略图适合快速筛选和总览；用户明确要求查看原图时，应取得并展示原图。contact sheet 只能作为总览，不能在没有实际图片时冒充预览。

## 组件边界

- `show_widget` 若需要承载照片，必须使用 `preview_server.py` 的共享 relay URL 和 `preview_pack.py widget --image-base-url ... --image-token ...`；不要把照片 Base64 或绝对 workspace 路径塞进 widget。relay 的 `state-dir` 要持久化，多个对话复用同一个 `service-id`，每个对话只使用自己的 `session-id` 和 token。
- 禁止 `file://`、绝对路径、未受管理的 `localhost`/`127.0.0.1`、固定端口中转服务、临时 URL 和手工 Base64。不要用 `pkill` 或任意 `http.server`，不要在一个会话结束时停止仍有其他会话使用的共享 relay，也不要在任务完成后自动执行 `stop-service`。
- `nexus.deliver_files` 用于交付 manifest、报告和预览文件，不能代替当前回复中的 Markdown 图片。

## 检查清单

- 图片文件位于 `.cloud-photo/` 且存在、非空、MIME 为图片。
- 生成的链接没有绝对路径、`data:image` 或服务地址。
- 回复先放图片，再放结论和详情。
- 图片无法渲染时明确报告预览未完成，不宣称成功。
