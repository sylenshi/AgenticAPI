---
name: data-governance
description: 数据治理 SOP：容量统计→导出→备份校验→dry-run 预览→分批清理→复核，强调两段式节奏
triggers: 清理,清库,数据治理,数据库膨胀,瘦身
---

# 数据治理 SOP（防 MySQL 膨胀）

**安全节奏（必须严格遵守）**：统计 → 导出 → dry-run 预览 → 管理员确认 → 真删 → 复核。任何 L2 清理都必须先以 `dry_run=true` 预览，向管理员展示预览数据并明确征得同意后，才能以 `dry_run=false` 发起真删（会再次弹出审批卡片）。

## 执行步骤

1. **容量统计**：`get_chat_record_stats` / `get_log_stats` / `get_aggregate_stats`，按月分布定位大头。
2. **清理建议**：给出建议保留窗口（logs 默认 90 天；chat_record 视业务定，如 180 天；usage_stats 默认 180 天），报给管理员确认。
3. **导出备份**：清理前用 `export_chat_records` / `export_logs` 按即将删除的时间范围导出（或依赖 cleanup 工具的 backup_first=true 自动备份），把下载链接交给管理员。
4. **dry-run 预览**：`cleanup_*` dry_run=true，向管理员报告"预计删除 N 行、时间切点"。
5. **真删**：管理员在审批卡片批准 dry_run=false 调用；观察实删行数。
6. **复核**：重新执行第 1 步统计，对比前后差异，报告释放效果；提示可选的 `OPTIMIZE TABLE`（不自动执行）。

## 判据

- 删除行数与 dry-run 预览偏差超过 5% → 说明期间有新数据写入，属正常，报告即可；
- 单表超过百万行 → 建议分多次清理（先按月切几刀），避免单次删除时间过长；
- 导出文件下载链接 24h 过期 → 提醒管理员及时下载保存。

## 红线

- 绝不使用 TRUNCATE / DROP（工具层面也不提供）；
- 真删前必须有 dry-run 预览 + 双重审批记录；
- backup_first=true 是默认，管理员明确说不需要备份时才可关。
