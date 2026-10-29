#!/usr/bin/env bash
# 新主機初始化（AWS Lightsail，Ubuntu 24.04 LTS）。開好機器後 SSH 進去執行一次：
#   sudo bash scripts/bootstrap_server.sh
# 做的事：時區、系統更新、Docker Engine＋compose plugin（官方 apt repository）、2GB swap、
#         自動安全更新、SSH 只允許金鑰登入、備份需要的 sqlite3 與 /etc/sitelog。
# 可以重複執行。
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "請用 sudo 執行：sudo bash $0" >&2
  exit 1
fi
# shellcheck source=/dev/null
. /etc/os-release
if [[ ${ID:-} != ubuntu || ${VERSION_ID:-} != 24.04 ]]; then
  echo "只支援 Ubuntu 24.04，這台是 ${PRETTY_NAME:-未知}" >&2
  exit 1
fi

DEPLOY_USER=${SUDO_USER:-ubuntu}
export DEBIAN_FRONTEND=noninteractive
step() { printf '\n== %s\n' "$*"; }

step "時區 Asia/Taipei"
timedatectl set-timezone Asia/Taipei

step "系統更新"
apt-get update
apt-get -y upgrade
apt-get install -y ca-certificates curl git sqlite3 unattended-upgrades

step "Docker Engine（https://docs.docker.com/engine/install/ubuntu/）"
for pkg in docker.io docker-compose docker-compose-v2 docker-doc podman-docker containerd runc; do
  if dpkg -s "$pkg" >/dev/null 2>&1; then apt-get remove -y "$pkg"; fi
done
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
# 容器 log 輪替，避免把 40GB 硬碟塞滿
cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
systemctl enable docker
systemctl restart docker
usermod -aG docker "$DEPLOY_USER"

step "2GB swap"
if ! swapon --show=NAME --noheadings | grep -qx /swapfile; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
fi
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
echo 'vm.swappiness=10' > /etc/sysctl.d/99-sitelog.conf
sysctl --system >/dev/null

step "自動安全更新（unattended-upgrades）"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
systemctl enable --now unattended-upgrades

step "SSH 只允許金鑰登入"
AUTH_KEYS=$(getent passwd "$DEPLOY_USER" | cut -d: -f6)/.ssh/authorized_keys
if [[ ! -s $AUTH_KEYS ]]; then
  echo "找不到 ${AUTH_KEYS}，先跳過 SSH 設定，免得把自己鎖在外面。放好公鑰後再執行一次。" >&2
else
  # sshd 對同一個設定採用「第一個讀到的值」，所以檔名用 00- 排在 Lightsail 預設的 60-cloudimg-settings.conf 前面
  cat > /etc/ssh/sshd_config.d/00-sitelog.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
EOF
  # Ubuntu 24.04 的 ssh 走 socket activation：sshd 沒常駐時 /run/sshd 不存在，sshd -t 會失敗
  install -d -m 0755 /run/sshd
  sshd -t
  # socket activation 每個連線都重新讀設定；只有 ssh.service 常駐時才需要 reload
  if systemctl is-active --quiet ssh.service; then systemctl reload ssh.service; fi
  echo "目前生效的設定："
  sshd -T | grep -E '^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin|pubkeyauthentication) '
fi

step "備份設定資料夾 /etc/sitelog（只有 root 能讀）"
install -d -m 700 /etc/sitelog

step "完成"
cat <<EOF
接下來（README「部署到 Lightsail」第 4 步起）：
  1. 登出再登入，讓 $DEPLOY_USER 加入 docker 群組生效
  2. 把專案放到 /srv/sitelog、建立 .env，執行 scripts/deploy.sh
  3. 建立 /etc/sitelog/backup.env 並安裝備份排程
EOF
