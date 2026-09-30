# cloud-photo

可安装的顶层照片云盘 Skill。它把云盘访问、照片索引和自然语言检索指导组合成一个入口，内部三个模块仍可独立维护。

- 不使用 embedding。
- 标签固定为文件元数据、缩略图派生标签、多模态视觉标签。
- 原始照片留在云盘；工作区 `.cloud-photo/` 保存可恢复的 JSONL 索引和 checkpoint。
- 中国移动云盘访问由外部 `cm-cloud-manage` 提供。

详见 [SKILL.md](SKILL.md)。
