#!/usr/bin/env bash
# AgenticAPI 健康检查自愈脚本（兜底：后端进程活着但数据库连接坏死时自动重启）
# crontab 每分钟调用（安装命令见部署记录）：
#   * * * * * flock -n /tmp/agenticapi-hc.lock /bin/bash ~/projects/AgenticAPI/ops/agenticapi-healthcheck.sh
# 探测对象 127.0.0.1:2027/models：公开且走数据库的接口（2026-11-14 故障时的报错点），
# 直连后端不经 nginx，nginx 自身故障不会误触发重启。
# 状态与日志在 ~/projects/healthcheck/（仓库外，不弄脏服务器 git 工作区）。
# 测试故障路径可用环境变量覆盖：
#   PROBE_URL=http://127.0.0.1:9999 RESTART_ENABLED=0 ./agenticapi-healthcheck.sh

set -u

PROBE_URL="${PROBE_URL:-http://127.0.0.1:2027/models}"
RESTART_ENABLED="${RESTART_ENABLED:-1}"
FAIL_THRESHOLD=3      # 连续失败 N 次才重启，防瞬时抖动误杀
RESTART_COOLDOWN=600  # 重启冷却期（秒）：冷却期内只记日志，防 MySQL 真宕机时反复重启

HC_DIR="$HOME/projects/healthcheck"
LOG_FILE="$HC_DIR/healthcheck.log"
FAIL_COUNT_FILE="$HC_DIR/fail_count"
LAST_RESTART_FILE="$HC_DIR/last_restart"

mkdir -p "$HC_DIR"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG_FILE"; }

if curl -sf -m 10 "$PROBE_URL" > /dev/null 2>&1; then
    # 探活成功：计数归零；若此前处于故障中，补一条自愈记录
    if [ -f "$FAIL_COUNT_FILE" ] && [ "$(cat "$FAIL_COUNT_FILE" 2>/dev/null || echo 0)" -ge 1 ]; then
        log "RECOVERED: 探测恢复，此前连续失败 $(cat "$FAIL_COUNT_FILE") 次"
    fi
    echo 0 > "$FAIL_COUNT_FILE"
    exit 0
fi

# 探活失败：计数 +1
FAILS=$(( $(cat "$FAIL_COUNT_FILE" 2>/dev/null || echo 0) + 1 ))
echo "$FAILS" > "$FAIL_COUNT_FILE"
log "FAIL: 探测失败（连续第 $FAILS 次） $PROBE_URL"
[ "$FAILS" -lt "$FAIL_THRESHOLD" ] && exit 0

# 达到阈值：检查重启冷却期
NOW=$(date +%s)
LAST_RESTART=$(cat "$LAST_RESTART_FILE" 2>/dev/null || echo 0)
if [ $((NOW - LAST_RESTART)) -lt "$RESTART_COOLDOWN" ]; then
    log "SKIP: 已达重启阈值，但距上次重启不足 ${RESTART_COOLDOWN}s，冷却期内不重启"
    exit 0
fi

# 测试模式：不真正执行重启
if [ "$RESTART_ENABLED" != "1" ]; then
    log "DRY: 满足重启条件但 RESTART_ENABLED=$RESTART_ENABLED，跳过（测试模式）"
    exit 0
fi

log "RESTART: 连续失败 $FAILS 次，重启 agenticapi.service"
echo "$NOW" > "$LAST_RESTART_FILE"
if sudo -n systemctl restart agenticapi.service; then
    log "RESTART: systemctl restart 执行成功"
else
    log "RESTART: systemctl restart 执行失败，请人工介入"
fi
