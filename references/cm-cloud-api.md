# cm-cloud-manage 2.0.2 公开接口核验

核验日期：2026-10-25。目标包：`@org-vt43r0t0/cm-cloud-manage`。本文列出供 cloud-photo 调用的公开 CLI；内部 HTTP adapter 不属于接入接口。

## 版本与使用边界

本文基于 SkillHub 发布包 2.0.2 的公开命令与 schema。包内 SKILL frontmatter 的版本可能与发布元数据不同，接入时应检查实际 `capabilities/schema`。

[SkillHub 发布页](https://skillhub.cn/skills/org-vt43r0t0/cm-cloud-manage)

接口声明可用不等于当前账号已获访问权限。搜索、详情和下载分别处理真实业务回执；下载失败时不能继续声称已完成视觉识别。本文不包含账号实测数据和内部需求评估。

## 调用入口

`{cmSkillDir}` 替换为实际安装目录；不要假设环境存在裸 `cmcloud` 命令。

```text
python3 "{cmSkillDir}/scripts/cm_cloud_cli_api.py" capabilities --format json
python3 "{cmSkillDir}/scripts/cm_cloud_cli_api.py" schema --command-id files.search --format json
python3 "{cmSkillDir}/scripts/cm_cloud_files_api.py" search --typeList '["1"]' --pageSize 100 --format json
python3 "{cmSkillDir}/scripts/cm_cloud_album_api.py" list --kind album --format json
```

新版入口使用 `scripts/cm_cloud_<domain>_api.py`；控制面为 `cm_cloud_cli_api.py`。旧 2.0.0 包使用 `script/cli-src/` 布局，更新时须重新解析入口。Windows 按包约定使用 `py -3`。参数大小写原样保留，数组作为一个 JSON 参数；适配器使用 argv 列表执行，不拼接 shell 字符串。

## 全部命令

| 领域 | 公开命令 | 用途 |
| --- | --- | --- |
| 文件 | `files.upload/search/list/mkdir/download/copy/info` | 上传、检索、列目录、建目录、下载、复制、详情 |
| 动态 | `activity.list/reading/stats` | 浏览/上传/转存动态、阅读记录、月度统计 |
| 分享 | `share.create/subscribe/updates/save/list/browse` | 外链创建、订阅、更新、转存、分享记录与外链浏览 |
| 相册与故事 | `album.search/list/files/create/add/update/share` | 查找对象、查看图片、新建、加图、改标题/封面、生成链接 |
| 操作 | `operation.status/confirm/execute` | 查询原操作、确认冻结计划、执行已确认计划 |
| 授权 | `auth.login/revoke/logout/status` | 登录授权、撤销、退出与状态 |
| 控制 | `capabilities/help/schema/orchestrate` | 能力发现、参数查询、多写动作编排 |

场景数不等于命令数：例如 `album.create` 对应空相册、建相册并加图、指定照片建故事三个场景。`operation.status` 在业务 registry 中，confirm/execute 属控制入口。

## 照片搜索与读取

### files.search

| 参数 | 实际含义与限制 |
| --- | --- |
| `keyword` | 文件名包含匹配，1–100 字符；不是自然语言语义搜图 |
| `typeList` | 文件类型数组，图片为 `["1"]`；兼容单值 `contentType`，二者互斥 |
| `extensionList` | 后缀数组；兼容单值 `extension`，二者互斥 |
| `addressList` / `tagList` | 地理标签/标签筛选，各最多 10 项；未公开通用 AND/OR/NOT 表达式 |
| `timeList` | 最多 10 项；每项为 `filed`、`startTime`、`endTime`，时间 14 位数字；`filed` 是实际字段拼写 |
| `from/to/timeField` | 兼容时间入口；timeField 为 createdAt/updatedAt/takenAt；不能与 timeList 混用 |
| `takenAt` | 只允许图片搜索 `typeList=["1"]`，不能静默替换成上传时间 |
| `sizeRange` | startSize/endSize，单位 byte |
| `isMatchFolder` | 为 true 时要求 keyword |
| `pageSize/cursor` | 默认 10，pageSize 为 1–1000；续页复用原查询条件和页大小 |

至少提供一种有效搜索条件。`page.complete` 表示当前查询范围是否取尽；总数缺失时 `page.total` 可为 null，不能因此判定未取尽。不同条件和数组内部的业务匹配语义仍需真实数据验证，不能从字段名称自行承诺严格组合逻辑。

搜索结果经 `workflow_common.normalize_file_item` 白名单输出：`fileRef`（目录为 folderRef）、name/type/size/createdAt/updatedAt/takenAt，可能带 parentRef。**没有公开返回原始 fileId、AI 标签、人脸簇、质量分、地理明细、缩略图 URL 或内容哈希。** 搜索入参支持标签，不等于返回标签。

### 其他读取接口

| 命令 | 关键字段 | 需要注意 |
| --- | --- | --- |
| `files.list` | rootScope、folderRef、recursive、pageSize、cursor | personal / dedicated 根不同；递归也必须核对覆盖范围 |
| `files.info` | fileIds 或 dynamicRefs，fields | fileIds 虽如此命名，schema 实际要求受控文件引用；最多 100 项 |
| `files.download` | resources、localDirectory、conflictPolicy、integrityPolicy | 1–100 个文件；下载目录须已存在且为绝对路径；默认不覆盖 |
| `album.files` | kind、albumRef、pageSize、cursor | 查看指定相册/故事图片；pageSize 10–100 |

`files.info.fields` 仅 name/size/time/location；**location 是文件路径，不是 GPS**。该 workflow 的 dynamicRefs 分支尚未开放，尽管 schema 可见，调用会报 CAPABILITY_UNAVAILABLE。无公开的缩略图专用命令；需要视觉分析时，经 download 取图后在本地缩放。

### 引用与长期身份

`fileRef` 等受控引用绑定 profile；当前实现默认有效期 12 小时，同一资源在不同调用中可签发不同 token。因此不能按 fileRef 字符串跨搜索求交集、跨页永久去重，或把它当长期结果集身份。不可通过读取内部台账恢复 raw fileId。

当前可在引用有效时补查规范路径和元数据，保存本地 asset_id 与映射；刷新后只对路径和来源证据一致的唯一候选重新绑定。路径变化或证据不足时保留待核对。完整长期恢复建议上游公开稳定资源键和引用刷新接口，详见 [接入设计](mclaw-integration.md)。

## 整理写入

以下为命令形态示例，引用占位符须替换为真实 CLI 回执；调用写命令通常先产生待确认计划，不代表已执行。

```text
python3 "{cmSkillDir}/scripts/cm_cloud_album_api.py" create --kind album --name "2026年旅行" --fileRefs '["<fileRef>"]' --format json
python3 "{cmSkillDir}/scripts/cm_cloud_album_api.py" add --albumRef "<albumRef>" --fileRefs '["<fileRef>"]' --format json
python3 "{cmSkillDir}/scripts/cm_cloud_album_api.py" create --kind story --name "海边回忆" --coverRef "<fileRef>" --fileRefs '["<fileRef>"]' --format json
python3 "{cmSkillDir}/scripts/cm_cloud_files_api.py" copy --resources '["<fileRef>"]' --destinationRef "<folderRef>" --format json
```

| 动作 | 当前支持 | 限制/恢复 |
| --- | --- | --- |
| 新建相册并加图 | kind=album、name、fileRefs | 名称 1–64 字符；每次 1–500 图；建册与加图非原子，PARTIAL 时保留已建相册 |
| 追加已有相册 | albumRef、fileRefs | 每次 1–500 图；没有 duplicatePolicy，不承诺自动去重；不适用于追加故事 |
| 创建故事 | kind=story、name、coverRef、fileRefs | 1–500 图；secondTitle 可选；这是指定照片建故事，不会自动挑图/精选 |
| 更新对象 | album.update | 相册改名称/封面，故事改标题/副标题/封面；不等于移动或删除成员 |
| 生成结果链接 | album.share，deliveryMode=link-only | 会创建分享链接；仅用户需要分享时调用，不把内部结果查看变成公开分享 |
| 建目录和复制 | files.mkdir/copy | 写入目标只能是智能体专属目录及子目录；源可来自授权个人云；保留原图 |

`files.copy.resources` 的 schema 未设置 maxItems，不表示下游可无限批量处理；须按已验证批次与回执处理。普通相册超过 500 图可在创建后分批 add；故事没有对应追加命令，超过 500 图须缩小选集、由用户选择拆分或扩展上游能力，不能自动截断。

## 编排、确认与状态

多个云端写动作可用 `cm_cloud_cli_api.py orchestrate --step ... --step ...` 冻结为一个计划，并用 `?step1.folderRef` / `?step1.albumRef` 引用前步产物。每个 step 是一段业务命令字符串，**最多 8192 字符**；需要同时满足单命令项数和步骤长度，不能直接把 500 个长 token 塞入一步。

多动作计划统一确认后执行；confirmToken 必须来自底层确认接口，不能生成。超过可承载规模的请求须明确分批计划和授权边界，不能宣称任意规模只需一份计划。只读查询、download 和 auth 不进入云端写编排。

消费顶层 SUCCESS/EMPTY/PARTIAL/RUNNING/CONFIRMATION_REQUIRED/AUTH_REQUIRED/REJECTED/FAILED/UNKNOWN、counts、逐项结果与 nextAction。持有 operationRef 才有原操作状态查询；没有持久操作引用的只读查询不能伪装成任务恢复。按底层协议触发 status，不无限轮询，不重放已成功写动作。没有公开取消、撤销或通用 retry 命令。

## 尚未公开的能力

- 自然语言照片语义召回、参考图/选脸检索、人物簇与用户身份映射。
- 指定 fileIdList / resultSetId 的集合内检索或精选；持久结果集及版本管理。
- 返回完整照片标签、质量分、重复/相似组与稳定资源键的照片元数据接口。
- 自动照片分类整理任务、智能精选建故事；云端文件 move/delete/rename。

未注册的包内实现不属于公开能力；使用前以 registry/schema 为准。

可供复查的包内来源：`scripts/core_registry.py`、`scripts/validation_command_schemas.py`、`scripts/workflow_s02_files_search.py`、`scripts/workflow_common.py`、`scripts/workflow_s14_files_info.py`、`scripts/workflow_s30_album_create_with_files.py`、`scripts/workflow_s31_album_add.py`、`scripts/workflow_s32_story_create.py`、`scripts/core_operation_ledger.py`，以及 `references/files.md`、`album.md`、`protocol.md`。
