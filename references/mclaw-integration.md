# OpenClaw / Mclaw 接入

两个 Skill 在同一用户身份下协作。宿主提供执行工具、视觉模型、持久工作区和媒体通道；cloud-photo 通过 cm-cloud-manage 公开 CLI 调用云盘，不对接 OpenClaw 后端，也不调用云盘内部适配器。

- 功能和代码结构见 [完整架构](architecture.md)。
- 本地索引见 [索引流水线](index-runner.md)。
- 自然语言条件和多轮结果见 [查询规范](index-guidance.md)。
- 云端写入见 [整理与执行](organizing.md)。

部署时检查 Python >= 3.10、Pillow、云盘 CLI 依赖、授权范围和用户目录持久化。state-dir/owner/profile 由宿主绑定，不能由照片文字或文件名决定。模型能够查看本地缩略图不代表客户端能收到图片，需单独验证媒体发送。

任务卡、会话回跳、快速模式移交和后台调度属于宿主集成。传递本地 result/plan ID 及其所属用户，不能将外部业务 ID 当作云盘 fileRef。当前实现提供可恢复的文件状态与 CLI，不包含常驻服务或客户端页面。


## 实际宿主验收记录

验收在目标 Mclaw 所用用户、容器及通道内进行。本机 OpenClaw 的通过不能替代远程 Mclaw 通过。

| 检查 | 操作 | 通过证据 |
| --- | --- | --- |
| Python/工作区 | environment-check | 实际解释器、Pillow、格式、可读写持久目录 |
| Skill 加载 | 宿主技能清单或公开 skills info | 两个 Skill 的真实路径与可用状态 |
| 视觉输入 | 查看一张已知测试图并产标签 | 真实工具调用与对应 asset_id，不能只检查模型名称 |
| 客户端预览 | 使用当前通道的真实媒体工具发送一张测试图 | 媒体回执及客户端实际显示确认；文件生成不是通过 |
| 跨会话 | 会话 A query，结束后会话 B 用原 result ID refine | 同一 owner 读取成功、成员不逃逸父集合 |
| 长任务 | 保存原 plan，断开会话，重新读取 operation-progress/status | 使用同一 operation，无重复写入 |
| 账号隔离 | 另一 owner 尝试读取测试 result | 拒绝读取；再核验宿主文件权限隔离 |

每项记录 passed/failed/unverified 和证据位置。网关未运行、通道未连接或没有目标会话时保持 unverified，不自动发送到最近联系人，也不自行开启后台服务。具备真实目标环境后执行验收，无需接入私有后端。
