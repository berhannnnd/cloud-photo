# cloud-photo

可安装的顶层照片云盘 Skill。它把云盘访问、照片索引和自然语言检索指导组合成一个入口，内部三个模块仍可独立维护。

- 不使用 embedding。
- 标签固定为文件元数据、缩略图派生标签、多模态视觉标签。
- 原始照片留在云盘；工作区 `.cloud-photo/` 保存可恢复的 JSONL 索引和 checkpoint。
- 中国移动云盘访问由外部 `cm-cloud-manage` 提供。
- 使用 `show_widget` 展示图片时由 `scripts/preview_server.py` 提供共享、按会话 token 隔离的 loopback relay；服务默认常驻，不使用 Base64，只有用户明确要求关闭时才停止。

整体的上下文边界、三类索引信息、检索流程和 500 张照片实测记录见 [大规模照片索引与召回说明](references/photo-retrieval-at-scale.md)。

详见 [SKILL.md](SKILL.md)。
