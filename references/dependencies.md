# 外部依赖

## 云盘 Skill

云端业务统一依赖 `@org-vt43r0t0/cm-cloud-manage` 的公开 CLI。本次于 2026-10-25 核验 SkillHub 包 **2.0.2**；原安装 2.0.0 未自动升级。cloud-photo 不复制其源码，不直接调用后端或内部 adapter。

运行前：

1. 从宿主技能目录定位实际安装包，读取 `_meta.json`；`cloud_photo.py dependency-status --path <目录> --expected 2.0.2` 只校验版本元信息，不证明能力兼容。
2. 按实际入口运行 capabilities，并读取本任务相关 schema；不同版本布局见 [cm-cloud-compatibility.md](cm-cloud-compatibility.md)。
3. 新版本先在隔离目录检查参数、回执与代表性场景，再按宿主的依赖更新流程启用。cloud-photo 更新不自动替换云盘包或登录账号。

2.0.2 的 SKILL frontmatter 仍写 2.0.0，不能单独据此判断发布版本。只读 capabilities/schema 成功也不等于云盘真实读写已联调。

## 宿主与 Python

宿主需能加载两个 Skill、执行 Python 脚本，并提供按用户隔离的持久工作区。解释器版本与授权依赖以云盘包实际要求为准。本仓库核心脚本要求 Python >= 3.10，使用标准库；图片元数据、缩略图与静态预览需要 Pillow，视觉标签需要实际可用的图片模型或宿主视觉工具。

安装目录与用户数据目录分开。云盘 profile/登录信息由云盘 Skill 与宿主管理，不复制到 manifest 或对话。图片输入、媒体发送、任务卡和会话回跳按当前 Mclaw 通道验证；OpenClaw 版本号不会自动补齐这些能力。

接口总表见 [cm-cloud-api.md](cm-cloud-api.md)，职责和宿主边界见 [mclaw-integration.md](mclaw-integration.md)。
