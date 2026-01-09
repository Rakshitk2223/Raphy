# Raphael

A local, privacy-first personal AI assistant inspired by the Great Sage from "That Time I Got Reincarnated as a Slime."

## Features

- **Local LLM** - Runs entirely on your machine using Ollama (Qwen 2.5)
- **Voice Interaction** - Click the orb to speak, get spoken responses
- **Hinglish Support** - Understands and responds in Hindi, English, or mixed
- **Human-like Voice** - Edge TTS for natural, expressive speech
- **Real-time Streaming** - See responses as they're generated
- **Privacy First** - All conversations stay on your machine

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/Rakshitk2223/Raphy.git
cd Raphy

# 2. Install dependencies
./scripts/install.sh

# 3. Start the server
./scripts/start.sh
```

Then open http://localhost:8080

## Requirements

### Hardware
- 8GB+ VRAM (RTX 3060 or better recommended)
- 16GB RAM
- CUDA-capable GPU

### Software
- Python 3.11+
- Ollama with CUDA support (`ollama-cuda` on Arch Linux)
- ffmpeg (for audio processing)

## Models Used

| Component | Model | Size | Purpose |
|-----------|-------|------|---------|
| LLM | Qwen 2.5 7B | 5.4 GB | Text generation |
| STT | Whisper large-v3 | 2.9 GB | Speech recognition |
| TTS | Edge TTS | Cloud | Human-like speech |

## Profiles

Switch between quality and speed modes:

```bash
# Quality mode (7B LLM, large-v3 STT)
./scripts/profile.sh p1

# Speed mode (3B LLM, medium STT)
./scripts/profile.sh p2
```

## Controls

| Action | Control |
|--------|---------|
| Send message | Enter |
| Voice input | Click orb or Alt+Enter |
| Stop generation | Esc or click orb |
| Toggle mute | Click speaker icon |
| Copy message | Hover and click copy button |

## Tech Stack

- **Backend**: FastAPI + WebSocket
- **LLM**: Ollama (Qwen 2.5)
- **STT**: faster-whisper (CUDA)
- **TTS**: Edge TTS (primary) / Piper (offline fallback)
- **Frontend**: Vanilla JS with galaxy-themed orb UI

## Project Structure

```
raphael/
├── backend/
│   ├── api/          # WebSocket endpoints
│   ├── core/         # LLM, STT, TTS modules
│   └── personality/  # System prompts
├── frontend/
│   ├── css/          # Styles
│   └── js/           # UI logic
├── profiles/         # P1/P2 configuration
├── scripts/          # Install/start scripts
└── models/           # Downloaded voice models
```

## License

MIT
