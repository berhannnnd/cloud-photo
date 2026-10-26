# 查询与持久结果集

自然语言由宿主模型解析成 QuerySpec，查询引擎不内置语言模型、不调用 embedding。优先查询当前标签实际使用的词；必要时把同义词展开为 any。不能把整个自然语言句子放进文件名 keyword。

## QuerySpec

字段必须是 file_metadata、thumbnail_tags、vision_tags 或 index_state 下一级字段。运算符：eq（数组表示任一元素相等）、contains（子串）、in、gte、lte、between（含两端）、exists。逻辑节点 all/any 使用非空数组，not 接收一个节点。

```json
{"all":[
  {"any":[
    {"field":"vision_tags.scene","op":"contains","value":"海边"},
    {"field":"vision_tags.scene","op":"contains","value":"beach"}
  ]},
  {"not":{"field":"vision_tags.image_type","op":"eq","value":"screenshot"}},
  {"field":"file_metadata.taken_at","op":"between","value":["2025-01-01T00:00:00","2025-12-31T23:59:59.999999"]}
]}
```

示例为本地拍摄时钟；有时区的时间使用带偏移的范围。带时区与无时区混合比较返回 unknown，不能擅自认定同一时区。null、空字符串和空数组表示未知；false/0 是实际值。NOT unknown 仍为 unknown，避免把没有截图标签的照片当作确定非截图。

## 地点、来源与目录

这三类条件都是普通字段，不需要额外运算符：

- **地点**：用 `between` 查询 `file_metadata.gps_lat` / `gps_lon`。优先采用用户给定范围或可用地理编码工具的结果，注明地名、范围来源及坐标系（与 EXIF 的 WGS84 对齐）。同名地点先明确城市/国家；没有可靠范围时说明限制，不能把模型估算当成精确城市或街区边界。用户接受近似检索时才使用明确标注的估算范围。跨 180° 经线拆成两个经度区间放进 any。矩形不等于行政边界，边缘候选需复核。
- **按地点分组**：使用 `file_metadata.geo_cell_3`、`geo_cell_4` 或 `geo_cell_5`。这是不同精度的地理网格，不是城市/景点；网格边界会拆开相邻照片，尺寸随纬度变化。组名默认保留网格编号；有可靠逆地理编码依据时才用地名，无法确定时写“位置组 <网格编号>”。默认不展示精确坐标；用户明确要求时可展示已有 EXIF 坐标并注明来源。
- **来源**：设备用 `file_metadata.capture_device`（phone/camera/capture），渠道用 `file_metadata.save_channel`（screenshot/wechat/qq/download），可同时筛选。规则推断须结合对应 evidence 展示，不宣称已证明真实来源。旧 `source_kind` 仅兼容历史查询。“截图”可用 any 合并 `save_channel=screenshot` 与 `vision_tags.image_type=screenshot`。
- **目录**：`file_metadata.folder` 是云盘父目录，用 `contains` 或 `eq` 限定或排除文件夹。

```json
{"all":[
  {"field":"file_metadata.gps_lat","op":"between","value":[30.10,30.45]},
  {"field":"file_metadata.gps_lon","op":"between","value":[119.95,120.40]},
  {"not":{"field":"file_metadata.save_channel","op":"in","value":["screenshot","wechat"]}}
]}
```

GPS 只来自原图 EXIF。微信/QQ 转发图、截图和被压缩的图片通常没有 GPS，按地点查询时进入 unknown，需单独告知数量；不能用画面内容、文件名或目录名推断拍摄地点。查询地点前用 report 查看 `file_metadata.gps_lat` 覆盖率。

## 命令

以下 `$STATE` 是当前用户工作区，`$OWNER` 是宿主绑定身份：

```bash
python3 scripts/cloud_photo.py query --state-dir "$STATE" --owner "$OWNER" --manifest "$STATE/manifest.jsonl" --spec query.json --complete
python3 scripts/cloud_photo.py result-show --state-dir "$STATE" --owner "$OWNER" --result <result-id> --limit 20
python3 scripts/cloud_photo.py refine --state-dir "$STATE" --owner "$OWNER" --result <result-id> --spec refine.json
python3 scripts/cloud_photo.py select --state-dir "$STATE" --owner "$OWNER" --result <result-id> --ids selected-ids.json
python3 scripts/cloud_photo.py dedupe --state-dir "$STATE" --owner "$OWNER" --result <result-id>
```

只有范围已经核实完整才能加 --complete；否则结果保留 coverage.complete=false。query 不限制成员数，result-show 仅分页展示；excluded/unknown 可用 --bucket 查看。select 接收 asset_id 数组，拒绝父集合以外成员。

refine 只操作父集合的 items，不把 unknown 自动纳入。需要补标签或放宽条件时，在明确的来源范围重新 query，或选回先前祖先；历史快照不原地修改。dedupe 只依据本地原图 sha256，缺哈希保留并列在 unverified_asset_ids，绝不声称相似精选。

## 引用刷新

从云盘公开详情取得新清单后：

```bash
python3 scripts/cloud_photo.py refresh-refs --state-dir "$STATE" --owner "$OWNER" --result <result-id> --listing fresh-details.json
```

需规范路径、大小、修改时间都匹配且唯一。任何成员不明确就停止，不按文件名或轮换的 fileRef 猜测。成功生成新的结果 ID，再生成新计划；不能刷新后沿用旧云端确认。

## 相似候选与复核

media-prepare 从实际图片生成 EXIF 方向校正后的 64 位 dHash。以下命令仅生成候选，不删除照片、不自动选最佳：

```bash
python3 scripts/cloud_photo.py similar-candidates --state-dir "$STATE" --owner "$OWNER" --result <result-id> --distance 4
python3 scripts/cloud_photo.py review-show --state-dir "$STATE" --owner "$OWNER" --review <review-id> --offset 0 --limit 20
```

距离允许 0–8，默认 4；距离 0 也不是字节完全相同的证明。每组是候选边的连通分量，A 接近 B、B 接近 C 不代表 A 接近 C。review 保存来源结果 ID/摘要、成员及每条边距离；模型查看实际图片后，通过 select 在原结果中明确保留成员。缺失或算法版本不一致的哈希列入 unverified_asset_ids，不作为不相似的证明。

当前比较为 O(n²)，单次最多 10000 张、最多 20000 条候选边；超限明确拒绝，缩小范围后重试。裁剪、旋转、同人物不同构图可能漏检，颜色不同或简单画面可能误报。候选快照不改变源结果，review-show 分页不截断存储成员。

执行语义查询前可运行 index_runner.py report，查看字段覆盖。处理状态 complete 不能替代 quality/people 等字段的 populated 统计。
