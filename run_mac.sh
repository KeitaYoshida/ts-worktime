#!/bin/zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
VENV_DIR="$ROOT_DIR/.venv"
REQ_FILE="$ROOT_DIR/requirements-mac.txt"
VENV_PYTHON="$VENV_DIR/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "python.org 版 Python 3.14 が見つかりません: $PYTHON_BIN"
  exit 1
fi

cd "$ROOT_DIR"

if [[ -x "$VENV_PYTHON" ]]; then
  VENV_BASE_PREFIX="$("$VENV_PYTHON" -c 'import sys; print(sys.base_prefix)')"
  EXPECTED_BASE_PREFIX="/Library/Frameworks/Python.framework/Versions/3.14"
  if [[ "$VENV_BASE_PREFIX" != "$EXPECTED_BASE_PREFIX" ]]; then
    echo "既存の .venv は python.org 版ではないため作り直します..."
    rm -rf "$VENV_DIR"
  fi
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "仮想環境を作成します..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "依存関係を確認します..."
python -m pip install -U pip
python -m pip install -r "$REQ_FILE"

echo "アプリを起動します..."
python main.py
