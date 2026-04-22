#!/usr/bin/env bash
# 在 conda 环境 auto 中启动脚本
set -euo pipefail
cd "$(dirname "$0")"
exec conda run --no-capture-output -n auto python3 course_autoplay.py
