# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Real-time voice chat backend using Pipecat framework. Audio flows through a WebSocket-based pipeline: STT (Deepgram) → LLM (Groq) → TTS (ElevenLabs). Designed as an alternative to ChatGPT voice mode with customizable LLM backends.

## Common Commands

### Running the Server
```bash
cd backend
source venv/bin/activate
export SSL_CERT_FILE=$(python -m certifi)  # Required on macOS for SSL
python server.py
```

### Running the Mac Test Client
```bash
cd backend
source venv/bin/activate
python mac_client.py
```

### Installing Dependencies
```bash
pip install -r requirements.txt
```

### Docker
```bash
docker build -t voice-chat-backend .
docker run -p 8765:8765 --env-file .env voice-chat-backend
```

## Architecture

### Pipeline Flow
```
Audio In → WebSocket → Deepgram STT → LLM (Groq) → ElevenLabs TTS → WebSocket → Audio Out
```

### Key Components

- **server.py**: Main Pipecat server orchestrating the voice pipeline
  - `TimingLogger`: Custom FrameProcessor for latency monitoring
  - Pipeline uses `ProtobufFrameSerializer` for WebSocket communication
  - `SileroVADAnalyzer` for voice activity detection

- **mac_client.py**: Test client for local development
  - Records 16kHz mono PCM audio
  - Outputs 24kHz audio from TTS
  - Uses protobuf frames from `pipecat.frames.protobufs.frames_pb2`

### Service Configuration

Services are configured via environment variables in `.env`:
- **STT**: Deepgram Nova-2 (streaming, ~<1ms latency)
- **LLM**: Groq Llama 3.3 70B (~100-200ms TTFB) - configurable via `LLM_MODEL`
- **TTS**: ElevenLabs Turbo v2 (~250ms TTFB)

Alternative configurations that have been tested:
- OpenRouter for LLM (higher latency ~500-800ms but supports Claude/Gemini)
- Cartesia for TTS (faster ~50-100ms but requires separate API key)

### Audio Settings

- Input: 16kHz, mono, 16-bit PCM, 640-sample chunks (40ms)
- Output: 24kHz, mono, 16-bit PCM

## Environment Variables

Copy `.env.example` to `.env` and configure:
- `DEEPGRAM_API_KEY`: STT service
- `GROQ_API_KEY`: LLM inference
- `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID`: TTS service
- `LLM_MODEL`: Model identifier (e.g., `llama-3.3-70b-versatile`)

## Known Issues

- macOS requires `SSL_CERT_FILE` export for API calls
- Groq models can be decommissioned - check console.groq.com/docs/deprecations for current models
- VAD requires silence buffer after speech to properly detect end of utterance
