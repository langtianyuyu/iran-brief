#!/usr/bin/env bash
set -euo pipefail
cd /Users/apple/Documents/codexproject
set -a
source .env
set +a
/usr/bin/python3 /Users/apple/Documents/codexproject/daily_iran_brief.py >> /Users/apple/Documents/codexproject/logs/iran_brief.log 2>&1
