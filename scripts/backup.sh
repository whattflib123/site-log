#!/usr/bin/env bash
# 備份 Cloudreve 資料庫（網盤檔案清單的唯一來源）到 R2 備份 bucket 的 backups/，保留最近 7 份。
#
# 每天由 /etc/cron.d/sitelog-backup 以 root 執行（scripts/sitelog-backup.cron）。手動執行：
#   sudo /srv/sitelog/scripts/backup.sh
#
# 憑證放在 /etc/sitelog/backup.env（root、權限 600），不放 .env，不給任何容器：
#   BACKUP_ENDPOINT=https://<帳戶 ID>.r2.cloudflarestorage.com
#   BACKUP_BUCKET=sitelog-backup
#   AWS_ACCESS_KEY_ID=...        # R2 帳戶 API 權杖 r2-sitelog-backup：只對 sitelog-backup 有「物件讀取和寫入」
#   AWS_SECRET_ACCESS_KEY=...
#
# 備份內容：cloudreve.db（sqlite3 .backup 的一致性快照，Cloudreve 執行中也安全）＋ conf.ini
#          ＋ projects.json（/admin 的共用工程清單，有的話）。
# 網盤裡的檔案本身在 R2 的 Cloudreve bucket，不在這裡。
set -euo pipefail

APP_DIR=${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}
ENV_FILE=${BACKUP_ENV:-/etc/sitelog/backup.env}
KEEP=${KEEP:-7}
AWS_CLI_IMAGE=amazon/aws-cli:2.39.0
DATA=$APP_DIR/data/cloudreve

# 任何一步失敗都馬上傳 Telegram（healthcheck.sh 也會在 26 小時沒備份時再提醒）
trap '"$APP_DIR/scripts/notify.sh" "🔴 工地隨手記備份失敗（sitelog，backup.sh 第 ${LINENO} 行），看 /var/log/sitelog-backup.log" || true' ERR

set -a
# shellcheck source=/dev/null
. "$ENV_FILE"
set +a
: "${BACKUP_ENDPOINT:?backup.env 缺 BACKUP_ENDPOINT}" "${BACKUP_BUCKET:?backup.env 缺 BACKUP_BUCKET}"
: "${AWS_ACCESS_KEY_ID:?backup.env 缺 AWS_ACCESS_KEY_ID}" "${AWS_SECRET_ACCESS_KEY:?backup.env 缺 AWS_SECRET_ACCESS_KEY}"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
name="cloudreve-$(date +%Y%m%d-%H%M%S).tar.gz"

sqlite3 "$DATA/cloudreve.db" ".backup '$work/cloudreve.db'"
if [[ $(sqlite3 "$work/cloudreve.db" 'PRAGMA integrity_check;') != ok ]]; then
  echo "$(date "+%F %T") 備份失敗：快照完整性檢查沒過" >&2
  "$APP_DIR/scripts/notify.sh" "🔴 工地隨手記備份失敗（sitelog）：資料庫快照完整性檢查沒過" || true
  exit 1
fi
cp "$DATA/conf.ini" "$work/conf.ini"
files=(cloudreve.db conf.ini)
if [[ -f $APP_DIR/data/form-app/projects.json ]]; then
  cp "$APP_DIR/data/form-app/projects.json" "$work/projects.json"
  files+=(projects.json)
fi
tar -C "$work" -czf "$work/$name" "${files[@]}"

s3() {
  # 用官方 aws-cli image，不在主機安裝；R2 不需要 region，填 auto
  docker run --rm \
    -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY \
    -e AWS_DEFAULT_REGION=auto \
    -e AWS_REQUEST_CHECKSUM_CALCULATION=when_required \
    -e AWS_RESPONSE_CHECKSUM_VALIDATION=when_required \
    -v "$work:/work:ro" \
    "$AWS_CLI_IMAGE" --endpoint-url "$BACKUP_ENDPOINT" s3 "$@"
}

s3 cp "/work/$name" "s3://$BACKUP_BUCKET/backups/$name" --only-show-errors

# 保留最近 KEEP 份（檔名含時間，字串排序＝時間排序）
deleted=0
while read -r old; do
  [[ -n $old ]] || continue
  s3 rm "s3://$BACKUP_BUCKET/backups/$old" --only-show-errors
  deleted=$((deleted + 1))
done < <(s3 ls "s3://$BACKUP_BUCKET/backups/" \
           | awk '{print $4}' \
           | grep -E '^cloudreve-[0-9]{8}-[0-9]{6}\.tar\.gz$' \
           | sort -r | tail -n +$((KEEP + 1)))

echo "$(date "+%F %T") 備份完成 ${name}（$(du -h "$work/$name" | cut -f1)），刪除舊備份 $deleted 份"
