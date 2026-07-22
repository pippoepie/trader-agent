#!/bin/bash
# Runs one agent decision cycle, then regenerates the dashboard.
# Invoked on a schedule by the launchd job installed via setup_automation.sh.
set -u
cd "$(dirname "$0")"

echo "===== $(date -u +"%Y-%m-%dT%H:%M:%SZ") =====" >> automation.log
python3 run.py --execute >> automation.log 2>&1
python3 dashboard.py >> automation.log 2>&1
