#!/bin/bash
# Run this once as a user with sudo to deploy the LSBBW site.
set -e

SITE=/var/www/lsbbw
SRC=/home/tim2/lsbbw

echo "==> Copying files to $SITE"
sudo cp -r "$SRC" "$SITE"
sudo chown -R www-data:www-data "$SITE"
sudo chmod -R 755 "$SITE"
sudo chmod -R 775 "$SITE/app/static/uploads" "$SITE/app/static/thumbnails"

echo "==> Creating Python venv"
sudo -u www-data python3 -m venv "$SITE/venv"
sudo -u www-data "$SITE/venv/bin/pip" install -q -r "$SITE/requirements.txt"

echo "==> Setting admin password"
read -rsp "Admin password (leave blank to keep 'changeme123'): " PASS
echo
if [ -n "$PASS" ]; then
    sudo sed -i "s|changeme123|$PASS|g" "$SITE/lsbbw.service"
fi

echo "==> Installing systemd service"
sudo cp "$SITE/lsbbw.service" /etc/systemd/system/lsbbw.service
sudo systemctl daemon-reload
sudo systemctl enable --now lsbbw.service

echo "==> Installing Apache vhost"
sudo cp "$SITE/lsbbw.conf" /etc/apache2/sites-available/lsbbw.conf
sudo a2enmod proxy proxy_http headers 2>/dev/null || true
sudo a2ensite lsbbw.conf
sudo apachectl configtest && sudo systemctl reload apache2

echo ""
echo "Done! LSBBW is running."
echo "  Site:  http://ilovelsbbw.com"
echo "  Admin: http://ilovelsbbw.com/admin/login"
echo ""
echo "Edit /etc/systemd/system/lsbbw.service to change the admin password,"
echo "then: sudo systemctl restart lsbbw"
