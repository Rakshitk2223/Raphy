#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Run ./scripts/install.sh first."
    exit 1
fi

source .venv/bin/activate

if ! systemctl is-active --quiet ollama; then
    echo "Starting Ollama service..."
    sudo systemctl start ollama
    sleep 2
fi

export OLLAMA_CUDA=1

echo ""
echo "Starting Raphael..."
echo ""

python -m backend.main
