# Raphael

A local, privacy-first personal AI assistant inspired by the Great Sage from "That Time I Got Reincarnated as a Slime."

## Features

- **Local LLM** - Runs entirely on your machine using Ollama (Qwen 2.5)
- **Voice Interaction** - Click the orb to speak, get spoken responses
- **Hinglish Support** - Understands and responds in Hindi, English, or mixed
- **Offline TTS** - Piper TTS runs completely offline (no cloud required)
- **Real-time Streaming** - See responses as they're generated
- **Privacy First** - All conversations stay on your machine
- **File Knowledge** - Index your documents for the AI to search
- **Memory** - Remember things you tell it, query later

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

## Configuration

All settings are in `backend/config.py` or `.env`:

```bash
# LLM
OLLAMA_MODEL=qwen2.5:7b-instruct-q5_K_M

# STT (Speech to Text)
STT_MODEL=large-v3

# TTS (Text to Speech) - piper (free/offline) or edge (cloud)
TTS_BACKEND=piper
```

## File Knowledge (RAG)

Add your documents to the knowledge folder and index them:

```bash
# 1. Add files to data/memory/knowledge/
# Supported: PDF, DOCX, TXT, MD

# 2. Index the files
python scripts/index_knowledge.py

# 3. Ask questions about your files
# The AI will search the vector database for relevant info
```

## Memory

The AI can remember things you tell it:

- **"Remember that my meeting is at 3pm"** - Stores as JSON
- **"What did I tell you to remember?"** - Queries memory
- Full CRUD: Add, Read, Update, Delete notes

Memory is stored in `data/memory/notes/notes.json`

## Models Used

| Component | Model | Size | Purpose |
|-----------|-------|------|---------|
| LLM | Qwen 2.5 7B | 5.4 GB | Text generation |
| STT | Whisper large-v3 | 2.9 GB | Speech recognition |
| TTS | Piper (offline) | ~100 MB | Human-like speech |

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
- **TTS**: Piper (offline/free) / Edge TTS (optional cloud)
- **Memory**: ChromaDB + sentence-transformers
- **Frontend**: Vanilla JS with galaxy-themed orb UI

## Project Structure

```
raphael/
├── backend/
│   ├── api/          # WebSocket & REST endpoints
│   ├── core/         # LLM, STT, TTS modules
│   ├── memory/       # Vector store & notes
│   └── personality/  # System prompts
├── frontend/
│   ├── css/          # Styles
│   └── js/           # UI logic
├── data/
│   └── memory/
│       ├── knowledge/   # Your files to index
│       ├── notes/      # Remembered items (JSON)
│       └── chroma/      # Vector database
├── scripts/
│   └── index_knowledge.py  # Index your files
└── models/           # Downloaded voice models
```

## API

### REST Endpoints

- `GET /api/health` - Health check
- `GET /api/models` - List available Ollama models
- `POST /api/chat` - Send chat message
- `GET /api/memory/notes` - List all notes
- `POST /api/memory/notes` - Add a note
- `POST /api/memory/search` - Search knowledge base

### WebSocket

Connect to `/ws/{client_id}` for real-time chat with streaming responses.

## License

MIT
