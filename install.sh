#!/bin/bash

CYAN='\033[0;96m'
BLUE='\033[0;94m'
GREEN='\033[0;92m'
YELLOW='\033[0;93m'
NC='\033[0m'

echo -e "${BLUE}==================================================${NC}"
echo -e "${CYAN}      Pasarguard Manager Utility Installer${NC}"
echo -e "${BLUE}==================================================${NC}"

echo -e "${YELLOW}➔ Installing required system packages (paramiko, unzip)...${NC}"
apt-get update >/dev/null 2>&1
apt-get install -y python3-paramiko unzip >/dev/null 2>&1

URL="https://raw.githubusercontent.com/Mo3tafakhodsetan/PasarGuard-bk.re/main/bk_re.py"
FILE="bk_re.py"

echo -e "${CYAN}➔ Downloading the script to the current directory...${NC}"

if curl -sO "$URL"; then
    echo -e "${GREEN}✔ Download successful!${NC}"
    echo -e "${CYAN}➔ Starting the utility...${NC}"
    echo ""
    python3 "$FILE"
else
    echo -e "${RED}✖ Download failed. Please check your internet connection or the GitHub repository.${NC}"
    exit 1
    fi
