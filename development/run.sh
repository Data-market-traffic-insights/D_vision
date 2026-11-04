#!/bin/sh
# 일반 사용자용 D·VISION 최종 프로토타입
cd "$(dirname "$0")" || exit 1
exec .venv/bin/python -m streamlit run prototype_app.py "$@"
