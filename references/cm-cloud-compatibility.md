# cm-cloud-manage 版本兼容

当前设计以 2026-10-25 实际下载并核验的 **2.0.2** 为准，包名 `@org-vt43r0t0/cm-cloud-manage`。本机原安装 2.0.0 未被替换。完整接口与核验方法见 [cm-cloud-api.md](cm-cloud-api.md)。

## 2.0.0 → 2.0.2

| 检查项 | 本机 2.0.0 | 下载的 2.0.2 |
| --- | --- | --- |
| 发布元数据 | _meta.json = 2.0.0 | _meta.json = 2.0.2 |
| 包内 Skill 版本文字 | 2.0.0 | 仍写 2.0.0，元信息存在不一致 |
| 脚本布局 | script/cli-src/ | scripts/ 下的领域入口和扁平模块 |
| registry / 输入 schema | 原有业务定义 | 对比只见布局/导入调整，无业务命令和参数增量 |
| 照片原子动作 | 相册创建/加图、指定照片建故事等 | 仍提供；不能称为本次新增 |

上述对比范围是 registry 和 schema，不声称两个包全部实现完全相同。调用前仍需检查当前安装的 capabilities、schema 和相关 workflow；例如 files.info 的 dynamicRefs 虽出现在 schema 中，当前分支仍拒绝执行。

## 2.x 的接入边界

- files.search/list/info/download 读取授权个人云；search 的 keyword 是文件名检索。
- files.upload/mkdir/copy 的文件写入落点只能是智能体专属目录及子目录。
- album.create/add 可整理普通相册；album.create kind=story 可用指定选图建故事。相册资源不等同于云盘目录。
- 无公开文件 move/delete/rename，也无公开照片语义搜索、人物识别、结果集筛选和精选去重命令。
- 受控引用有期限和 profile 绑定；不能当永久 ID。裸 cmcloud 不一定可执行，优先使用实际包内完整入口。

历史 1.0.6 的下载/目录限制不作为当前 2.0.2 契约。升级验收应覆盖分页、身份刷新、相册追加、故事创建、部分成功和专属目录复制，不能只比较版本字符串。
