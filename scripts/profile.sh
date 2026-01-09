#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROFILES_DIR="$PROJECT_DIR/profiles"
ENV_FILE="$PROJECT_DIR/.env"

show_help() {
    echo "Raphael Profile Switcher"
    echo ""
    echo "Usage: $0 <profile>"
    echo ""
    echo "Available profiles:"
    echo "  p1, quality   - Quality mode (7B LLM, large-v3 STT) - Best accuracy, ~15-30s response"
    echo "  p2, speed     - Speed mode (3B LLM, medium STT) - Fast responses, ~5-8s"
    echo ""
    echo "Current profile:"
    if [ -f "$ENV_FILE" ]; then
        grep "OLLAMA_MODEL" "$ENV_FILE" 2>/dev/null || echo "  (default settings)"
    else
        echo "  (no profile set - using defaults)"
    fi
}

set_profile() {
    local profile="$1"
    local profile_file=""

    case "$profile" in
        p1|quality)
            profile_file="$PROFILES_DIR/p1-quality.env"
            echo "Switching to P1 (Quality Mode)..."
            ;;
        p2|speed)
            profile_file="$PROFILES_DIR/p2-speed.env"
            echo "Switching to P2 (Speed Mode)..."
            ;;
        *)
            echo "Unknown profile: $profile"
            show_help
            exit 1
            ;;
    esac

    if [ ! -f "$profile_file" ]; then
        echo "Profile file not found: $profile_file"
        exit 1
    fi

    cp "$profile_file" "$ENV_FILE"
    echo "Profile activated! Restart the server for changes to take effect."
    echo ""
    echo "Settings:"
    cat "$ENV_FILE" | grep -v "^#" | grep -v "^$"
}

if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

set_profile "$1"
