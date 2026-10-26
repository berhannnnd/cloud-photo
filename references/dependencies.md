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

安装目录与用户数据目录分开。云盘 profile/登录信息由云盘 Skill 与宿主管理，不复制到 manifest 或对话。图片输入、媒体发送、任务卡和会话回跳按宿主当前通道验证；宿主平台版本号不会自动补齐这些能力。

接口总表见 [cm-cloud-api.md](cm-cloud-api.md)，职责和宿主边界见 [host-integration.md](host-integration.md)。

## Python 安装与自检

最低 Python 3.10（使用 zone/time parsing、Path.is_relative_to 与 int.bit_count）；推荐在用户工作区的独立虚拟环境运行，安装目录与数据目录分开。

```bash
python3 -m venv "$STATE/venv"
"$STATE/venv/bin/python" -m pip install -r "{baseDir}/requirements.txt"
"$STATE/venv/bin/python" "{baseDir}/scripts/cloud_photo.py" environment-check --directory "$STATE"
```

Windows 使用 `py -3 -m venv`，解释器为 `<STATE>\venv\Scripts\python.exe`。`requirements.txt` 仅列本项目图片处理依赖 Pillow>=9.1；查询、索引合并、结果集和计划逻辑只用标准库。没有强制安装 OpenAI SDK、向量库或第二套模型服务。

HEIC/HEIF 等格式取决于 Pillow 可用解码器；需要时另装兼容的解码插件并完成注册与样图解码测试。安装了插件包不等于已注册成功。环境检查会列出当前实际注册的格式；不支持的格式仍返回解码失败，不能跳过后报全量成功。

云盘 Skill 的依赖遵循其自身发行说明；不要把本项目 requirements 当作云盘完整依赖。两个解释器可不同：cloud-* 的 `--python` 指定上游解释器，当前命令本身的 Python 仍必须安装本项目所需库。环境自检只证明本地解释器、图片库和目录读写，不证明宿主视觉模型、手机媒体展示或跨会话恢复。
