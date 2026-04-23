#!/bin/bash
# Install and enable freepbx-tools systemd units.
# Run as root: sudo bash scripts/install_systemd.sh
set -euo pipefail

REPO=/var/www/freePBX_Tools
SYSTEMD=/etc/systemd/system

echo "Installing systemd units from $REPO/systemd/ ..."

cp "$REPO/systemd/freepbx-tools.service"            "$SYSTEMD/"
cp "$REPO/systemd/freepbx-tools-watchdog.service"   "$SYSTEMD/"
cp "$REPO/systemd/freepbx-tools-watchdog.timer"     "$SYSTEMD/"
cp "$REPO/systemd/freepbx-nightly-scrape.service"   "$SYSTEMD/"
cp "$REPO/systemd/freepbx-nightly-scrape.timer"     "$SYSTEMD/"

chmod 644 "$SYSTEMD"/freepbx-*.{service,timer}

systemctl daemon-reload

systemctl enable freepbx-tools.service
systemctl enable freepbx-tools-watchdog.timer
systemctl enable freepbx-nightly-scrape.timer

echo ""
echo "Units installed and enabled. To activate now:"
echo "  sudo systemctl start freepbx-tools.service"
echo "  sudo systemctl start freepbx-tools-watchdog.timer"
echo "  sudo systemctl start freepbx-nightly-scrape.timer"
echo ""
echo "To check status:"
echo "  systemctl status freepbx-tools.service"
echo "  systemctl list-timers --all | grep freepbx"
echo ""
echo "Logs:"
echo "  journalctl -u freepbx-tools -f"
echo "  journalctl -u freepbx-watchdog -f"
echo "  journalctl -u freepbx-nightly-scrape -f"
