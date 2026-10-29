#!/usr/bin/env bash
# 在主機上更新並啟動（第一次部署和之後每次更新都用這個）：
#   cd /srv/sitelog && scripts/deploy.sh
# .env 的 COMPOSE_FILE 會自動疊上 docker-compose.prod.yml。
set -euo pipefail
# 整份包在 { } 裡：bash 會先讀完再執行，下面 git pull 改到這個檔案也不會執行到一半的新內容
{
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "找不到 .env：cp .env.example .env 後照 README 填好" >&2
  exit 1
fi
if [[ $(stat -c %a .env) != 600 ]]; then
  chmod 600 .env
  echo "已把 .env 權限改成 600"
fi
if ! grep -q '^COMPOSE_FILE=.*docker-compose.prod.yml' .env; then
  echo ".env 沒有設定 COMPOSE_FILE（會用本機開發設定，不會啟動 Cloudflare Tunnel）" >&2
  exit 1
fi

git pull --ff-only
# form-app 以 uid 10001 執行，要能寫共用工程清單 data/form-app/projects.json
if [[ $(stat -c %u data/form-app 2>/dev/null) != 10001 ]]; then
  sudo mkdir -p data/form-app && sudo chown 10001:10001 data/form-app && sudo chmod 0750 data/form-app
fi
docker compose build --pull form-app
docker compose up -d --remove-orphans
docker image prune -f >/dev/null
sleep 10
docker compose ps
exit
}
