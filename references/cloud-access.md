# 云盘访问边界

只使用 cm-cloud-manage 的公开 CLI；不复制 SDK、不读凭据、不拼接后台 HTTP。命令与参数见 [cm-cloud-api.md](cm-cloud-api.md)。本仓库适配器位于 scripts/cloud_photo_core/adapters/cm_cloud.py。

cloud-scan 提取搜索分页并补查详情路径，cloud-download 把真实逐项回执映射为本地批次。AUTH_REQUIRED 交云盘 Skill 的登录流程；其他权限/网络错误不伪装成未登录。不能靠搜索成功推断下载已授权。

文件引用可能轮换和过期。本地 asset_id 独立；引用刷新只做规范路径、大小和修改时间的唯一匹配。缺少证据、改名、路径复用或同名冲突保留待核对。上游稳定键仍是更可靠的长期方案。

云端写计划由 plans.py 编译，execution.py 保存原操作；没有成功回执就不能报告整理完成。写入目录权限由云盘 CLI 验证，源文件保留。
