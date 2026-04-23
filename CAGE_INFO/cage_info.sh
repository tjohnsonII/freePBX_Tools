#!/bin/sh
set -eu

HOST="192.168.50.1"
USER="tjohnson"

ssh -oHostKeyAlgorithms=+ssh-dss -oPubkeyAcceptedAlgorithms=+ssh-dss "${USER}@${HOST}" 'sh -s' <<'EOF'
set -eu

OS="$(uname -s 2>/dev/null || echo unknown)"
echo "===== BASIC ====="
echo "Host: $(hostname)"
echo "OS:   $OS"
echo "Uptime:"
uptime || true
echo

echo "===== USERS ====="
cut -d: -f1 /etc/passwd | sort
echo

echo "===== GROUPS ====="
cut -d: -f1 /etc/group | sort
echo

echo "===== SHELLS ====="
[ -f /etc/shells ] && cat /etc/shells || echo "/etc/shells not found"
echo
echo "Current shell (from passwd):"
id -un | xargs -I{} sh -c "grep '^{}:' /etc/passwd | cut -d: -f7" || true
echo

echo "===== LISTENING PORTS ====="
if command -v sockstat >/dev/null 2>&1; then
  sockstat -4l || true
  sockstat -6l || true
else
  netstat -an | egrep 'LISTEN' || true
fi
echo

echo "===== ROOT PROCESSES (sample) ====="
ps aux | awk '$1=="root"{print}' | head -n 40 || true
echo

echo "===== CRON ====="
if [ -f /etc/crontab ]; then
  egrep -n 'root' /etc/crontab || true
else
  echo "/etc/crontab not found"
fi
echo

echo "===== SUID / SGID (sample) ====="
find / -type f \( -perm -4000 -o -perm -2000 \) -exec ls -l {} \; 2>/dev/null | head -n 100 || true
echo

echo "===== .rhosts (IMPORTANT) ====="
find /usr/home /root -name .rhosts -exec ls -l {} \; 2>/dev/null || true
echo

echo "===== BACKUP-LIKE FILES (sample) ====="
find /etc /var /usr/local /root /tmp /usr/home -type f \( \
  -iname '*backup*' -o -iname '*.back' -o -iname '*.bck' -o -iname '*.bk' -o -iname '*.bak' \
\) 2>/dev/null | head -n 200 || true
echo

echo "===== DB FILES (sample) ====="
find / -type f \( -iname '*.db' -o -iname '*.sqlite' -o -iname '*.sqlite3' \) 2>/dev/null | head -n 200 || true
echo

echo "===== LANGUAGES ====="
for c in python python3 perl ruby lua; do
  if command -v "$c" >/dev/null 2>&1; then
    echo "$c: $(command -v "$c")"
  else
    echo "$c: not found"
  fi
done
EOF

