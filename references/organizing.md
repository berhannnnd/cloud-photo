# 分组计划与云端执行

## 分组

```bash
python3 scripts/cloud_photo.py group-plan --state-dir "$STATE" --owner "$OWNER" --result <result-id> --target album --by month --prefix "旅行-"
python3 scripts/cloud_photo.py plan-show --state-dir "$STATE" --owner "$OWNER" --plan <plan-id>
```

--by 支持 all、year、month 或标签路径，例如 vision_tags.image_type、vision_tags.people；逗号分隔最多三维。时间只用 taken_at。未知值单列“待归类”。--overlap first 按值排序选第一个归属，all 允许同图多组；人物等多标签分组应向用户说明该选择。自动分类由宿主查看实际标签分布后选择 --by，不凭空预测照片类别。

目标：album 新建相簿；existing-album 需 --destination <albumRef> 且 --by all；story 用选集顺序第一张做封面，用户指定封面可通过 select 的有序 ID 数组置首；folder 需 --destination <folderRef> 并经云盘验证属于专属目录。空集合不建计划。来源未取尽时默认拒绝，用户明确只整理已加载集合后可 --allow-partial。

每个计划固定 result ID/摘要、组名、真实成员、目标与重叠规则。名称非法字符转为连字符；碰撞或超长时拒绝，由用户规则修正，不能默默覆盖。

## 公开 CLI 执行

```bash
python3 scripts/cloud_photo.py cloud-prepare --state-dir "$STATE" --owner "$OWNER" --plan <plan-id> --skill-dir "$CM_SKILL" --profile default
# 展示云盘实际返回的冻结计划；只有用户确认后才运行下一条
python3 scripts/cloud_photo.py cloud-execute --state-dir "$STATE" --owner "$OWNER" --plan <plan-id> --skill-dir "$CM_SKILL" --profile default --confirmation CONFIRM
python3 scripts/cloud_photo.py cloud-status --state-dir "$STATE" --owner "$OWNER" --plan <plan-id> --skill-dir "$CM_SKILL" --profile default
```

prepare 会编译为一个公开 orchestrate 计划。普通相簿首批 create，余下 add 并绑定前步 albumRef；目录 mkdir 后分批 copy；故事无追加能力，超限直接拒绝。数量和每步 8192 字符同时限制，完整参数超过 100 KB 时要求显式拆分。引用观察时间超过 10 小时或缺失时拒绝准备；这只是提前保守检查，真正有效性仍由云盘判断。

execute 用真实 operationRef/planHash confirm，再以内存中的 confirmToken execute；令牌不落盘、不输出。profile、Skill 目录、owner 与计划必须一致。prepare 再次运行不会提交第二份云端请求。

部分成功或未知时停止，不重放成功动作。status 只读；如果恢复需要新计划，先从原回执及云端成员列表对账，使用剩余成员创建新结果和新计划。执行器不声称有撤销、自动取消、后台轮询或任意部分恢复能力。所有真实云端写入仍需在目标环境联调。
