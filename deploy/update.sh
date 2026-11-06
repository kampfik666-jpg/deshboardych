# Обновление проекта на сервере: загрузи архив по SSH и запусти
cd /opt/deshboardych
systemctl stop deshboardych
tar -xzf /tmp/deshboardych.tar.gz --overwrite --exclude='.venv' --exclude='bin'
chown -R deshboardych:deshboardych /opt/deshboardych
sudo -u deshboardych bash -c 'cd /opt/deshboardych && .venv/bin/pip install -r requirements.txt -q'
chmod 600 /opt/deshboardych/.env
chown deshboardych:deshboardych /opt/deshboardych/.env
systemctl start deshboardych
echo "Обновление завершено: systemctl status deshboardych --no-pager"
