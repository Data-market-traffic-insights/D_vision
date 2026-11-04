#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python ]; then
    echo '먼저 Python 3.12로 가상환경을 만들고 requirements.txt를 설치해 주세요.' >&2
    exit 1
fi
exec .venv/bin/python -m streamlit run prototype_app.py "$@"
