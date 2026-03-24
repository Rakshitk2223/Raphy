#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=================================================="
echo "  Raphael - Installation Script"
echo "=================================================="
echo ""

check_command() {
    if command -v "$1" &> /dev/null; then
        echo "[OK] $1 is installed"
        return 0
    else
        echo "[MISSING] $1 is not installed"
        return 1
    fi
}

echo "[1/6] Checking system dependencies..."
echo ""

MISSING_DEPS=()

check_command "python" || MISSING_DEPS+=("python")
check_command "uv" || MISSING_DEPS+=("uv")
check_command "ollama" || MISSING_DEPS+=("ollama")

echo ""

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo "Missing dependencies: ${MISSING_DEPS[*]}"
    echo ""
    echo "Install them with:"
    echo ""
    
    for dep in "${MISSING_DEPS[@]}"; do
        case "$dep" in
            "python")
                echo "  sudo pacman -S python"
                ;;
            "uv")
                echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
                ;;
            "ollama")
                echo "  sudo pacman -S ollama"
                echo "  # OR"
                echo "  curl -fsSL https://ollama.com/install.sh | sh"
                ;;
        esac
    done
    echo ""
    echo "After installing dependencies, run this script again."
    exit 1
fi

echo "[2/6] Setting up Python environment..."
echo ""

if [ ! -d ".venv" ]; then
    uv venv
    echo "Virtual environment created."
else
    echo "Virtual environment already exists."
fi

source .venv/bin/activate

echo ""
echo "[3/6] Installing Python dependencies..."
echo ""

uv pip install -e ".[all]"
uv pip install pathvalidate

echo ""
echo "[4/6] Setting up Ollama..."
echo ""

if ! systemctl is-active --quiet ollama; then
    echo "Starting Ollama service..."
    sudo systemctl enable --now ollama
    sleep 2
fi

echo "Ollama service is running."

MODEL="qwen2.5:7b-instruct-q5_K_M"
echo ""
echo "Checking for model: $MODEL"

if ollama list | grep -q "qwen2.5:7b-instruct"; then
    echo "Model already downloaded."
else
    echo "Downloading model (this may take a while, ~5.5GB)..."
    ollama pull "$MODEL"
fi

echo ""
echo "[5/6] Creating data directories..."
echo ""

mkdir -p data/{memory,conversations}
mkdir -p models/{whisper,piper}

echo "Data directories created."

echo ""
echo "[6/6] Verifying installation..."
echo ""

python -c "from backend.main import app; print('[OK] Backend imports successfully')"

echo ""
echo "=================================================="
echo "  Installation Complete!"
echo "=================================================="
echo ""
echo "To start Raphael:"
echo "  ./scripts/start.sh"
echo ""
echo "Or manually:"
echo "  source .venv/bin/activate"
echo "  python -m backend.main"
echo ""
echo "Then open: http://localhost:8080"
echo ""
