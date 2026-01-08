#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MODELS_DIR="$PROJECT_DIR/models"

echo "=================================================="
echo "  Raphael - Model Download Script"
echo "=================================================="
echo ""

mkdir -p "$MODELS_DIR/whisper"
mkdir -p "$MODELS_DIR/piper"

echo "[1/3] Downloading Whisper model (for Phase 2)..."
echo "Skipping for now - will be downloaded in Phase 2"
echo ""

echo "[2/3] Downloading Piper voices (for Phase 2)..."
echo "Skipping for now - will be downloaded in Phase 2"
echo ""

echo "[3/3] Pulling Ollama model..."
echo ""

MODEL="qwen2.5:7b-instruct-q5_K_M"

if ollama list 2>/dev/null | grep -q "qwen2.5:7b-instruct"; then
    echo "Model $MODEL already exists."
else
    echo "Pulling $MODEL (~5.5GB)..."
    ollama pull "$MODEL"
fi

echo ""
echo "=================================================="
echo "  Model download complete!"
echo "=================================================="
