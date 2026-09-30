# cloud-access 模块

该模块只负责访问边界，不实现中国移动云盘 API。所有云盘操作通过已安装的 `cm-cloud-manage` 完成：登录状态检查、目录分页、文件元数据、缩略图/临时图片引用和按文件 ID 重新读取。

## 输出给 photo-index 的最小记录

```json
{"asset_id":"cm:file-id","source_ref":{"provider":"cm-cloud-manage","file_id":"file-id","path":"/照片/2026/IMG.JPG"},"file_metadata":{}}
```

不要把访问令牌、cookie、二维码或临时下载 URL 写入 manifest。临时 URL 只在当前批次内使用，过期后按 `file_id` 重新取得。工作区目录建议：

```text
.cloud-photo/
  manifest.jsonl
  checkpoints/<scan-id>.json
  batches/<batch-id>.jsonl
  thumbnails/<asset-id>.<ext>
  reports/<scan-id>.json
```

访问模块的变更必须只影响 `packages/cloud-access/`，并保持上述输出契约不变。


## 当前适配版本

本模块固定按 `@org-vt43r0t0/cm-cloud-manage` 2.0.0 的能力边界编排。详细差异见 [cm-cloud-compatibility.md](cm-cloud-compatibility.md)：个人云可以全盘读取和下载，但文件写入只落智能体专属目录；文件层面没有移动、删除、改名，整理文件夹时只能复制，整理相簿时使用相簿 API。


索引产物上传使用 `files mkdir` / `files upload` 写入专属目录；它不代表原始照片已被移动。

## 文件复制与整理写入

- 文件夹整理使用 `cmcloud files copy --resources '<JSON 数组>' --destinationRef <folderRef>`。源文件可以来自个人云任意可读位置，目标目录必须是智能体专属目录或其子目录；原照片保持不变。
- `files copy` 是异步任务。命令返回受理成功不等于所有文件复制成功；必须保存 operation 引用，查询 `cmcloud operation status` 的逐项 succeeded/failed 结果，最后重新 `cmcloud files list` 目标目录对账。
- 一批复制可以提交多个文件引用。不要在 Skill 中臆造批量上限；实际参数和限制以当前 `cm-cloud-manage` schema/help 为准。批量失败时按逐项结果更新整理报告，未知状态不得自动重放。
- 复制前先展示图片优先的整理预览，包含候选图片、目标路径和“复制后原图保留”；用户确认后再走计划 → 确认 → 执行。
- 相册整理优先调用 album 能力把图片加入相簿，不把相册操作伪装成文件复制；相簿与文件夹的结果分别对账。
