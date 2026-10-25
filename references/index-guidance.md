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
