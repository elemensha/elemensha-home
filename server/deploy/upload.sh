#!/usr/bin/env bash
# ============================================================================
#  로컬 -> Oracle VM 배포 (Git Bash 에서 실행)
#
#     SSH_KEY=/c/Users/eleme/dev/keys/elemensha-claude-bot.key \
#     bash server/deploy/upload.sh 150.230.218.11
#
#  기존 봇(elemensha-claude-bot)은 건드리지 않는다. 이 스크립트는
#  같은 VM 에 두 번째 서비스를 올리고 Caddy 에 /home 경로만 추가한다.
#  재실행하면 코드만 갱신되고 .env 와 SQLite DB 는 보존된다.
# ============================================================================
set -euo pipefail

VM_IP="${1:-150.230.218.11}"
APP_NAME="${APP_NAME:-elemensha-home}"
APP_PORT="${APP_PORT:-8091}"
DOMAIN="${DOMAIN:-elemensha-claude.duckdns.org}"
PATH_PREFIX="${PATH_PREFIX:-/home}"
SSH_USER="${SSH_USER:-ubuntu}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$(dirname "$SCRIPT_DIR")"
KEY="${SSH_KEY:-/c/Users/eleme/dev/keys/elemensha-claude-bot.key}"

log() { echo -e "\n\033[1;32m==>\033[0m $*"; }
die() { echo -e "\n\033[1;31m!!\033[0m $*" >&2; exit 1; }

[[ -f "$KEY" ]] || die "SSH 키가 없습니다: $KEY"
chmod 600 "$KEY" 2>/dev/null || true

log "1/4  연결 확인"
ssh -i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 \
    "${SSH_USER}@${VM_IP}" \
    'echo "  $(hostname) / 가용 $(free -m | awk "/Mem:/{print \$7}")MB"' \
  || die "SSH 접속 실패."

log "2/4  코드 업로드"
TMP_TAR=$(mktemp -t elemensha-home-XXXX.tar.gz)
# .env 는 이름을 바꿔 함께 보낸다. 서버에 .env 가 없을 때만 설치되고,
# 이미 있으면 설치 스크립트가 버린다(기존 키를 덮어쓰지 않기 위해).
if [[ -f "${SERVER_DIR}/.env" ]]; then
  cp "${SERVER_DIR}/.env" "${SERVER_DIR}/.env.deploy"
fi
tar --exclude='__pycache__' --exclude='data' --exclude='.env' --exclude='*.pyc' \
    --exclude='.venv' \
    -czf "$TMP_TAR" -C "$(dirname "$SERVER_DIR")" server
rm -f "${SERVER_DIR}/.env.deploy"
scp -i "$KEY" -q "$TMP_TAR" "${SSH_USER}@${VM_IP}:/tmp/elemensha-home.tar.gz"
rm -f "$TMP_TAR"
echo "  업로드 완료"

log "3/4  설치 (${APP_NAME}, 포트 ${APP_PORT})"
ssh -i "$KEY" "${SSH_USER}@${VM_IP}" bash -s <<REMOTE
set -euo pipefail
sudo mkdir -p /opt/${APP_NAME}
sudo tar -xzf /tmp/elemensha-home.tar.gz -C /opt/${APP_NAME}
# Windows 에서 온 CRLF 는 bash 가 스크립트를 못 읽게 만든다. 실행 전에 제거한다.
sudo find /opt/${APP_NAME}/server -type f \\
     \\( -name '*.sh' -o -name '*.template' -o -name 'requirements.txt' -o -name '.env.deploy' \\) \\
     -exec sed -i 's/\\x0d\$//' {} +
rm -f /tmp/elemensha-home.tar.gz
sudo chmod +x /opt/${APP_NAME}/server/deploy/oracle-setup.sh
sudo APP_NAME=${APP_NAME} APP_PORT=${APP_PORT} DOMAIN='${DOMAIN}' \\
     PATH_PREFIX='${PATH_PREFIX}' \\
     bash /opt/${APP_NAME}/server/deploy/oracle-setup.sh
REMOTE

log "4/4  앱 설정값"
ssh -i "$KEY" "${SSH_USER}@${VM_IP}" \
    "sudo grep HOME_API_TOKEN /opt/${APP_NAME}/.env"

cat <<DONE

────────────────────────────────────────────────────────
 배포 완료

 앱 서버 주소 : https://${DOMAIN}${PATH_PREFIX}
 로그         : ssh -i "\$SSH_KEY" ${SSH_USER}@${VM_IP} 'sudo journalctl -u ${APP_NAME} -f'
 재배포       : 이 스크립트를 다시 실행 (설정·DB 보존)
────────────────────────────────────────────────────────
DONE
