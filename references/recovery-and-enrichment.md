# 长任务恢复与按需补标

## 进度与恢复

`operation-progress --state-dir "$STATE" --owner "$OWNER" --plan <id>` 读取本地操作回执，不重新提交、不调用上游。显示回执时间、上游计数和已观察步骤；步骤条数不是照片数，也不是完成百分比。

云端执行默认进程期限为 1800 秒，读取默认 120 秒，可用 `--timeout <秒>` 配置。宿主应使用自己的后台执行/进程句柄等待机制，并保存句柄；不要用短于执行期限的外层命令超时强杀。进程期限不是云端完成承诺，超时仍记 UNKNOWN，不能自动重试。

会话恢复先读取原 plan/result ID 和 operation-progress。UNKNOWN 或 RUNNING 用 cloud-status 查询原 operation；必须检查实际 nextAction。超时不是失败证明，已完成步骤不重放。进程句柄存在时先等待原进程；句柄已终止后再对账。

`reconcile-plan --state-dir "$STATE" --owner "$OWNER" --plan <id> --listing target-listing.json` 保存本地对账记录。多组计划必须用 `--group` 指定唯一组；输入应是该目标完整分页汇总的公开回执。调用者必须核实目标引用，不把其他同名目录的清单传入。输出元数据匹配/缺失/多余数量；重复名称大小组合列为歧义，原操作非终态时禁止准备剩余项。

对账使用目标的公开分页列表，取尽后按原冻结计划比较成员；文件名重复时必须补其他可靠证据，不按同名自动判定。确认原操作终态和实际已完成成员后，select 剩余成员生成新计划。原操作还在运行、状态未知或读回不完整时，不生成执行“剩余项”的新请求。上游没有取消接口时不假装已经停止。

## 候选内补标

```bash
python3 scripts/cloud_photo.py enrichment-plan --state-dir "$STATE" --owner "$OWNER" --result <id> --fields quality,people_count --limit 32
```

仅从该结果的 items 选缺失字段，生成持久 request ID 和当前批次任务。0/false 是已知值；空数组/null/空字符串为未知。质量和 OCR 要求查看原图，其余可先用缩略图。任务不调用模型、不自行取图；由宿主按真实媒体能力看图，未知仍留空，人物姓名须用户确认。

任务携带 asset_id、source_ref、所需字段和来源结果摘要。模型只提交本批成员的标签，通过 `enrichment-apply --state-dir "$STATE" --owner "$OWNER" --request <request-id> --manifest "$STATE/manifest.jsonl" --labels labels.jsonl` 写入原 manifest。该入口拒绝批次外成员、未请求字段和已变化的原图哈希；没有已验证原图哈希时先完成取图/元数据阶段。然后刷新原选集的证据：

```bash
python3 scripts/cloud_photo.py refresh-index --state-dir "$STATE" --owner "$OWNER" --result <id> --manifest "$STATE/manifest.jsonl"
```

只更新原 items，不引入任何新成员；保留旧快照。原图哈希不一致、资产消失或缺少可验证身份时拒绝。无哈希时仅接受相同规范路径及完整大小/修改时间指纹，这不是字节一致证明。新结果没有重新应用旧条件，使用新 ID 再 refine。下一批补标应针对刷新后的结果生成，避免重复请求已经补齐的字段。

此流程补足缺失证据，不承诺人脸识别或审美模型。某字段依旧无法识别时应报告未知数量，不无限重试。

## 取图失败恢复

使用 media-index 固定本批成员、合并成功与失败状态。不能仅凭退出码、文件存在或批次执行过判断完成：检查 index-report.json 的 index_applied、status、media_complete、failed。media_complete 只表示取图与元数据阶段完成，不代表视觉标签齐全。checkpoint.processed_asset_ids 表示处理过，可能包含 error，不能当作成功清单。

- 空文件、缺文件、大小/已有哈希不一致或下载失败：标记 error，输出 retry.batch.jsonl，仅包含需重新取图的成员。不要用数据集原图覆盖失败下载并宣称云端验证成功。
- 解码失败：先核对内容、格式和 Pillow 解码能力；列入 needs_review，不自动无限重新下载。GPS/相机字段缺失不是解码失败。
- 原失败文件和回执保留；重新下载到新的目录，避免 conflictPolicy=fail 被旧空文件阻挡。不要删除或覆盖成功文件。

```bash
python3 scripts/cloud_photo.py cloud-download --skill-dir "$CM_SKILL" --batch "$STATE/media/batch-001/retry.batch.jsonl" --directory "$STATE/retry-downloads/attempt-001" --output "$STATE/retry-downloads-001.jsonl"
python3 scripts/cloud_photo.py media-index --manifest "$STATE/manifest.jsonl" --batch "$STATE/media/batch-001/retry.batch.jsonl" --downloads "$STATE/retry-downloads-001.jsonl" --directory "$STATE/media/retry-001"
```

retry_count 为 0 时不调用 cloud-download。重试再次失败则报告错误并检查权限/网络，不循环重试。引用过期先通过公开接口刷新并重新生成相同成员批次；不得读取私有台账。media-index 拒绝成员元数据/引用已变化的旧 batch。命令中断时检查现有 manifest 和报告，以同一范围的新批次恢复；禁止重放相簿创建、复制等云端写操作。

底层 media-prepare 仍可单独使用；它不修改 manifest，失败标签在 failure.labels.jsonl，不能只 apply 成功标签后宣称整批完成。优先使用 media-index，避免宿主自行拼接恢复脚本。
