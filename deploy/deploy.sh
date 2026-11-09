#!/usr/bin/env bash
# LunwenToCode 一键部署脚本（Ubuntu / Debian）
#
# 用法：
#   sudo bash deploy/deploy.sh [选项]
#
#   --domain example.com     绑定域名（配 Nginx + HTTPS）
#   --no-nginx               只起服务，不配 Nginx
#   --docker                 用 Docker 部署（默认用 systemd）
#   --token 你的令牌         直接写入 SITE_TOKEN
#
# 示例：
#   sudo bash deploy/deploy.sh --domain thesis.example.com --token abc123xyz

set -euo pipefail

APP_DIR="/opt/lunwentocode"
VENV="/opt/venv"
SERVICE_USER="lunwen"
PORT="8000"

DOMAIN=""
USE_DOCKER=0
USE_NGINX=1
SITE_TOKEN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)    DOMAIN="$2"; shift 2 ;;
    --token)     SITE_TOKEN="$2"; shift 2 ;;
    --no-nginx)  USE_NGINX=0; shift ;;
    --docker)    USE_DOCKER=1; shift ;;
    --port)      PORT="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

log()  { printf "\033[1;33m==>\033[0m %s\n" "$*"; }
ok()   { printf "\033[1;32m  ✓\033[0m %s\n" "$*"; }
warn() { printf "\033[1;31m  !\033[0m %s\n" "$*"; }

[[ $EUID -eq 0 ]] || { echo "请用 root 运行：sudo bash $0"; exit 1; }

# ---------------------------------------------------------------- Docker 模式
if [[ $USE_DOCKER -eq 1 ]]; then
  log "安装 Docker"
  apt-get update -qq
  apt-get install -y -qq docker.io docker-compose-plugin >/dev/null 2>&1 || \
    apt-get install -y -qq docker.io docker-compose >/dev/null
  systemctl enable --now docker

  log "准备目录 $APP_DIR"
  mkdir -p "$APP_DIR"
  # 假设代码已在上传/clone到当前目录
  SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  cp -r "$SRC_DIR"/. "$APP_DIR"/ 2>/dev/null || true
  cd "$APP_DIR"

  if [[ ! -f .env ]]; then
    log "生成 .env"
    cp .env.web.example .env
    if [[ -z "$SITE_TOKEN" ]]; then
      SITE_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    fi
    sed -i "s|^SITE_TOKEN=.*|SITE_TOKEN=${SITE_TOKEN}|" .env
    ok "已生成访问令牌：$SITE_TOKEN"
  fi

  log "构建镜像（首次约 3-5 分钟）"
  docker compose up -d --build

  sleep 5
  log "健康检查"
  curl -fsS "http://127.0.0.1:${PORT}/api/health" && echo
  ok "Docker 部署完成"
  echo
  echo "  访问: http://<服务器IP>:${PORT}"
  echo "  日志: docker compose logs -f web"
  exit 0
fi

# ---------------------------------------------------------------- systemd 模式
log "安装系统依赖"
apt-get update -qq
apt-get install -y -qq python3.11 python3.11-venv nginx git \
                   fonts-wqy-zenhei fonts-noto-cjk curl >/dev/null
systemctl enable --now nginx

log "创建服务用户与目录"
id -u "$SERVICE_USER" >/dev/null 2>&1 || \
  useradd -r -m -d "$APP_DIR" -s /bin/bash "$SERVICE_USER"
mkdir -p "$APP_DIR" /var/log/lunwentocode
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR" /var/log/lunwentocode

log "同步代码到 $APP_DIR"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$SRC_DIR" != "$APP_DIR" ]]; then
  rsync -a --exclude '.git' --exclude 'web_output' --exclude 'web_uploads' \
        "$SRC_DIR"/ "$APP_DIR"/ 2>/dev/null || cp -r "$SRC_DIR"/. "$APP_DIR"/
fi

log "创建虚拟环境 $VENV"
if [[ ! -x "$VENV/bin/python" ]]; then
  sudo -u "$SERVICE_USER" python3.11 -m venv "$VENV"
fi
sudo -u "$SERVICE_USER" "$VENV/bin/pip" install -U pip wheel -q
sudo -u "$SERVICE_USER" "$VENV/bin/pip" install -q -r "$APP_DIR/requirements.txt" \
                                                 -r "$APP_DIR/requirements-web.txt"
sudo -u "$SERVICE_USER" "$VENV/bin/pip" install -q jupyterlab ipykernel
sudo -u "$SERVICE_USER" "$VENV/bin/python" -m ipykernel install --sys-prefix --name python3
ok "依赖安装完成"

log "配置 .env"
cd "$APP_DIR"
if [[ ! -f .env ]]; then
  cp .env.web.example .env
  if [[ -z "$SITE_TOKEN" ]]; then
    SITE_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  fi
  sed -i "s|^SITE_TOKEN=.*|SITE_TOKEN=${SITE_TOKEN}|" .env
  sed -i "s|^OUTPUT_ROOT=.*|OUTPUT_ROOT=${APP_DIR}/web_output|" .env
  sed -i "s|^UPLOAD_ROOT=.*|UPLOAD_ROOT=${APP_DIR}/web_uploads|" .env
  ok "访问令牌：$SITE_TOKEN"
else
  ok "沿用已有 .env"
fi
mkdir -p "$APP_DIR/web_output" "$APP_DIR/web_uploads"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

log "安装 systemd 服务"
cp "$APP_DIR/deploy/lunwentocode-web.service" /etc/systemd/system/
sed -i "s|--port 8000|--port ${PORT}|" /etc/systemd/system/lunwentocode-web.service
sed -i "s|Environment=\"PATH=/opt/venv/bin|Environment=\"PATH=${VENV}/bin|" /etc/systemd/system/lunwentocode-web.service
sed -i "s|/opt/venv/bin/uvicorn|${VENV}/bin/uvicorn|" /etc/systemd/system/lunwentocode-web.service
systemctl daemon-reload
systemctl enable --now lunwentocode-web
sleep 4
systemctl is-active --quiet lunwentocode-web && ok "服务已启动" || {
  warn "服务启动失败，日志："; journalctl -u lunwentocode-web -n 30; exit 1;
}

# ---------------------------------------------------------------- Nginx
if [[ $USE_NGINX -eq 1 ]]; then
  if [[ -n "$DOMAIN" ]]; then
    log "配置 Nginx + HTTPS：$DOMAIN"
    sed "s|lunwentocode.example.com|$DOMAIN|g" \
        "$APP_DIR/deploy/nginx.conf" > /etc/nginx/sites-available/lunwentocode
    ln -sf /etc/nginx/sites-available/lunwentocode /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl reload nginx
    ok "Nginx 已配置"

    log "申请证书"
    apt-get install -y -qq certbot python3-certbot-nginx >/dev/null
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
            --register-unsafely-without-email --redirect || \
      warn "证书申请失败，请检查域名解析是否已生效后手动执行 certbot"
  else
    log "未指定 --domain，跳过 Nginx 配置"
    warn "服务仅监听 127.0.0.1:${PORT}，外网无法访问"
  fi
fi

# ---------------------------------------------------------------- 自检
log "健康检查"
HEALTH="$(curl -fsS "http://127.0.0.1:${PORT}/api/health" 2>/dev/null || echo '')"
if [[ -n "$HEALTH" ]]; then
  echo "  $HEALTH"
  ok "部署完成"
else
  warn "健康检查未通过，日志："
  journalctl -u lunwentocode-web -n 30
fi

echo
echo "────────────────────────────────────────────"
if [[ -n "$DOMAIN" ]]; then
  echo "  访问地址: https://${DOMAIN}"
else
  echo "  本机访问: http://127.0.0.1:${PORT}"
  echo "  外网访问需自行配置 Nginx 反代"
fi
echo "  查看日志: journalctl -u lunwentocode-web -f"
echo "  重启服务: systemctl restart lunwentocode-web"
echo "────────────────────────────────────────────"
