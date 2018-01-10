#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"

cd "$SCRIPT_DIR"

tmux new -d -s 'kzbot' 'source .pyenv/bin/activate; ipython -i script.py -- --start'

