#!/bin/bash

# FreePBX Host Profile Auto-Detection Script
# Automatically detects and populates host configuration values

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Output file
OUTPUT_FILE="freepbx_host_profile.conf"

echo -e "${BLUE}=== FreePBX Host Profile Auto-Detection ===${NC}\n"

# Function to detect OS family
detect_os_family() {
    if [ -f /etc/redhat-release ]; then
        local version=$(rpm -q --qf "%{VERSION}" centos-release 2>/dev/null || rpm -q --qf "%{VERSION}" rocky-release 2>/dev/null || rpm -q --qf "%{VERSION}" almalinux-release 2>/dev/null || echo "")
        if [[ $version =~ ^7 ]]; then
            echo "el7"
        elif [[ $version =~ ^8 ]]; then
            echo "el8"
        elif [[ $version =~ ^9 ]]; then
            echo "el9"
        else
            # Try to detect from /etc/redhat-release content
            local release_content=$(cat /etc/redhat-release 2>/dev/null || echo "")
            if [[ $release_content =~ "release 7" ]]; then
                echo "el7"
            elif [[ $release_content =~ "release 8" ]]; then
                echo "el8"
            elif [[ $release_content =~ "release 9" ]]; then
                echo "el9"
            else
                echo "el8"  # default fallback
            fi
        fi
    elif [ -f /etc/debian_version ] || [ -f /etc/lsb-release ]; then
        echo "debian/ubuntu"
    else
        echo "unknown"
    fi
}

# Function to find executable path
find_executable() {
    local cmd=$1
    local default_path=$2
    
    # Check if default path exists and is executable
    if [ -x "$default_path" ]; then
        echo "$default_path"
        return
    fi
    
    # Try which command
    local which_result=$(which "$cmd" 2>/dev/null || echo "")
    if [ -n "$which_result" ] && [ -x "$which_result" ]; then
        echo "$which_result"
        return
    fi
    
    # Try common locations
    local common_paths=("/usr/bin/$cmd" "/usr/sbin/$cmd" "/bin/$cmd" "/sbin/$cmd" "/usr/local/bin/$cmd")
    for path in "${common_paths[@]}"; do
        if [ -x "$path" ]; then
            echo "$path"
            return
        fi
    done
    
    echo "$default_path"  # fallback to default
}

# Function to extract FreePBX database config
extract_freepbx_config() {
    local freepbx_conf=$1
    
    if [ ! -f "$freepbx_conf" ]; then
        echo -e "${RED}Warning: FreePBX config file not found at $freepbx_conf${NC}"
        return
    fi
    
    # Try to extract database info using PHP
    local php_script='<?php
    if (file_exists("'$freepbx_conf'")) {
        include "'$freepbx_conf'";
        if (isset($amp_conf)) {
            echo "AMPDBNAME=" . (isset($amp_conf["AMPDBNAME"]) ? $amp_conf["AMPDBNAME"] : "asterisk") . "\n";
            echo "AMPDBUSER=" . (isset($amp_conf["AMPDBUSER"]) ? $amp_conf["AMPDBUSER"] : "asteriskuser") . "\n";
            echo "AMPDBPASS=" . (isset($amp_conf["AMPDBPASS"]) ? $amp_conf["AMPDBPASS"] : "") . "\n";
        }
    }
    ?>'
    
    if command -v php >/dev/null 2>&1; then
        echo "$php_script" | php 2>/dev/null || true
    fi
}

# Function to find MySQL socket
find_mysql_socket() {
    local common_sockets=(
        "/var/lib/mysql/mysql.sock"
        "/tmp/mysql.sock" 
        "/var/run/mysqld/mysqld.sock"
        "/run/mysql/mysql.sock"
    )
    
    for socket in "${common_sockets[@]}"; do
        if [ -S "$socket" ]; then
            echo "$socket"
            return
        fi
    done
    
    # Try to find from MySQL config
    if command -v mysql >/dev/null 2>&1; then
        local socket_from_mysql=$(mysql -e "SHOW VARIABLES LIKE 'socket';" 2>/dev/null | grep socket | awk '{print $2}' || echo "")
        if [ -n "$socket_from_mysql" ] && [ -S "$socket_from_mysql" ]; then
            echo "$socket_from_mysql"
            return
        fi
    fi
    
    echo "/var/lib/mysql/mysql.sock"  # default fallback
}

# Function to detect SELinux mode
detect_selinux() {
    if command -v getenforce >/dev/null 2>&1; then
        local mode=$(getenforce 2>/dev/null || echo "")
        case "${mode,,}" in
            enforcing) echo "enforcing" ;;
            permissive) echo "permissive" ;;
            disabled) echo "disabled" ;;
            *) echo "disabled" ;;
        esac
    else
        echo "disabled"
    fi
}

# Function to check if user exists
user_exists() {
    id "$1" >/dev/null 2>&1
}

# Start detection
echo "Detecting system configuration..."

# OS Family
echo -n "Detecting OS family... "
OS_FAMILY=$(detect_os_family)
echo -e "${GREEN}$OS_FAMILY${NC}"

# Asterisk user
echo -n "Checking Asterisk user... "
if user_exists "asterisk"; then
    ASTERISK_USER="asterisk"
    echo -e "${GREEN}asterisk${NC}"
elif user_exists "freepbx"; then
    ASTERISK_USER="freepbx"
    echo -e "${YELLOW}freepbx${NC}"
else
    ASTERISK_USER="asterisk"
    echo -e "${RED}not found, defaulting to asterisk${NC}"
fi

# FreePBX config path
echo -n "Checking FreePBX config... "
if [ -f "/etc/freepbx.conf" ]; then
    FREEPBX_CONF="/etc/freepbx.conf"
    echo -e "${GREEN}/etc/freepbx.conf${NC}"
elif [ -f "/etc/asterisk/freepbx.conf" ]; then
    FREEPBX_CONF="/etc/asterisk/freepbx.conf"
    echo -e "${GREEN}/etc/asterisk/freepbx.conf${NC}"
else
    FREEPBX_CONF="/etc/freepbx.conf"
    echo -e "${RED}not found, defaulting to /etc/freepbx.conf${NC}"
fi

# Extract database config
echo "Extracting database configuration..."
DB_CONFIG=$(extract_freepbx_config "$FREEPBX_CONF")
if [ -n "$DB_CONFIG" ]; then
    AMPDBNAME=$(echo "$DB_CONFIG" | grep "AMPDBNAME=" | cut -d= -f2)
    AMPDBUSER=$(echo "$DB_CONFIG" | grep "AMPDBUSER=" | cut -d= -f2)
    AMPDBPASS=$(echo "$DB_CONFIG" | grep "AMPDBPASS=" | cut -d= -f2)
    echo -e "  Database: ${GREEN}${AMPDBNAME:-asterisk}${NC}"
    echo -e "  User: ${GREEN}${AMPDBUSER:-asteriskuser}${NC}"
    echo -e "  Password: ${GREEN}[detected]${NC}"
else
    echo -e "${YELLOW}Using defaults${NC}"
    AMPDBNAME="asterisk"
    AMPDBUSER="asteriskuser"  
    AMPDBPASS=""
fi

# MySQL socket
echo -n "Finding MySQL socket... "
MYSQL_SOCKET=$(find_mysql_socket)
if [ -S "$MYSQL_SOCKET" ]; then
    echo -e "${GREEN}$MYSQL_SOCKET${NC}"
else
    echo -e "${YELLOW}$MYSQL_SOCKET (not verified)${NC}"
fi

# Executables
echo "Locating executables..."
PYTHON3=$(find_executable "python3" "/usr/bin/python3")
echo -e "  Python3: ${GREEN}$PYTHON3${NC}"

DOT_BIN=$(find_executable "dot" "/usr/bin/dot")
if [ -x "$DOT_BIN" ]; then
    echo -e "  Graphviz dot: ${GREEN}$DOT_BIN${NC}"
else
    echo -e "  Graphviz dot: ${RED}$DOT_BIN (not found - install graphviz)${NC}"
fi

ASTERISK_BIN=$(find_executable "asterisk" "/usr/sbin/asterisk")
echo -e "  Asterisk: ${GREEN}$ASTERISK_BIN${NC}"

# fwconsole
echo -n "Finding fwconsole... "
FWCONSOLE_CANDIDATES=(
    "/var/lib/asterisk/bin/fwconsole"
    "/usr/local/sbin/fwconsole"
    "/usr/sbin/fwconsole"
)

FWCONSOLE_BIN=""
for candidate in "${FWCONSOLE_CANDIDATES[@]}"; do
    if [ -x "$candidate" ]; then
        FWCONSOLE_BIN="$candidate"
        break
    fi
done

if [ -z "$FWCONSOLE_BIN" ]; then
    FWCONSOLE_BIN="/var/lib/asterisk/bin/fwconsole"
    echo -e "${RED}not found, defaulting to $FWCONSOLE_BIN${NC}"
else
    echo -e "${GREEN}$FWCONSOLE_BIN${NC}"
fi

# SELinux
echo -n "Checking SELinux... "
SELINUX_MODE=$(detect_selinux)
echo -e "${GREEN}$SELINUX_MODE${NC}"

# Output directories
CALLFLOWS_DIR="/home/123net/callflows"
CALLFLOWS_OWNER="$ASTERISK_USER"

# Generate configuration file
echo
echo -e "${BLUE}Generating configuration file: $OUTPUT_FILE${NC}"

cat > "$OUTPUT_FILE" << EOF
# === 123NET FreePBX Tools — Host Profile ===
# Generated on $(date)

# OS family (choose): el7 | el8 | el9 | debian/ubuntu
OS_FAMILY=$OS_FAMILY

# Asterisk/FreePBX basics
ASTERISK_USER=$ASTERISK_USER               # usually "asterisk"
FREEPBX_CONF=$FREEPBX_CONF       # usually this path

# MariaDB/MySQL access (usually read from freepbx.conf via PHP)
AMPDBNAME=$AMPDBNAME                            # e.g. asterisk
AMPDBUSER=$AMPDBUSER
AMPDBPASS=$AMPDBPASS
MYSQL_SOCKET=$MYSQL_SOCKET                         # e.g. /var/lib/mysql/mysql.sock

# Output folders & ownership
CALLFLOWS_DIR=$CALLFLOWS_DIR  # where dumps/graphs land
CALLFLOWS_OWNER=$CALLFLOWS_OWNER              # chown target (user:group optional)

# Executables (let me know if you've customized paths)
PYTHON3=$PYTHON3
DOT_BIN=$DOT_BIN
ASTERISK_BIN=$ASTERISK_BIN       # optional convenience symlink
FWCONSOLE_BIN=$FWCONSOLE_BIN

# SELinux mode (choose): enforcing | permissive | disabled
SELINUX_MODE=$SELINUX_MODE

# Anything unusual I should know (proxy, no internet, etc.)
NOTES=

EOF

echo -e "${GREEN}Configuration saved to: $OUTPUT_FILE${NC}"
echo
echo -e "${YELLOW}Please review the generated configuration and make any necessary adjustments.${NC}"

# Show warnings if needed
echo
echo -e "${BLUE}=== Verification Notes ===${NC}"

if [ ! -x "$DOT_BIN" ]; then
    echo -e "${RED}⚠ Graphviz not found. Install with:${NC}"
    case $OS_FAMILY in
        el*) echo "  sudo yum install graphviz" ;;
        debian/ubuntu) echo "  sudo apt-get install graphviz" ;;
    esac
    echo
fi

if [ ! -f "$FREEPBX_CONF" ]; then
    echo -e "${RED}⚠ FreePBX config file not found at $FREEPBX_CONF${NC}"
    echo "  Please verify the correct path and update the configuration"
    echo
fi

if [ ! -S "$MYSQL_SOCKET" ]; then
    echo -e "${YELLOW}⚠ MySQL socket not verified at $MYSQL_SOCKET${NC}"
    echo "  Please verify MySQL/MariaDB is running and the socket path is correct"
    echo
fi

echo -e "${GREEN}Detection complete!${NC}"