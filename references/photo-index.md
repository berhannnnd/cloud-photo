# 内容标签与证据

标签分三组：file_metadata 是文件和 EXIF 事实；thumbnail_tags 是本地/缩略图派生信息；vision_tags 是宿主视觉模型实际观察结果。只允许这些分组，不填臆测置信度。

建议视觉词表保持项目内一致，以下是输出形态，不是默认赋值：

```json
{"asset_id":"asset-example","vision_tags":{"subjects":["猫"],"scene":["室内"],"actions":["睡觉"],"objects":["沙发"],"image_type":"photo","people_count":0,"people":[],"ocr_text":[],"quality":"clear"},"index_state":{"vision_source":"host-model","vision_revision":"label-schema-v1"}}
```

image_type 推荐 photo/screenshot/document/illustration；quality 可用 clear/blurred，无法可靠判断填 null。[] 表示没有可用标签，不作为“确定不存在”的证据；如果需要筛选无人照片，使用 people_count=0。不根据外观猜人物姓名、具体地点或日期。人物分组依赖用户确认的身份标签；同一个视觉人物描述不能视为稳定身份。

media-prepare 只自动生成方向、尺寸、哈希和 EXIF。主色、OCR、主体、场景、动作和清晰度由可用视觉服务生成。缩略图不足以判断时只取候选原图复核；同一批实际未读取的图片不能提交视觉标签。

精确重复用原图 SHA-256。相似连拍与最佳照片由宿主复核后输出保留 ID，调用 select 保存选择；dHash 可生成[相似候选](index-guidance.md#相似候选与复核)，但不自动选最佳；当前没有人脸聚类，不能宣称自动可靠识别人名。标签更新后新建查询结果，已存在快照保持原证据。
