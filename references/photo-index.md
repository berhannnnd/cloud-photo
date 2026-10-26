# 内容标签与证据

标签分三组：file_metadata 是文件和 EXIF 事实；thumbnail_tags 是本地/缩略图派生信息；vision_tags 是宿主视觉模型实际观察结果。只允许这些分组，不填臆测置信度。

建议视觉词表保持项目内一致，以下是输出形态，不是默认赋值：

```json
{"asset_id":"asset-example","vision_tags":{"subjects":["猫"],"scene":["室内"],"actions":["睡觉"],"objects":["沙发"],"image_type":"photo","people_count":0,"people":[],"ocr_text":[],"quality":"clear"},"index_state":{"vision_source":"host-model","vision_revision":"label-schema-v1"}}
```

image_type 推荐 photo/screenshot/document/illustration；quality 可用 clear/blurred，无法可靠判断填 null。[] 表示没有可用标签，不作为“确定不存在”的证据；如果需要筛选无人照片，使用 people_count=0。不根据外观猜人物姓名、具体地点或日期。人物分组依赖用户确认的身份标签；同一个视觉人物描述不能视为稳定身份。

media-prepare 只自动生成方向、尺寸、哈希、EXIF 拍摄时间、相机型号与 GPS。主色、OCR、主体、场景、动作和清晰度由可用视觉服务生成。缩略图不足以判断时只取候选原图复核；同一批实际未读取的图片不能提交视觉标签。

## 照片来源

来源拆成两个独立维度：

- `capture_device`：phone、camera、capture（有拍摄线索但设备类型不确定）。仅已知厂商与型号组合细化为 phone/camera；仅有厂商或文件名线索时用 capture。
- `save_channel`：screenshot、wechat、qq、download。文件名或当前目录只提供渠道线索，不能证明真实传输历史；screenshot 是兼容的截图线索，需与视觉 image_type 交叉核实。
- 两者分别带 `_evidence` 和 `_basis` 字段；basis 为 rule-inference，表示规则推断，不是原始事实。未命中为 null。比如 iPhone 照片放在 Downloads 下，仍可同时命中 phone 和 download。

`source_kind` / `source_evidence` 保留兼容，仍以渠道优先、设备其次生成。新查询使用拆分字段，避免把“手机拍摄”和“微信保存”当成互斥条件。ingest 和 apply 根据合并后的名称、路径、EXIF 重算；旧索引需重新 ingest，已有结果快照需 refresh-index 后才能使用新字段，不改写历史快照。

## 地点

media-prepare 只读取原图 EXIF GPS，写入 `gps_lat`/`gps_lon` 和三级 `geo_cell`。不根据画面、文件名或目录补写拍摄 GPS。地名检索与命名需按 [地点查询规则](index-guidance.md#地点来源与目录) 使用明确范围或地理编码依据。默认预览与对话只展示粗粒度地点或网格编号，不主动展示精确坐标；用户明确要求查看位置时可展示已有 EXIF 坐标，并说明来源。云端备份索引前须提醒用户其中含位置信息。云盘下载若经过压缩，EXIF 可能缺失，接入时先用一张已知带 GPS 的原图验证。

精确重复用原图 SHA-256。相似连拍与最佳照片由宿主复核后输出保留 ID，调用 select 保存选择；dHash 可生成[相似候选](index-guidance.md#相似候选与复核)，但不自动选最佳；当前没有人脸聚类，不能宣称自动可靠识别人名。标签更新后新建查询结果，已存在快照保持原证据。
