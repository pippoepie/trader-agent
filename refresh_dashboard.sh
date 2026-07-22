#!/bin/bash
# Regenerates dashboard.html only (no trading decision, no Claude call) —
# runs much more often than automate.sh so the profit tracker/positions
# actually stay close to real-time between trading cycles.
set -u
cd "$(dirname "$0")"
python3 dashboard.py >> dashboard_refresh.log 2>&1
