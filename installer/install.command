#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 install.py
echo
read -p "Press Enter to close..."
