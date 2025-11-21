#!/bin/bash
#
# FUNCTION MAP LEGEND
# -------------------
# (This script is procedural but organized into major sections)
#
# - Root Check: Warns if running as root and prompts for confirmation.
# - Python Version Check: Ensures Python 3 is available and meets requirements.
# - Directory Setup: Creates install directory if missing.
# - File Copy: Copies analyzer script to install location.
# - Symlink Creation: Creates/updates symlink for easy CLI access.
# - Permissions: Sets executable permissions on installed files.
# - Success Message: Prints completion and usage instructions.
#
#
# Phone Config Analyzer - Installation Script
# Installs and configures the phone config analyzer tool
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/usr/local/123net/freepbx-tools/bin"
TOOL_NAME="phone_config_analyzer.py"
SYMLINK_NAME="phone-config-analyzer"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}"
echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                            ║"
echo "║              Phone Configuration Analyzer - Installation                  ║"
echo "║                                                                            ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ] && [ "$1" != "--force-root" ]; then
    echo -e "${YELLOW}Warning: Running as root. Installation will be system-wide.${NC}"
    echo -e "Press Ctrl+C to cancel, or Enter to continue..."
    read
fi

# Check Python version
echo -e "${CYAN}Checking Python version...${NC}"
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 6 ]); then
    echo -e "${RED}Error: Python 3.6+ required (found $PYTHON_VERSION)${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Python $PYTHON_VERSION found${NC}"
echo ""

# Check if tool exists
if [ ! -f "$SCRIPT_DIR/$TOOL_NAME" ]; then
    echo -e "${RED}Error: $TOOL_NAME not found in $SCRIPT_DIR${NC}"
    exit 1
fi

# Installation choice
echo -e "${CYAN}Installation Options:${NC}"
echo "  1) System-wide installation (requires sudo)"
echo "     Installs to: $INSTALL_DIR"
echo "     Creates symlink: /usr/local/bin/$SYMLINK_NAME"
echo ""
echo "  2) User installation (no sudo required)"
echo "     Installs to: ~/.local/bin/"
echo "     Creates symlink: ~/.local/bin/$SYMLINK_NAME"
echo ""
echo "  3) Current directory only (no installation)"
echo "     Use: python3 $TOOL_NAME"
echo ""

read -p "Select option (1-3): " INSTALL_OPTION

case $INSTALL_OPTION in
    1)
        # System-wide installation
        echo -e "${CYAN}Installing system-wide...${NC}"
        
        # Create directory if needed
        if [ ! -d "$INSTALL_DIR" ]; then
            echo "Creating directory: $INSTALL_DIR"
            sudo mkdir -p "$INSTALL_DIR"
        fi
        
        # Copy tool
        echo "Copying $TOOL_NAME to $INSTALL_DIR/"
        sudo cp "$SCRIPT_DIR/$TOOL_NAME" "$INSTALL_DIR/"
        sudo chmod +x "$INSTALL_DIR/$TOOL_NAME"
        
        # Create symlink
        if [ -L "/usr/local/bin/$SYMLINK_NAME" ]; then
            echo "Removing existing symlink"
            sudo rm "/usr/local/bin/$SYMLINK_NAME"
        fi
        
        echo "Creating symlink: /usr/local/bin/$SYMLINK_NAME"
        sudo ln -s "$INSTALL_DIR/$TOOL_NAME" "/usr/local/bin/$SYMLINK_NAME"
        
        echo -e "${GREEN}✓ System-wide installation complete${NC}"
        echo ""
        echo -e "Run with: ${CYAN}$SYMLINK_NAME config.xml${NC}"
        ;;
        
    2)
        # User installation
        echo -e "${CYAN}Installing for user...${NC}"
        
        USER_BIN="$HOME/.local/bin"
        
        # Create directory if needed
        if [ ! -d "$USER_BIN" ]; then
            echo "Creating directory: $USER_BIN"
            mkdir -p "$USER_BIN"
        fi
        
        # Copy tool
        echo "Copying $TOOL_NAME to $USER_BIN/"
        cp "$SCRIPT_DIR/$TOOL_NAME" "$USER_BIN/"
        chmod +x "$USER_BIN/$TOOL_NAME"
        
        # Create symlink
        if [ -L "$USER_BIN/$SYMLINK_NAME" ]; then
            echo "Removing existing symlink"
            rm "$USER_BIN/$SYMLINK_NAME"
        fi
        
        echo "Creating symlink: $USER_BIN/$SYMLINK_NAME"
        ln -s "$USER_BIN/$TOOL_NAME" "$USER_BIN/$SYMLINK_NAME"
        
        # Check if ~/.local/bin is in PATH
        if [[ ":$PATH:" != *":$USER_BIN:"* ]]; then
            echo -e "${YELLOW}Warning: $USER_BIN is not in your PATH${NC}"
            echo ""
            echo "Add to your ~/.bashrc or ~/.profile:"
            echo -e "${CYAN}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
            echo ""
        fi
        
        echo -e "${GREEN}✓ User installation complete${NC}"
        echo ""
        echo -e "Run with: ${CYAN}$SYMLINK_NAME config.xml${NC}"
        ;;
        
    3)
        # Current directory only
        echo -e "${CYAN}No installation - using current directory${NC}"
        chmod +x "$SCRIPT_DIR/$TOOL_NAME"
        echo -e "${GREEN}✓ Tool is executable${NC}"
        echo ""
        echo -e "Run with: ${CYAN}python3 $TOOL_NAME config.xml${NC}"
        ;;
        
    *)
        echo -e "${RED}Invalid option${NC}"
        exit 1
        ;;
esac

# Run smoke test
echo ""
echo -e "${CYAN}Running smoke test...${NC}"

SAMPLE_CONFIG="$SCRIPT_DIR/freepbx-tools/bin/123net_internal_docs/CSU_VVX600.cfg"

if [ -f "$SAMPLE_CONFIG" ]; then
    if [ "$INSTALL_OPTION" -eq 3 ]; then
        TEST_CMD="python3 $SCRIPT_DIR/$TOOL_NAME"
    else
        TEST_CMD="$SYMLINK_NAME"
    fi
    
    if $TEST_CMD "$SAMPLE_CONFIG" --no-color > /tmp/phone_analyzer_test.log 2>&1; then
        echo -e "${GREEN}✓ Smoke test passed${NC}"
        
        # Show sample output
        echo ""
        echo "Sample output:"
        head -20 /tmp/phone_analyzer_test.log
        echo "..."
        rm -f /tmp/phone_analyzer_test.log
    else
        echo -e "${RED}✗ Smoke test failed${NC}"
        echo "Check /tmp/phone_analyzer_test.log for details"
    fi
else
    echo -e "${YELLOW}Sample config not found - skipping smoke test${NC}"
fi

# Copy documentation
echo ""
echo -e "${CYAN}Documentation files:${NC}"

if [ -f "$SCRIPT_DIR/PHONE_CONFIG_ANALYZER_README.md" ]; then
    echo "  • PHONE_CONFIG_ANALYZER_README.md - Full documentation"
fi

if [ -f "$SCRIPT_DIR/PHONE_CONFIG_ANALYZER_QUICKREF.md" ]; then
    echo "  • PHONE_CONFIG_ANALYZER_QUICKREF.md - Quick reference"
fi

if [ -f "$SCRIPT_DIR/phone_config_analyzer_demo.py" ]; then
    echo "  • phone_config_analyzer_demo.py - Interactive demo"
fi

# Finish
echo ""
echo -e "${GREEN}"
echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                            ║"
echo "║                      Installation Complete!                                ║"
echo "║                                                                            ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

# Show next steps
echo -e "${CYAN}Next steps:${NC}"
echo ""
echo "  1. Analyze a phone config:"
if [ "$INSTALL_OPTION" -eq 3 ]; then
    echo -e "     ${CYAN}python3 $TOOL_NAME /path/to/config.xml${NC}"
else
    echo -e "     ${CYAN}$SYMLINK_NAME /path/to/config.xml${NC}"
fi
echo ""

echo "  2. Batch analyze configs:"
if [ "$INSTALL_OPTION" -eq 3 ]; then
    echo -e "     ${CYAN}python3 $TOOL_NAME --directory /tftpboot/configs/${NC}"
else
    echo -e "     ${CYAN}$SYMLINK_NAME --directory /tftpboot/configs/${NC}"
fi
echo ""

echo "  3. Export results:"
if [ "$INSTALL_OPTION" -eq 3 ]; then
    echo -e "     ${CYAN}python3 $TOOL_NAME config.xml --json report.json --csv summary.csv${NC}"
else
    echo -e "     ${CYAN}$SYMLINK_NAME config.xml --json report.json --csv summary.csv${NC}"
fi
echo ""

echo "  4. Run demo:"
echo -e "     ${CYAN}python3 phone_config_analyzer_demo.py${NC}"
echo ""

echo "  5. View documentation:"
echo -e "     ${CYAN}less PHONE_CONFIG_ANALYZER_README.md${NC}"
echo ""

echo -e "${GREEN}Happy analyzing!${NC}"
echo ""
