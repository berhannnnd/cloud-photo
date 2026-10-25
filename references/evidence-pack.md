# 回执、进度与恢复

索引进度使用 checkpoint/report 的实际数量；结果集给出匹配、排除、未知以及查询范围完整性；分组计划分别计成员数和分组归属数，同一照片多组时两者不同。

云端状态保存在 owners/<owner-hash>/plans/<plan-id>.operation.json，绑定本地计划摘要、profile、Skill 目录和原始 operationRef/planHash。确认令牌只在内存传递，不记录。不要把生成计划、提交或 RUNNING 报告为成功。

| 状态 | 处理 |
| --- | --- |
| CONFIRMATION_REQUIRED | 展示云盘实际冻结计划，用户确认后执行 |
| SUCCESS | 报告真实结果，不重放 |
| RUNNING | cloud-status 查询原操作；无真实进度不编造百分比 |
| PARTIAL | 对账成功项；仅剩余成员可以另立新计划 |
| FAILED / REJECTED | 报告错误；不当作空结果 |
| UNKNOWN | 查询原操作；无 operationRef 时人工核对，不自动重交 |
| AUTH_REQUIRED | 按云盘 Skill 原流程授权，保留本地任务 |

锁文件避免同一计划并发提交。进程异常留下锁时先确认原进程结束，再由维护者处理该锁；不能以删除锁和原日志的方式盲目重试。执行器不提供自动撤销或后台轮询。
