#!/bin/bash
# ДЭШБОРДЫЧЬ — установка на Ubuntu 24.04 (/opt/deshboardych).
# Запускать от root: bash setup.sh
set -e

echo "=== 1. Системные пакеты ==="
apt update
apt install -y python3 python3-venv python3-pip ffmpeg rsync curl ca-certificates ufw

echo "=== 2. Пользователь и директории ==="
useradd -m -s /bin/bash deshboardych 2>/dev/null || true
mkdir -p /opt/deshboardych
chown -R deshboardych:deshboardych /opt/deshboardych

echo "=== 3. Файрвол: только SSH ==="
ufw allow OpenSSH
ufw --force enable

echo "=== 4. Python-окружение ==="
sudo -u deshboardych bash -c 'cd /opt/deshboardych && python3 -m venv .venv && .venv/bin/pip install --upgrade pip -q && .venv/bin/pip install -r requirements.txt -q'

echo "=== 5. Права на .env ==="
chmod 600 /opt/deshboardych/.env
chown deshboardych:deshboardych /opt/deshboardych/.env

echo "=== 6. systemd-сервис ==="
cat > /etc/systemd/system/deshboardych.service <<'EOF'
[Unit]
Description=Deshboardych (ДЭШБОРДЫЧЬ) Personal Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=deshboardych
WorkingDirectory=/opt/deshboardych
ExecStart=/opt/deshboardych/.venv/bin/python /opt/deshboardych/run.py
Restart=always
RestartSec=10
Environment=PYTHONIOENCODING=utf-8
Environment=TZ=Asia/Yekaterinburg

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable deshboardych
systemctl restart deshboardych

echo "=== 7. Бэкап базы данных (cron, ежедневно в 04:00) ==="
mkdir -p /opt/deshboardych/backups
chown deshboardych:deshboardych /opt/deshboardych/backups
cat > /opt/deshboardych/deploy/backup.sh <<'EOF'
#!/bin/bash
# Ежедневный бэкап базы (7 дней хранения)
set -e
SRC=/opt/deshboardych/data/lifehub.sqlite3
DST=/opt/deshboardych/backups/lifehub-$(date +%F).sqlite3
cp "$SRC" "$DST"
find /opt/deshboardych/backups -name "lifehub-*.sqlite3" -mtime +7 -delete
EOF
chmod +x /opt/deshboardych/deploy/backup.sh
(crontab -u deshboardych -l 2>/dev/null; echo "0 4 * * * /opt/deshboardych/deploy/backup.sh") | crontab -u deshboardych -

echo
echo "=== ГОТОВО ==="
echo "Статус:  systemctl status deshboardych --no-pager"
echo "Логи:    journalctl -u deshboardych -f"
