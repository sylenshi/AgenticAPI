---
name: model-onboarding
description: 新模型上线检查单：定价合理性→渠道绑定与一致性→拨测验证→上线文案
triggers: 新模型,上线模型,模型检查
---

# 新模型上线检查单 SOP

## 检查步骤

1. **配置核查**：`get_model_info`（指定新模型名），确认：
   - 定价四项（输入/缓存/输出/按次）非零且量级与同类模型相当（明显偏离 10 倍以上要提醒）；
   - `model_group`（free/vip）与预期一致；
   - `context_length` / `max_tokens` 与上游规格匹配；
   - `channels` 已绑定且渠道启用；`upstream_name` 映射（若有）拼写正确。
2. **绑定一致性**：`check_binding_consistency`，确认无单向绑定/孤儿引用。
3. **拨测验证**：`test_model`（单模型，逐渠道），记录时延基线；必要时 `test_channel` scope=all 验证渠道侧支持列表。
4. **上线文案**：给出一段可直接用的公告文案（模型名、分组、定价、适用场景）。

## 判据

- 拨测全部渠道失败 → 不具备上线条件，给出归因（参考 channel-troubleshooting）；
- 定价偏离同类 10 倍以上 → 提醒管理员复核（Agent 不修改定价）；
- is_log 开关：建议生产默认关闭，仅排障期开启。

## 边界提醒

Agent 只读模型配置；创建/改价/改映射请管理员在模型管理页操作，Agent 可提供字段级建议。
