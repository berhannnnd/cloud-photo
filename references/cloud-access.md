# cloud-access 模块

云端访问统一调用 `cm-cloud-manage` 的公开 CLI；本模块不实现中国移动云盘 HTTP，也不直连 Mclaw 业务后端。核验版本为 2.0.2，入口与参数见 [cm-cloud-api.md](cm-cloud-api.md)，完整编排见 [mclaw-integration.md](mclaw-integration.md)。

## 读取与数据归一化

通过 files.search/list 取得候选，必要时 files.info 补名称、大小、时间和路径，通过 files.download 下载候选供本地缩放/标签处理。读取覆盖授权个人云；实际可用范围仍以回执为准。search 不返回 AI 标签、人物、质量或缩略图；info.location 是路径。

索引需要本地稳定 asset_id、来源信息和当前受控 fileRef。现有 v1 manifest 的兼容形态如下，`file_id` 在此存放的是短期引用，**不是底层永久 ID**：

```json
{"asset_id":"local-photo-001","source_ref":{"provider":"cm-cloud-manage","file_id":"<current-fileRef>","path":"/照片/2026/IMG.JPG"},"file_metadata":{}}
```

该片段只示意来源字段，完整记录须满足 [manifest-schema.md](manifest-schema.md)。把 info 返回的路径段数组规范化为明确的路径格式后再参与匹配；不把不同来源的 type 数值直接当相同枚举。

将 CLI 回执显式归一化为 runner 接收的逐条 JSONL，列表提取 data.items，下载结果映射 asset_id/local_path/status，详见 [index-runner.md](index-runner.md)。runner 有独立逐行读取器；通用 JSONL 截断问题发生在 cloud_photo.py 的 read_json_records。分页必须取至所需范围完成并记录覆盖情况，不把第一页当整库。

不要保存访问令牌、cookie、二维码或临时下载 URL。asset_id、短期引用、扫描范围、路径和元数据分别保存；工作区由宿主按用户隔离。

## 受控引用的生命周期

当前云盘包的 fileRef 默认有效 12 小时，同一资源在不同调用中可能返回不同 token。只通过公开命令取得引用，不读内部台账，不尝试解码 raw fileId。文件名和 fileRef 都不能作为跨会话的唯一身份。

在引用有效时用 files.info 保存必要来源证据。执行前失效的引用须重新 list/search，并根据规范路径与元数据唯一绑定；改名、移动、内容变化或路径复用时保留 unresolved，不能凭同名猜测。

`cloud_photo.py resolve-refs` 当前有按唯一名称回退和通用 JSONL 截断限制，只是匹配辅助，不能独自决定写入。自动执行前需收紧匹配规则；长期可靠恢复建议上游增加稳定资源键/刷新接口。

## 文件夹与相册写入

- 文件夹整理用 files.mkdir/copy，目标只能是智能体专属目录及子目录。先通过 files.list rootScope=dedicated 取得真实根引用和路径；源可来自授权个人云，复制保留原图。
- 相册使用 album.create + fileRefs 或 album.add；故事使用 album.create kind=story 并指定封面与选图。它们是相册资源，不是云盘目录移动。
- 云端文件 move/delete/rename 未公开。目标不受支持时明确限制，不能擅自替换目标后称已满足需求。
- 按当前 schema 生成参数并遵守数量/长度限制；多个写动作用底层 orchestrate 冻结计划、确认和执行。索引产物上传见 [cloud-artifacts.md](cloud-artifacts.md)。
- 保存真实 operationRef、逐项结果和目标引用。建册加图 PARTIAL 时不重建已成功相册；异步复制按 status/nextAction 处理，未知项先对账。最终用 album.files 或 files.list 核对相应目标，不自动生成公开分享链接代替查看结果。
