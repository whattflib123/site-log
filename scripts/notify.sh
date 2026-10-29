#!/usr/bin/env bash
# 傳一則 Telegram 訊息到維護群組。給 healthcheck.sh、backup.sh 用，也可以手動測試：
#   sudo /srv/sitelog/scripts/notify.sh "測試訊息"
#
# 設定放在 /etc/sitelog/notify.env（root、權限 600），不放 .env，不給任何容器：
#   TG_BOT_TOKEN=...     # Telegram bot token（@BotFather 建立）
#   TG_CHAT_ID=...       # 群組的 chat_id（負數，例：-100xxxxxxxxxx）
# 沒有這個檔就只印出訊息、不傳送，不讓呼叫的腳本失敗。
set -euo pipefail

ENV_FILE=${NOTIFY_ENV:-/etc/sitelog/notify.env}
text=${1:?用法：notify.sh "訊息"}

if [[ ! -r $ENV_FILE ]]; then
  echo "$(date "+%F %T") 沒有 $ENV_FILE，不傳送：$text" >&2
  exit 0
fi
set -a
# shellcheck source=/dev/null
. "$ENV_FILE"
set +a
: "${TG_BOT_TOKEN:?notify.env 缺 TG_BOT_TOKEN}" "${TG_CHAT_ID:?notify.env 缺 TG_CHAT_ID}"

# 網址（含 token）從 stdin 給 curl，不出現在指令列，ps 看不到
if ! curl -fsS -m 15 --retry 2 -o /dev/null -K - \
       --data-urlencode "chat_id=${TG_CHAT_ID}" \
       --data-urlencode "text=${text}" \
       --data-urlencode "disable_web_page_preview=true" \
       <<<"url = \"https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage\""; then
  echo "$(date "+%F %T") Telegram 傳送失敗：$text" >&2
  exit 1
fi
