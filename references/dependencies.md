# 外部依赖

`cloud-photo` 固定依赖 SkillHub 包 `@org-vt43r0t0/cm-cloud-manage` **2.0.0**，只调用它公开的云盘能力，不复制源码。版本能力差异和文件写入边界见 [cm-cloud-compatibility.md](cm-cloud-compatibility.md)。更新流程由宿主显式触发：

1. 读取当前安装目录的 `_meta.json`，用 `dependency-status` 检查版本和格式。
2. 需要更新时再由 SkillHub 下载新包，并在同一工作区做兼容性检查。
3. 检查失败保留原版本；不因为 `cloud-photo` 自身更新而自动替换云盘访问模块。

因此 cm 模块的独立更新可以被发现，但不会产生未经用户要求的云盘登录或文件写操作。
