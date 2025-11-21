# Voice Chat with Custom LLM Backend

A real-time voice chat system similar to ChatGPT's voice mode, but with the flexibility to route responses through different LLMs (Gemini, Claude, Llama) via OpenRouter.

## Architecture

```
┌─────────────┐     WebSocket      ┌─────────────────────────────────────┐
│   Client    │ ◄──────────────► │            Pipecat Server            │
│ (mac_client)│    Protobuf       │                                     │
└─────────────┘                   │  ┌─────┐   ┌─────┐   ┌─────┐       │
                                  │  │ STT │ → │ LLM │ → │ TTS │       │
                                  │  └─────┘   └─────┘   └─────┘       │
                                  │  Deepgram  OpenRouter ElevenLabs   │
                                  └─────────────────────────────────────┘
```

### Pipeline Flow

1. **Audio Input** → Client captures 16kHz mono PCM, sends via WebSocket
2. **VAD** → Silero detects speech start/stop
3. **STT** → Deepgram Nova-2 transcribes in real-time (streaming)
4. **LLM** → OpenRouter routes to Gemini/Claude/Llama
5. **TTS** → ElevenLabs generates speech
6. **Audio Output** → 24kHz audio streamed back to client

### Latency Profile

| Stage | Service | Latency |
|-------|---------|---------|
| STT | Deepgram Nova-2 | <1ms (streaming) |
| LLM | Gemini 2.0 Flash | 400-800ms TTFB |
| TTS | ElevenLabs Turbo v2 | 250ms TTFB |
| **Total** | | **~750-1000ms** |

## Quick Start

### Prerequisites

- Python 3.11+
- API keys for: Deepgram, OpenRouter, ElevenLabs

### Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys
```

### Run

**Server:**
```bash
export SSL_CERT_FILE=$(python -m certifi)  # Required on macOS
python server.py
```

**Client (separate terminal):**
```bash
python mac_client.py
```

Press Enter to start/stop recording.

## Configuration

### Environment Variables

```bash
# Speech-to-Text
DEEPGRAM_API_KEY=...

# LLM (via OpenRouter)
OPENROUTER_API_KEY=...
LLM_MODEL=google/gemini-2.0-flash-001

# Text-to-Speech
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
```

### LLM Model Options

Via OpenRouter, you can use:
- `google/gemini-2.0-flash-001` - Fast, good quality (default)
- `anthropic/claude-sonnet-4` - More capable, slower
- `anthropic/claude-3-5-haiku-20241022` - Fast but may hit rate limits
- `meta-llama/llama-3.1-70b-instruct` - Open source option

### Voice Options

ElevenLabs voice IDs:
- `21m00Tcm4TlvDq8ikWAM` - Rachel (default)
- `EXAVITQu4vr4xnSDxMaL` - Bella
- `ErXwobaYiN019PkySvjV` - Antoni
- `pNInz6obpgDQGcFmaJgB` - Adam

## Code Structure

```
backend/
├── server.py          # Pipecat pipeline server
├── mac_client.py      # Test client for macOS
├── requirements.txt   # Python dependencies
├── .env.example       # Environment template
├── Dockerfile         # Container deployment
├── CLAUDE.md          # AI assistant context
└── HOW_IT_WORKS.md    # Detailed architecture docs
```

### Key Implementation Details

**Server Pipeline (`server.py`):**

```python
pipeline = Pipeline([
    transport.input(),           # WebSocket audio input
    stt,                         # Deepgram STT
    timing_logger,               # Latency monitoring
    context_aggregator.user(),   # Add to conversation history
    llm,                         # OpenRouter LLM
    SentenceAggregator(),        # Buffer for complete sentences
    tts,                         # ElevenLabs TTS
    transport.output(),          # WebSocket audio output
    context_aggregator.assistant() # Save response to history
])
```

**Client Protocol (`mac_client.py`):**

```python
# Send audio frame
proto_frame = frame_protos.Frame()
proto_frame.audio.audio = raw_pcm_bytes
proto_frame.audio.sample_rate = 16000
proto_frame.audio.num_channels = 1
await ws.send(proto_frame.SerializeToString())
```

**TimingLogger** - Custom FrameProcessor that logs latency at each stage:
- `TranscriptionFrame` - STT complete
- `LLMFullResponseStartFrame` - LLM first token
- `TTSStartedFrame` - TTS first audio

## Performance Tuning

### Faster LLM Options

**Groq** (~100-200ms TTFB when available):
```python
from pipecat.services.groq.llm import GroqLLMService
llm = GroqLLMService(api_key=..., model="llama-3.3-70b-versatile")
```

### Faster TTS Options

**Cartesia** (~50-100ms TTFB):
```python
from pipecat.services.cartesia.tts import CartesiaTTSService
tts = CartesiaTTSService(api_key=..., voice_id="...")
```

## Docker Deployment

```bash
docker build -t voice-chat .
docker run -p 8765:8765 --env-file .env voice-chat
```

## Troubleshooting

**SSL errors on macOS:**
```bash
export SSL_CERT_FILE=$(python -m certifi)
```

**Connection timeout:**
- Server has idle timeout; restart if client disconnects after long pause

**403 errors from Groq:**
- Network/account restrictions; switch to OpenRouter

**Rate limits:**
- Switch to a different model or wait

## License

MIT
