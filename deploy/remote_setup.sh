#!/usr/bin/env bash
set -euo pipefail

APP_NAME="spanish-study-telegram-bot"
APP_DIR="${APP_DIR:-$HOME/apps/$APP_NAME}"
VENV_DIR="${VENV_DIR:-$APP_DIR/venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SERVICE_NAME="${SERVICE_NAME:-spanish-study-bot}"
SYSTEMD_USER_DIR="${SYSTEMD_USER_DIR:-$HOME/.config/systemd/user}"
SERVICE_FILE="${SERVICE_FILE:-$SYSTEMD_USER_DIR/${SERVICE_NAME}.service}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"

echo "==> Preparing application directory at ${APP_DIR}"
mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/data"

# Ensure we are running from the repository root within the app directory.
if [[ -f "./deploy/remote_setup.sh" ]]; then
  REPO_ROOT="$(pwd)"
else
  REPO_ROOT="$APP_DIR"
  cd "$APP_DIR"
fi

echo "==> Ensuring virtual environment at ${VENV_DIR}"
if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "==> Installing Python dependencies"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$REPO_ROOT/requirements.txt"

echo "==> Writing systemd user service to ${SERVICE_FILE}"
mkdir -p "$SYSTEMD_USER_DIR"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Spanish Study Telegram Bot
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/python ${APP_DIR}/main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=spanish-study-bot

[Install]
WantedBy=default.target
EOF

if [[ ! -f "$ENV_FILE" ]]; then
  echo "WARNING: No environment file found at ${ENV_FILE}. The bot will fail to start until it exists." >&2
fi

echo "==> Killing any manual bot processes"
# Kill any manually started python processes running main.py
pkill -f "python.*main.py" || true

echo "==> Reloading systemd user daemon"
systemctl --user daemon-reload

echo "==> Enabling and restarting ${SERVICE_NAME} service"
systemctl --user enable "${SERVICE_NAME}.service"
systemctl --user restart "${SERVICE_NAME}.service"

# Wait a moment for service to start
sleep 2

echo "==> Checking service status"
systemctl --user status "${SERVICE_NAME}.service" --no-pager || true

echo ""
echo "==> Deployment complete."
echo "Service status: $(systemctl --user is-active ${SERVICE_NAME}.service)"
echo "View logs: journalctl --user -u ${SERVICE_NAME}.service -f"
echo ""
echo "Hint: Ensure 'loginctl enable-linger ${USER}' is set so the user service keeps running after logout."
