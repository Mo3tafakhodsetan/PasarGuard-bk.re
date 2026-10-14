#!/bin/bash

CYAN='\033[0;96m'
BLUE='\033[0;94m'
GREEN='\033[0;92m'
YELLOW='\033[0;93m'
RED='\033[0;91m'
NC='\033[0m'

echo -e "${BLUE}==================================================${NC}"
echo -e "${CYAN}      Pasarguard Enterprise Installer${NC}"
echo -e "${BLUE}==================================================${NC}"

echo -e "${YELLOW}➔ Installing required system packages (paramiko, unzip, flask)...${NC}"
apt-get update >/dev/null 2>&1
apt-get install -y python3-paramiko python3-flask python3-pip unzip >/dev/null 2>&1

URL="https://raw.githubusercontent.com/Mo3tafakhodsetan/PasarGuard-bk.re/main/bk_re.py"
FILE="bk_re.py"

echo -e "${CYAN}➔ Downloading the script...${NC}"
if curl -sO "$URL"; then
    echo -e "${GREEN}✔ Download successful!${NC}"
else
    echo -e "${RED}✖ Download failed. Please check the repository URL.${NC}"
    exit 1
fi

echo ""
echo -e "${CYAN}Which version do you want to run?${NC}"
echo -e "  1) Terminal Management Menu"
echo -e "  2) Web Panel Dashboard"
read -p "Select option (1/2): " install_choice

mkdir -p /opt/pasarguard

if [ "$install_choice" == "2" ]; then
    read -p "🔑 Enter a secure password for Web Panel login: " web_pwd
    echo "$web_pwd" > /opt/pasarguard/.web_pwd
    echo -e "${GREEN}✔ Password saved successfully!${NC}"
    echo -e "${CYAN}➔ Starting Web Panel on port 5000...${NC}"
    python3 "$FILE" --web
else
    echo -e "${CYAN}➔ Starting Terminal Menu...${NC}"
    python3 "$FILE"
fi
