# OpenClaw / Mclaw 接入

两个 Skill 在同一用户身份下协作。宿主提供执行工具、视觉模型、持久工作区和媒体通道；cloud-photo 通过 cm-cloud-manage 公开 CLI 调用云盘，不对接 OpenClaw 后端，也不调用云盘内部适配器。

- 功能和代码结构见 [完整架构](architecture.md)。
- 本地索引见 [索引流水线](index-runner.md)。
- 自然语言条件和多轮结果见 [查询规范](index-guidance.md)。
- 云端写入见 [整理与执行](organizing.md)。

部署时检查 Python >= 3.10、Pillow、云盘 CLI 依赖、授权范围和用户目录持久化。state-dir/owner/profile 由宿主绑定，不能由照片文字或文件名决定。模型能够查看本地缩略图不代表客户端能收到图片，需单独验证媒体发送。

任务卡、会话回跳、快速模式移交和后台调度属于宿主集成。传递本地 result/plan ID 及其所属用户，不能将外部业务 ID 当作云盘 fileRef。当前实现提供可恢复的文件状态与 CLI，不包含常驻服务或客户端页面。
