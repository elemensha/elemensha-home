#!/usr/bin/env bash
# ============================================================================
#  elemensha-home 서버 설치 — 기존 봇과 같은 VM에 두 번째 서비스로 올린다.
#
#  전제
#    - 이미 elemensha-claude-bot 이 8090 에서 돌고 있다
#    - Caddy 가 elemensha-claude.duckdns.org 를 8090 으로 넘기고 있다
#
#  이 스크립트는 그 위에 /home/* 경로를 얹어 8091 로 보낸다.
#  **봇 서비스는 건드리지 않는다.** Caddy 설정만 합쳐서 다시 쓰며,
#  쓰기 전에 백업하고 validate 를 통과하지 못하면 되돌린다.
#
#  사용법: sudo APP_PORT=8091 DOMAIN=elemensha-claude.duckdns.org bash oracle-setup.sh
# ============================================================================
set -euo pipefail

APP_NAME="${APP_NAME:-elemensha-home}"
APP_PORT="${APP_PORT:-8091}"
APP_MEM="${APP_MEM:-280M}"
APP_DIR="/opt/${APP_NAME}"
REPO_DIR="${APP_DIR}/server"
VENV="${APP_DIR}/venv"
DOMAIN="${DOMAIN:-}"
PATH_PREFIX="${PATH_PREFIX:-/home}"

# 같은 도메인을 공유하는 기존 봇
BOT_NAME="${BOT_NAME:-elemensha-claude-bot}"
BOT_PORT="${BOT_PORT:-8090}"
CADDY_SITE="/etc/caddy/${BOT_NAME}.caddy"

log()  { echo -e "\n\033[1;32m==>\033[0m $*"; }
warn() { echo -e "\033[1;33m !\033[0m $*"; }
die()  { echo -e "\n\033[1;31m!!\033[0m $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "sudo 로 실행하세요."
[[ -f "${REPO_DIR}/requirements.txt" ]] || die "${REPO_DIR} 에 서버 코드가 없습니다."

log "1/7  메모리 여유 확인"
AVAIL=$(free -m | awk '/Mem:/{print $7}')
echo "  가용 ${AVAIL}MB / 스왑 $(free -m | awk '/Swap:/{print $3"MB 사용 / "$2"MB"}')"
if (( AVAIL < 150 )); then
  # 여기서 멈추지 않고 진행하면 pip 설치 도중 OOM 이 난다. 실제로 한 번 겪었다.
  die "가용 메모리가 ${AVAIL}MB 뿐입니다. 불필요한 데몬을 먼저 정리하세요.
  예: sudo systemctl disable --now fwupd   # 클라우드 VM 에는 갱신할 펌웨어가 없다"
fi

log "2/7  전용 계정과 디렉터리"
id -u "${APP_NAME}" &>/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin "${APP_NAME}"
mkdir -p "${APP_DIR}/data"
chown -R "${APP_NAME}:${APP_NAME}" "${APP_DIR}"

log "3/7  파이썬 가상환경"
command -v python3 >/dev/null || die "python3 가 없습니다."
if [[ ! -x "${VENV}/bin/python" ]]; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv >/dev/null 2>&1 || true
  python3 -m venv "${VENV}"
fi
# --no-cache-dir: 캐시를 남기면 1GB VM 의 디스크·메모리를 함께 갉아먹는다
"${VENV}/bin/pip" install -q --no-cache-dir --upgrade pip
"${VENV}/bin/pip" install -q --no-cache-dir -r "${REPO_DIR}/requirements.txt"
chown -R "${APP_NAME}:${APP_NAME}" "${VENV}"

log "4/7  .env"
if [[ ! -f "${APP_DIR}/.env" ]]; then
  if [[ -f "${REPO_DIR}/.env.deploy" ]]; then
    mv "${REPO_DIR}/.env.deploy" "${APP_DIR}/.env"
    echo "  업로드된 .env 를 설치했습니다"
  else
    cp "${REPO_DIR}/.env.example" "${APP_DIR}/.env"
    warn "빈 .env 를 만들었습니다. 서비스키를 채워야 물건이 수집됩니다."
  fi
  # 토큰이 비어 있으면 URL 을 아는 누구나 소득·자산 정보를 읽는다.
  if ! grep -q '^HOME_API_TOKEN=.\+' "${APP_DIR}/.env"; then
    TOKEN=$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | head -c 32)
    sed -i "s|^HOME_API_TOKEN=.*|HOME_API_TOKEN=${TOKEN}|" "${APP_DIR}/.env"
    echo "  API 토큰을 자동 생성했습니다"
  fi
else
  # 재배포: 기존 설정과 DB 는 보존한다
  rm -f "${REPO_DIR}/.env.deploy"
  echo "  기존 .env 를 유지합니다"
fi
# systemd 하드닝(ProtectSystem=strict)이 걸려 있어 쓰기가 허용된 경로는
# ${APP_DIR}/data 뿐이다. 기본값은 server/data 라서 그대로 두면 기동에 실패한다.
if grep -q '^HOME_DATA_DIR=' "${APP_DIR}/.env"; then
  sed -i "s|^HOME_DATA_DIR=.*|HOME_DATA_DIR=${APP_DIR}/data|" "${APP_DIR}/.env"
else
  printf '
# 데이터 경로. systemd 가 쓰기를 허용하는 유일한 위치다.
HOME_DATA_DIR=%s/data
'     "${APP_DIR}" >> "${APP_DIR}/.env"
fi
chown "${APP_NAME}:${APP_NAME}" "${APP_DIR}/.env"
chmod 600 "${APP_DIR}/.env"

log "5/7  systemd 서비스"
sed -e "s|@APP_NAME@|${APP_NAME}|g" \
    -e "s|@APP_DIR@|${APP_DIR}|g" \
    -e "s|@APP_PORT@|${APP_PORT}|g" \
    -e "s|@APP_MEM@|${APP_MEM}|g" \
    "${REPO_DIR}/deploy/elemensha-home.service.template" > "/etc/systemd/system/${APP_NAME}.service"
systemctl daemon-reload
systemctl enable --quiet "${APP_NAME}"
systemctl restart "${APP_NAME}"

log "6/7  Caddy 경로 추가 (${PATH_PREFIX}/* -> ${APP_PORT})"
if [[ -z "${DOMAIN}" ]]; then
  warn "DOMAIN 이 비어 Caddy 설정을 건너뜁니다."
else
  [[ -f "${CADDY_SITE}" ]] || die "${CADDY_SITE} 가 없습니다. 봇이 먼저 설치돼 있어야 합니다."
  BACKUP="${CADDY_SITE}.bak.$(date +%Y%m%d%H%M%S)"
  cp "${CADDY_SITE}" "${BACKUP}"

  cat > "${CADDY_SITE}" <<CADDY
# elemensha — 한 도메인에 두 서비스를 얹는다.
#   ${PATH_PREFIX}/*  -> ${APP_NAME} (${APP_PORT})   부동산 알림
#   그 외             -> ${BOT_NAME} (${BOT_PORT})   트레이딩 봇
#
# handle_path 는 매칭된 접두사를 떼고 넘긴다. 앱의 서버 주소를
#   https://${DOMAIN}${PATH_PREFIX}
# 로 넣으면 /api/health 가 그대로 백엔드에 도착한다.
${DOMAIN} {
	encode zstd gzip

	handle_path ${PATH_PREFIX}/* {
		reverse_proxy 127.0.0.1:${APP_PORT} {
			header_up X-Real-IP {remote_host}
		}
	}

	handle {
		reverse_proxy 127.0.0.1:${BOT_PORT} {
			header_up X-Real-IP {remote_host}
		}
	}
}
CADDY

  if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
    systemctl reload caddy
    echo "  Caddy 반영 완료 (백업: ${BACKUP})"
  else
    cp "${BACKUP}" "${CADDY_SITE}"
    die "Caddy 설정 검증 실패. 원본으로 되돌렸습니다. 봇은 그대로 동작합니다."
  fi
fi

log "7/7  기동 확인"
sleep 3
if systemctl is-active --quiet "${APP_NAME}"; then
  echo "  서비스 active"
  curl -fsS "http://127.0.0.1:${APP_PORT}/api/health" | head -c 400 || warn "헬스체크 응답 없음"
  echo
else
  journalctl -u "${APP_NAME}" -n 30 --no-pager
  die "서비스가 기동하지 못했습니다."
fi

cat <<DONE

────────────────────────────────────────────────────────
 설치 완료: ${APP_NAME}  (포트 ${APP_PORT}, 한도 ${APP_MEM})

 앱에 넣을 서버 주소 : https://${DOMAIN}${PATH_PREFIX}
 API 토큰            : sudo grep HOME_API_TOKEN ${APP_DIR}/.env
 로그                : sudo journalctl -u ${APP_NAME} -f
────────────────────────────────────────────────────────
DONE
