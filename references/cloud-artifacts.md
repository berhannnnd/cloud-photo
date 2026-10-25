# 云盘索引产物

索引产物可通过 cm-cloud-manage 公开 files.mkdir/upload 写入智能体专属目录。上传索引不改变原照片的位置。

## 目录布局

通过 files.list rootScope=dedicated 取得当前真实专属根引用，再创建或定位 `.cloud-photo`：

```text
<智能体专属目录>/.cloud-photo/
  manifest-<scan_id>.jsonl
  checkpoint-<scan_id>.json
  report-<scan_id>.json
```

每次更新生成新版本文件，保存 scan_id 与实际上传回执。manifest 的 asset_id 是本地身份；当前 v1 source_ref.file_id 可能是短期 fileRef，不能作为下次运行永久可用的云盘 ID。

## 上传与恢复

1. 本地完成批次合并和 schema 校验。
2. 取得真实 folderRef；同名目录先定位唯一现有对象，不盲目重复创建。
3. 新建目录与多个上传动作使用底层 orchestrate 固定为一份可承载的计划；依赖前步目录时用其产物引用。
4. 按底层确认与执行流程处理，保存 operationRef、实际文件名和结果；未知状态先核对，成功项不重复上传。
5. 新会话从公开 list/download 读取对应版本，验证 scan_id、格式与完整性，再恢复本地状态和短期引用。

索引不保存授权凭据、确认 token、临时下载 URL 或图片二进制。持久工作区已有有效 manifest 时优先复用；不完整索引按 checkpoint 继续，不能当作整库已经索引完成。
