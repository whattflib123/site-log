#!/usr/bin/env bash
# 每 5 分鐘檢查一次系統，有異常就傳 Telegram（scripts/notify.sh）。
#
# 由 /etc/cron.d/sitelog-health 以 root 執行（scripts/sitelog-health.cron）。手動執行：
#   sudo /srv/sitelog/scripts/healthcheck.sh
#
# 檢查項目：
#   - 5 個容器都在跑、有 healthcheck 的都是 healthy
#   - 從外面打得開網盤（Cloudflare → Tunnel → Caddy → Cloudreve 整條路）
#   - 每小時一次：表單存檔的路（WebDAV → Cloudreve → R2）寫得進去、讀得回來
#   - 硬碟用量 < 85%
#   - 最近 26 小時內有成功的備份
#   - form-app 的 log 有 ERROR，或 PDF 沒轉成功（這類是事件，每次出現都通知）
#
# 同一個問題只在「剛壞」和「恢復」時各通知一次；一直沒修好的話每 6 小時再提醒一次。
set -euo pipefail

APP_DIR=${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}
STATE_DIR=${STATE_DIR:-/var/lib/sitelog/health}
BACKUP_LOG=${BACKUP_LOG:-/var/log/sitelog-backup.log}
REMIND_SECONDS=$((6 * 3600))
SERVICES=(caddy cloudflared cloudreve form-app gotenberg)

cd "$APP_DIR"
mkdir -p "$STATE_DIR"
now=$(date +%s)
host=${HOST_LABEL:-sitelog}

problems=()   # 每筆「代號|說明」
fail() { problems+=("$1|$2"); }

# --- 容器 ---
declare -A seen=()
while read -r svc state health; do
  [[ -n $svc ]] || continue
  seen[$svc]=1
  if [[ $state != running ]]; then
    fail "svc-$svc" "容器 ${svc} 沒有在跑（${state}）"
  elif [[ $health == unhealthy ]]; then
    fail "svc-$svc" "容器 ${svc} 狀態 unhealthy"
  fi
done < <(docker compose ps -a --format '{{.Service}} {{.State}} {{.Health}}' 2>/dev/null)
for svc in "${SERVICES[@]}"; do
  [[ -n ${seen[$svc]:-} ]] || fail "svc-$svc" "容器 ${svc} 不存在"
done

# --- 從外面打網盤 ---
drive=$(grep -E '^DRIVE_DOMAIN=' .env | cut -d= -f2- | sed -E 's#^https?://##')
code=$(curl -s -o /dev/null -w '%{http_code}' -m 15 "https://${drive}/api/v4/site/ping" || true)
[[ $code == 200 ]] || fail "drive-public" "從外面打不開網盤 https://${drive}（HTTP ${code:-連不上}）"

# --- 存檔整條路（每小時第一次執行時檢查；其他時候沿用上次結果）---
storage_state=$STATE_DIR/storage
if [[ ! -f $storage_state || $(( now - $(stat -c %Y "$storage_state") )) -ge 3300 ]]; then
  result=$(timeout 90 docker compose exec -T form-app python - < scripts/check_storage.py 2>/dev/null || true)
  echo "${result:-fail: 檢查程式沒有回應}" > "$storage_state"
fi
storage=$(cat "$storage_state")
[[ $storage == ok ]] || fail "storage" "表單存不進網盤／R2：${storage#fail: }（R2 金鑰或 Cloudreve 有問題，填表人員送出會失敗）"

# --- 硬碟 ---
disk=$(df --output=pcent / | tail -1 | tr -dc '0-9')
(( disk < 85 )) || fail "disk" "硬碟已用 ${disk}%"

# --- 備份 ---
last_ok=$(grep -a '備份完成' "$BACKUP_LOG" 2>/dev/null | tail -1 | cut -c1-19 || true)
if [[ -z $last_ok ]]; then
  fail "backup" "找不到成功的備份紀錄（${BACKUP_LOG}）"
elif (( now - $(date -d "$last_ok" +%s) > 26 * 3600 )); then
  fail "backup" "超過 26 小時沒有成功備份（最後一次 ${last_ok}）"
fi

# --- 比對上次狀態：新壞的、恢復的、還沒修好的 ---
state_file=$STATE_DIR/problems
remind_file=$STATE_DIR/last_remind
declare -A before=() current=()
if [[ -f $state_file ]]; then
  while IFS='|' read -r key msg; do [[ -n $key ]] && before[$key]=$msg; done < "$state_file"
fi
new=() recovered=()
for p in "${problems[@]}"; do
  key=${p%%|*}; current[$key]=${p#*|}
  [[ -n ${before[$key]:-} ]] || new+=("• ${p#*|}")
done
for key in "${!before[@]}"; do
  [[ -n ${current[$key]:-} ]] || recovered+=("• ${before[$key]}")
done
printf '%s\n' "${problems[@]}" > "$state_file"

if (( ${#new[@]} )); then
  scripts/notify.sh "🔴 工地隨手記異常（${host}）
$(printf '%s\n' "${new[@]}")" || true
  echo "$now" > "$remind_file"
elif (( ${#problems[@]} )) && (( now - $(cat "$remind_file" 2>/dev/null || echo 0) >= REMIND_SECONDS )); then
  scripts/notify.sh "⏰ 還沒修好（${host}）
$(for p in "${problems[@]}"; do echo "• ${p#*|}"; done)" || true
  echo "$now" > "$remind_file"
fi
if (( ${#recovered[@]} )); then
  scripts/notify.sh "✅ 已恢復（${host}）
$(printf '%s\n' "${recovered[@]}")" || true
fi

# --- form-app log：上次檢查之後的錯誤 ---
since_file=$STATE_DIR/log_since
since=$(cat "$since_file" 2>/dev/null || date -u -d '-5 min' +%Y-%m-%dT%H:%M:%SZ)
date -u -d "@$now" +%Y-%m-%dT%H:%M:%SZ > "$since_file"
# 只看 form-app（Cloudreve 的 log 可能有資料庫設定，不外傳）；每行最多 200 字、最多 5 行
errors=$(docker compose logs --no-color --no-log-prefix --since "$since" --until "$(cat "$since_file")" form-app 2>/dev/null \
           | grep -E ' ERROR | pdf=(failed|not-saved)' | cut -c1-200 || true)
if [[ -n $errors ]]; then
  count=$(wc -l <<<"$errors")
  scripts/notify.sh "⚠️ 表單程式有 ${count} 筆錯誤（${host}）
$(tail -5 <<<"$errors")" || true
fi

echo "$(date "+%F %T") 檢查完成：${#problems[@]} 個問題"
