# 整理结果证据包

整理结果同时提供可见图片和可核对事实。图片是主证据，路径和状态是辅助证据。

## 对话中的结果顺序

1. 先展示整理后的分类图片。运行 `scripts/preview_pack.py markdown` 生成每批一个包含最多 6 张照片的 `.cloud-photo/...` 紧凑 Markdown 画廊，并把内容原样放入回复。
2. 用一句话说明真实执行结果；成功数只能来自云盘执行回执，未知和失败不能计入成功。
3. 在每张图下补充短文件名、云盘路径、主要标签和“候选/目标/状态”。用户可见内容不显示 `file_id`。
4. 需要结构化统计或计划时，再加载 `visualize` Skill 调用 `show_widget`。如果同时要在 widget 中展示照片，先用共享 relay 注册当前 session，再用 `preview_pack.py widget` 生成只含短 relay URL 的 HTML；不放照片 Base64。确认图片渲染后不要自动关闭服务；只有用户明确要求注销 session 或关闭服务时，才分别执行 `stop` 或带 `--confirm-close` 的 `stop-service`。
5. 用 `nexus.deliver_files` 交付 manifest、checkpoint、整理报告和 contact sheet 文件，作为追溯材料。

## 预览约束

- 图片和缩略图必须先落盘到当前 workspace 的 `.cloud-photo/`；`/tmp` 只能做下载中转。
- Markdown 图片链接只能使用 `.cloud-photo/...` 工作区相对路径。禁止 `file://`、绝对路径、未受管理的 `localhost`/`127.0.0.1`、临时 URL 和手工 Base64。widget 中的 `localhost` 只能来自本 Skill 管理的共享 relay，并且必须带当前 session 的 token。
- 每批最多 6 张，超出部分使用 `--sheet-offset` 继续生成下一批。不要把一万张原图放入一次消息。
- 停止中转服务或清理 `/tmp` 不应影响已经落盘的预览；如果工作区图片 URL 无法取得，必须明确标记预览未完成并重新检查。

## 交付文件

可交付以下文件：

- `organize-report-<run_id>.json`：逐项事实、原路径、目标引用和回执状态；
- `manifest-<scan_id>.jsonl`：本次使用的索引版本；
- `checkpoint-<scan_id>.json`：可恢复进度；
- `contact-sheet-<run_id>-<part>.jpg`：图片总览。

报告内部可以保留稳定引用供系统回查，但用户可见字段只展示路径。不要默认创建公开分享链接，也不要把临时下载 URL 当长期链接。

## 演示顺序

先展示图片，再展示“候选 → 目标 → 状态”的结构化卡片和报告。这样能同时证明图片确实匹配用户目标、云盘动作确实执行，以及每张图仍可追溯。
