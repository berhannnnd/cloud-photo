# cloud-photo

云盘相册统一 Skill 的顶层项目。

## 发布形态

用户只安装一个 `cloud-photo` Skill。内部模块保持独立维护：

- `cloud-access`：通过官方 `@org-vt43r0t0/cm-cloud-manage` 登录和访问移动云盘文件；不迁移或复制其实现。
- `photo-index`：生成文件元数据、缩略图派生特征和多模态视觉标签，不使用 embedding。
- `index-guidance`：根据索引状态路由搜索、增量索引、复核和批量整理流程。

包内只保留一个可发现的顶层 `SKILL.md`，内部模块使用 references、scripts 或打包库实现。

## 依赖更新

`cloud-photo` 保存 `cm-cloud-manage` 的来源、兼容性范围和已验证版本。执行 Skill 更新检查时：

1. 检查 cloud-photo 自身是否有新版本；
2. 检查 SkillHub 上 `@org-vt43r0t0/cm-cloud-manage` 是否有新版本；
3. 读取变更元数据并执行访问接口兼容性检查；
4. 只有用户明确要求更新且兼容性检查通过，才更新依赖；
5. 依赖更新失败时保留当前可用版本并报告原因。

cloud-photo 更新不会静默替换 cm-cloud-manage，也不会把 cm-cloud-manage 的源码复制进本项目。

当前阶段：项目初始化，尚未实现顶层 Skill 或索引逻辑。
