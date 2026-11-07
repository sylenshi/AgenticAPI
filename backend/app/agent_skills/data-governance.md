---
name: data-governance
description: 数据治理 SOP（v0.11.0 沙箱连库版）：站内数据表现状说明 + 沙箱 pymysql 脚本完成容量统计、样本预览、分批清理与复核
triggers: 清理,清库,数据治理,数据库膨胀,瘦身,数据统计,存储占用
---

# 数据治理 SOP（沙箱连库版，v0.11.0）

**能力来源**：原 8 个数据治理工具已下线，改用容器沙箱内执行的 pymysql 脚本。沙箱已注入站内 MySQL 连接环境变量（`MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE`），镜像内已装 pymysql。每条沙箱命令是否弹审批由会话审批档位决定。

**安全节奏（必须严格遵守）**：统计 → 清理条件确认 → 样本预览 → 删除量预览 → 管理员确认 → 分批真删 → 复核。

## 站内数据表现状（详细口径见 docs/数据库设计文档.md）

| 表 | 内容 | 治理口径 |
|---|---|---|
| `logs` | 统一日志宽表（type=api/login/admin/user），含 token 数 / 费用 / 耗时 / 渠道 | 增长最快，默认治理对象（建议保留 90 天） |
| `chat_record` | 出站模型调用对话全文（输入/推理/输出，MediumText），仅 is_log=1 且 token≤5000 的调用落库 | 单行大、最占空间（建议保留 180 天起，视业务定） |
| `usage_stats` | 调用量小时桶预聚合（stat_hour+user_id+model_name 唯一约束） | 建议保留 180 天 |
| `usage_summary` | 单行全站累计计数器 | 不增长，不清理 |
| `agent_session` / `agent_message` | 维护 Agent 会话与消息 | 有自动惰性清理（每用户 50 个 / 30 天），不要手工清理 |
| `user` / `api_key` / `llm_channels` / `llm_models` / `redeem_code` / `system_config` | 配置与资金表 | 严禁 DELETE / UPDATE |

## 执行步骤

1. **容量统计**：脚本 A，输出全表行数/占用排序 + 三张治理表按月分布，定位大头；
2. **清理建议**：给出保留窗口建议报管理员确认，确定表名与保留天数（TABLE / DAYS）；
3. **样本预览**：脚本 B，抽即将删除范围的少量行（LIMIT ≤ 20）让管理员确认条件正确；
4. **删除量预览**：脚本 C 以 `DRY=1` 运行，报告"预计删除 N 行"；
5. **分批真删**：管理员确认后脚本 C 以 `DRY=0` 运行；每批 5000 行、批间休止 0.2s；
6. **复核**：重跑脚本 A 对比前后差异；如需回收磁盘空间，提示管理员登服务器手工 `OPTIMIZE TABLE`（不自动执行）。

## 脚本模板

### A. 容量统计

```sh
python3 - <<'PY'
import os, pymysql
conn = pymysql.connect(host=os.environ["MYSQL_HOST"], port=int(os.environ["MYSQL_PORT"]),
    user=os.environ["MYSQL_USER"], password=os.environ["MYSQL_PASSWORD"],
    database=os.environ["MYSQL_DATABASE"], charset="utf8mb4")
cur = conn.cursor()
cur.execute("""SELECT TABLE_NAME, TABLE_ROWS, ROUND((DATA_LENGTH+INDEX_LENGTH)/1048576,1)
  FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()
  ORDER BY DATA_LENGTH+INDEX_LENGTH DESC""")
print("table\trows\tMB")
for r in cur.fetchall():
    print("\t".join(str(x) for x in r))
for t in ("logs", "chat_record", "usage_stats"):
    cur.execute(f"SELECT DATE_FORMAT(create_time,'%Y-%m'), COUNT(*) FROM {t} GROUP BY 1 ORDER BY 1")
    print(t, cur.fetchall())
PY
```

### B. 样本预览（表与条件按第 2 步结论替换；永远显式列名，禁 SELECT *）

```sh
python3 - <<'PY'
import os, pymysql
conn = pymysql.connect(host=os.environ["MYSQL_HOST"], port=int(os.environ["MYSQL_PORT"]),
    user=os.environ["MYSQL_USER"], password=os.environ["MYSQL_PASSWORD"],
    database=os.environ["MYSQL_DATABASE"], charset="utf8mb4")
cur = conn.cursor()
cur.execute("SELECT id, type, model_name, cost, create_time FROM logs \
            WHERE create_time < DATE_SUB(NOW(), INTERVAL 90 DAY) ORDER BY id LIMIT 20")
for r in cur.fetchall():
    print(r)
PY
```

### C. 分批清理（DRY=1 预览 / DRY=0 真删；TABLE 与 DAYS 按第 2 步结论替换）

```sh
python3 - <<'PY'
import os, time, pymysql
TABLE, DAYS, DRY = "logs", 90, 1
COND = f"create_time < DATE_SUB(NOW(), INTERVAL {DAYS} DAY)"
conn = pymysql.connect(host=os.environ["MYSQL_HOST"], port=int(os.environ["MYSQL_PORT"]),
    user=os.environ["MYSQL_USER"], password=os.environ["MYSQL_PASSWORD"],
    database=os.environ["MYSQL_DATABASE"], charset="utf8mb4")
cur = conn.cursor()
cur.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE {COND}")
total = cur.fetchone()[0]
print(f"[{TABLE}] would delete: {total}" if DRY else f"deleting {total} rows ...")
if DRY:
    raise SystemExit
done = 0
while True:
    n = cur.execute(f"DELETE FROM {TABLE} WHERE {COND} LIMIT 5000")
    conn.commit()
    done += n
    if n < 5000:
        break
    time.sleep(0.2)
cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
print(f"deleted {done}, remaining {cur.fetchone()[0]}")
PY
```

## 判据

- 实删行数与预览偏差超过 5% → 期间有新数据写入，属正常，报告即可；
- 单表超过百万行 → 分多次清理（先按月切几刀），防单命令超时（沙箱单命令上限 120s）；
- 一次跑不完 → 原条件重跑即可（幂等），不要加大单批 LIMIT；
- 统计打印保持精简：只打行数与汇总，不打印全量明细（沙箱输出上限 64KB 保尾部）。

## 红线

- 绝不使用 TRUNCATE / DROP / ALTER；DELETE 仅限 `logs` / `chat_record` / `usage_stats` 三表；
- `user` / `api_key` / `llm_channels` / `llm_models` / `redeem_code` / `system_config` / `agent_*` 严禁 DELETE / UPDATE；
- 严禁查询 `llm_channels.api_key`、`user.password` 等凭证列——SELECT 永远显式列出业务列，不用 SELECT *；
- 大数据导出无法经沙箱回传（stdout 上限 64KB）：小样本预览走脚本 B；全量导出 / 备份提示管理员登服务器用 mysqldump；
- 真删前必须完成"删除量预览 → 管理员明确同意"两步；管理员拒绝后调整方案（如缩小时间范围），不原样重试。
