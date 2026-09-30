# photo-index 模块

photo-index 分三个阶段工作：

1. **扫描**：通过 cloud-access 分页读取照片元数据，按稳定 `asset_id` 去重，写入 `pending` 记录。
2. **缩略图标签**：在本地对缩略图提取方向、尺寸、主色、场景提示和 OCR 等派生信息；生成缩略图失败时保留文件元数据并标记 `partial`。
3. **视觉标签**：将缩略图或受控图片引用按批次交给多模态文本图片模型，要求只返回 `vision_tags` 对象；模型结果先经过 schema 校验，再合并到对应记录。

不使用 embedding，也不把整库图片直接放入对话上下文。每批完成后原子写入 `batches/<batch-id>.jsonl`，再合并到 manifest，并记录 checkpoint（扫描游标、批次 ID、已完成 asset_id、失败 asset_id）。重复运行按 `source_hash` 跳过未变化的资产。

三类标签的边界：

- `file_metadata`：云盘和图片文件本身提供的事实。
- `thumbnail_tags`：由缩略图或本地轻量处理得到的派生事实。
- `vision_tags`：多模态模型根据图片内容生成的可检索词；模型不返回置信度。
