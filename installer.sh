#!/bin/bash
# Created by Roshan Shrestha

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}[*] Zphisher Web UI Installer${NC}"
echo -e "${BLUE}[*] Created by Roshan Shrestha${NC}"
echo ""

# Check for Python3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[!] Python3 is required but not found. Please install python3.${NC}"
    exit 1
fi

# Create Virtual Environment
echo -e "${GREEN}[+] Creating virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}[!] Failed to create virtual environment.${NC}"
        exit 1
    fi
else
    echo -e "${BLUE}[*] Virtual environment already exists.${NC}"
fi

# Activate and Install Dependencies
echo -e "${GREEN}[+] Installing dependencies...${NC}"
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip &> /dev/null

# Install required packages
pip install fastapi uvicorn aiofiles pydantic

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}[+] Installation successful!${NC}"
    echo -e "${BLUE}[*] Run ./zphisher.sh to start the tool.${NC}"
else
    echo -e "${RED}[!] Failed to install dependencies.${NC}"
    exit 1
fi
