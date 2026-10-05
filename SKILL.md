---
name: cloud-photo
description: 在云盘中建立可持续更新的照片索引，或根据用户目标整理照片。自动区分“索引照片”和“整理照片”两种模式；通过 cm-cloud-manage 访问中国移动云盘，不把全部照片一次性发送给模型，也不使用 embedding。
---

# Cloud Photo

## 最高优先级展示规则

无论任何场景，用户要求查找、分类、整理或预览照片时，**必须展示分类后的实际图片**。图片展示是结果的必要条件和最高优先级：即使时间、payload、组件能力或候选数量受限，也要先按类别分批展示图片；文件名、路径、标签、数量、统计、操作计划和报告都可以省略、延后或作为辅助信息，但不能用这些文字内容替代图片。没有实际图片展示就不能宣称任务结果已完成。

## 对话内图片展示（必须遵守）

照片展示默认走 Nexus 原生工作区 Markdown 图片链路，不把图片字节放进模型上下文。`preview_pack.py markdown` 会生成短的 `![文件名](.cloud-photo/...)` 画廊；Nexus 会把这些工作区相对路径解析为带权限的 inline preview URL。

如果当前对话需要使用 Nexus `visualize`/`show_widget` 组件展示图片，必须先使用本 Skill 的共享 loopback relay，再用 `preview_pack.py widget --image-base-url ... --image-token ...` 生成 HTML。relay 只传短的受 token 保护的图片 URL，不把图片编码成 Base64；`show_widget` 接收成功仍不等于图片已渲染，必须确认图片实际出现后才算完成。

每个稳定的 workspace 或 owner 使用一个持久 `state-dir` 和 `service-id`。每个对话只生成自己的 `session-id`，调用 `preview_server.py start` 时先复用已经运行的共享服务，再向同一端口注册一个独立 token；不要为每个对话重复起端口。服务默认常驻：任务完成、回复结束或组件渲染成功后都不能顺手关闭服务。一个会话执行 `stop` 只注销自己，不能停止仍被其他对话使用的服务；`stop-service` 只能在用户明确要求关闭服务、确认没有活动会话，并额外传入 `--confirm-close` 时执行。state-dir 必须落在持久工作区或 owner 状态目录，不能放在 `/tmp`。

禁止使用 `file://`、未受本 Skill 管理的 `localhost`/`127.0.0.1` 服务、绝对路径、临时下载 URL 或手工 Base64。不要使用固定端口、全局 `pkill` 或任意 `http.server`。relay 能防止不同会话误用彼此的 token 和 workspace，但同一操作系统用户仍可以故意终止进程；Skill 不能把普通用户进程变成安全边界。若服务失效，先用 `status`，再用相同 `service-id` 和新的会话参数调用 `start` 恢复；不能杀掉未知进程。若工作区图片 URL 无法取得，必须报告“图片预览未完成”，不能用文件名或交付文件卡片代替。

这是一个顶层 Skill，安装后同时提供三个协作模块：

1. **cloud-access**：发现云盘文件、读取元数据、取得缩略图或可访问的图片引用，并把结果写入工作区索引目录。
2. **photo-index**：对照片生成三类标签并维护 manifest：文件元数据、缩略图派生标签、多模态视觉标签。
3. **index-guidance**：把用户的自然语言条件转换成结构化检索条件，先查索引，再只把候选图片交给视觉模型复核。

三个模块可以在 `packages/` 下独立维护，但只能由本顶层 `SKILL.md` 作为可安装入口。模块之间通过 `references/manifest-schema.md` 定义的 JSONL 清单交换数据。

## 模式路由

先读取 [modes.md](references/modes.md) 判断用户意图：

- 用户说“索引、扫描、打标签、建立照片库”时，只走索引模式：扫描、打标签、写入 manifest，不执行云盘整理写操作。
- 用户说“整理、归类、移动、归档、创建相册”时，走整理模式：先检索和视觉复核，输出可审阅的预览计划，得到确认后才执行云盘写操作。
- 同时提出两种要求时，先补齐必要索引，再停在整理预览计划。

## 运行约束

- 使用 `cm-cloud-manage` 完成登录、列目录、读取文件和取得图片引用；不要复制或改写该 Skill 的源码。
- 大规模相册必须分批、可恢复地建立索引。每条记录都要有稳定的 `asset_id`、`source_ref` 和 `schema_version`。
- 不把整库图片放进一次模型请求；检索先在索引上过滤，随后只检查有限候选，必要时再逐张取得原图。
- 标签只使用三类：`file_metadata`、`thumbnail_tags`、`vision_tags`。不要加入 `confidence` 或 embedding 字段。
- 默认只读；移动、重命名、删除、建相册等写操作必须在用户明确要求后调用 `cm-cloud-manage` 的确认流程。
- 索引文件放在云盘智能体专属目录下的 `.cloud-photo/`；每次索引生成带 `scan_id` 的 manifest、checkpoint 和报告并上传，原始照片仍是云盘中的唯一事实来源。

## 工作流

1. 读取 [cloud-access.md](references/cloud-access.md)，确认当前云盘身份、工作区和可用的图片引用。
2. 读取 [manifest-schema.md](references/manifest-schema.md)，用 `scripts/cloud_photo.py validate` 检查或创建清单。
3. 首次或增量整理时读取 [photo-index.md](references/photo-index.md)，按游标扫描文件、生成缩略图标签，再按受控批次请求多模态视觉标签。
4. 用户提出“找照片”时读取 [index-guidance.md](references/index-guidance.md)，先运行本地检索，再对候选进行视觉复核。
5. 索引或整理完成后读取 [preview.md](references/preview.md)、[image-first-preview.md](references/image-first-preview.md) 和 [evidence-pack.md](references/evidence-pack.md)：优先用 `preview_pack.py markdown` 生成每批一个、包含最多 6 张照片的紧凑工作区图片画廊；若使用 `visualize`/`show_widget` 展示图片，先按共享 relay 流程注册会话并生成 relay URL，确认实际渲染后再用 `nexus.deliver_files` 交付清单和报告。
6. 每个阶段都保存 checkpoint；失败或超时只重试未完成的批次，不重放已经确认的云盘写操作。
7. 需要确认外部依赖时读取 [dependencies.md](references/dependencies.md)，运行 `dependency-status`；不要在索引任务中自动升级 `cm-cloud-manage`。

大规模相册的上下文边界、三类索引信息和实测召回流程见 [photo-retrieval-at-scale.md](references/photo-retrieval-at-scale.md)。

## Nexus 对话内展示流程

索引或整理完成后，必须把“做了什么”和“哪些图片对应哪些结果”展示在当前对话中：

1. 先通过 `cloud-access` 取得实际处理或检索命中的原图引用，并让用户能打开真实原图；回复主体必须按分类使用经过尺寸和 payload 检查的图片预览。候选过多时按类别和批次展示，contact sheet 只作总览附件。
2. 用普通文字给出真实数量和状态。
3. 运行 `preview_pack.py markdown` 生成单批原生图片画廊，并把输出的 Markdown 原样放入回复。每批生成一张最多包含 6 张照片的 contact sheet；图片使用 `.cloud-photo/` 下的相对路径，Nexus 负责鉴权和 inline 读取。若必须使用 `show_widget`，先运行一次共享 relay `start`，把输出的 `url`、`token` 和 `session_id` 传给 `preview_pack.py widget`；不要把图片 Base64 读入上下文。
4. 组件实际显示图片后不要自动关闭服务，也不要在任务收尾时顺手执行 `stop-service`；共享服务和当前 session 可以留给其他对话复用。只有用户明确要求注销当前 session 时才执行 `stop`，只有用户明确要求关闭服务时才执行 `stop-service --confirm-close`。用 `nexus.deliver_files` 交付整理报告、manifest、checkpoint 和完整 contact sheet 文件。

只有回复中实际出现可解析的工作区 Markdown 图片，或收到平台原生图片附件后，才算完成预览；仅生成 contact sheet 文件、widget HTML 草稿或 `deliver_files` 文件卡片不算展示成功。禁止读取或拼接任何 `.b64`/`sheets_b64.txt` 文件。
5. 对每张图片优先展示图片本身；稳定云盘链接和路径作为辅助信息，没有稳定链接时只展示云盘路径，不伪造 URL。`file_id` 仅保留在内部 manifest 和执行回执中，不在对话界面展示。若一个批次超过 6 张，先用 `--sheet-offset` 生成下一批画廊，不要连续调用多个 `show_widget`。

不要把 `yun.139.com` 登录页面嵌入 `show_widget`。widget 只承载已经落盘的静态预览和轻量状态，云盘读取和写入仍通过 `cm-cloud-manage 2.0.0` 完成。完整字段和交付文件见 [evidence-pack.md](references/evidence-pack.md)。

## 可执行索引流水线

索引模式优先使用 [index-runner.md](references/index-runner.md) 的预置 runner，不要临时编写全量扫描脚本：

1. `cm-cloud-manage` 输出云盘文件清单 JSONL。
2. `index_runner.py ingest` 过滤非图片并生成 pending manifest。
3. `index_runner.py batch` 生成有界批次、下载请求和下一批游标；宿主按批次取得图片或缩略图。
4. 宿主把下载结果交给 `index_runner.py run-batch`，由 runner 校验文件并生成缩略图任务清单。
5. 多模态模型返回三类标签 JSONL，`index_runner.py apply` 合并并更新 manifest/checkpoint。
6. `report` 生成进度，供 `show_widget` 实时展示；每批都可以独立上传和恢复。

索引模式必须优先使用 `index_runner.py`。如果 runner 已覆盖当前步骤，不得临时创建新的全量扫描、批次合并或 checkpoint 脚本；临时脚本只能处理尚未覆盖的云盘适配边界，并且结果必须回交 runner。

云盘登录、清单读取和图片取得仍由 `cm-cloud-manage` 完成；runner 不读取凭据，也不直接请求云盘 API。

## 配套工具

```text
python scripts/index_runner.py ingest --input cloud-listing.jsonl --output-dir .cloud-photo
python scripts/index_runner.py batch --manifest .cloud-photo/manifest.jsonl --output .cloud-photo/batch.jsonl --limit 32
python scripts/index_runner.py run-batch --manifest .cloud-photo/manifest.jsonl --batch .cloud-photo/batch.jsonl --downloads .cloud-photo/downloads.jsonl --batch-id batch-001
python scripts/preview_pack.py build --items .cloud-photo/organize/candidates.json --thumbnail-dir .cloud-photo/thumbnails --output .cloud-photo/organize/preview
python scripts/preview_pack.py markdown --preview-index .cloud-photo/organize/preview/preview-index.json --output .cloud-photo/organize/preview/gallery-01.md
# show_widget 图片模式：start 的 JSON 中读取 url/token/session_id 后执行
python scripts/preview_server.py start --root "$WORKSPACE" --state-dir "$WORKSPACE/.cloud-photo/runtime/relay" --service-id cloud-photo --session-id "$SESSION_ID"
python scripts/preview_pack.py widget --preview-index .cloud-photo/organize/preview/preview-index.json --output .cloud-photo/organize/preview/widget.html --image-base-url "$RELAY_URL" --image-token "$RELAY_TOKEN" --workspace-root "$WORKSPACE"
# 下一批使用 --sheet-offset 1、2…；把生成的 gallery-02.md 原样放入回复
python scripts/index_runner.py report --manifest .cloud-photo/manifest.jsonl
python scripts/cloud_photo.py mode-detect --text "把我这里照片索引一下"
python scripts/cloud_photo.py init --output .cloud-photo/manifest.jsonl
python scripts/cloud_photo.py validate .cloud-photo/manifest.jsonl
python scripts/cloud_photo.py search .cloud-photo/manifest.jsonl --query "猫 户外"
python scripts/cloud_photo.py resolve-refs --listing fresh-list.json --items candidates.json --output ref-resolution.json
python scripts/cloud_photo.py plan .cloud-photo/manifest.jsonl --query "猫" --target "猫相册"
python scripts/cloud_photo.py merge --base old.jsonl --delta batch.jsonl --output manifest.jsonl
```

工具只负责确定性格式校验、合并和检索；云盘登录、文件下载、缩略图生成和视觉模型调用仍由宿主与 `cm-cloud-manage` 按模块契约完成。
