# How the Voice Chat System Works

## Overview

This is a real-time voice chat system that lets you talk to an AI and hear spoken responses back. It's like ChatGPT's voice mode, but you can choose which AI model powers the responses.

## The Pipeline

When you speak, your audio flows through this pipeline:

```
Your Voice → [Microphone] → [WebSocket] → [STT] → [LLM] → [TTS] → [WebSocket] → [Speaker]
```

### Step-by-Step Flow

1. **You speak into your microphone**
   - Audio is captured at 16kHz, mono, 16-bit PCM
   - Sent in small 40ms chunks for real-time processing

2. **Voice Activity Detection (VAD)**
   - Silero VAD detects when you start and stop speaking
   - Prevents processing silence or background noise
   - Triggers transcription only when speech is detected

3. **Speech-to-Text (Deepgram)**
   - Converts your audio to text in real-time
   - Uses streaming for instant results (<1ms latency)
   - Example: "What's the weather like?" → text

4. **Language Model (OpenRouter → Gemini/Claude)**
   - Receives your transcribed text
   - Generates a conversational response
   - Maintains conversation history for context
   - ~400-800ms to first token

5. **Text-to-Speech (ElevenLabs)**
   - Converts AI response to natural-sounding speech
   - Streams audio back as it's generated
   - ~250ms to first audio chunk

6. **You hear the response**
   - Audio plays through your speakers
   - 24kHz output for high quality

## Key Components

### Server (`server.py`)

The server orchestrates everything using Pipecat, a framework for building real-time AI pipelines.

```python
pipeline = Pipeline([
    transport.input(),           # Receive audio from client
    stt,                         # Deepgram: audio → text
    context_aggregator.user(),   # Add to conversation history
    llm,                         # Generate AI response
    SentenceAggregator(),        # Wait for complete sentences
    tts,                         # ElevenLabs: text → audio
    transport.output(),          # Send audio to client
    context_aggregator.assistant() # Save AI response to history
])
```

### Client (`mac_client.py`)

The client handles:
- Recording audio from your microphone
- Sending audio frames via WebSocket using protobuf serialization
- Receiving and playing back audio responses

### Communication Protocol

Client and server communicate via WebSocket using protobuf frames:
- `AudioRawFrame`: Raw PCM audio data
- `TranscriptionFrame`: Text from STT
- `TextFrame`: LLM response text

## Services Used

| Service | Purpose | Latency | Why This One? |
|---------|---------|---------|---------------|
| **Deepgram** | Speech-to-Text | <1ms | Streaming, accurate, fast |
| **OpenRouter** | LLM Gateway | ~500ms | Access to multiple models |
| **Gemini Flash** | AI Model | ~400ms | Fast, good quality |
| **ElevenLabs** | Text-to-Speech | ~250ms | Natural voices |

## Latency Breakdown

Total time from end of speech to hearing response: **~750-1000ms**

- STT: ~0ms (streaming)
- LLM: ~400-800ms (time to first token)
- TTS: ~250ms (time to first audio)

## Configuration

All services are configured via environment variables in `.env`:

```bash
DEEPGRAM_API_KEY=...      # STT
OPENROUTER_API_KEY=...    # LLM gateway
ELEVENLABS_API_KEY=...    # TTS
LLM_MODEL=google/gemini-2.0-flash-001  # Which AI model
```

## Alternative Configurations

You can swap services for different tradeoffs:

**Faster LLM (when working):**
- Groq Llama 3.3: ~100-200ms TTFB
- Requires Groq API key, sometimes has access issues

**Faster TTS:**
- Cartesia: ~50-100ms TTFB
- Requires separate API key

**Different AI models via OpenRouter:**
- `anthropic/claude-sonnet-4` - More capable, slower
- `anthropic/claude-3-5-haiku-20241022` - Fast but may hit rate limits
- `google/gemini-2.0-flash-001` - Good balance of speed and quality

## How Interruptions Work

The system supports interrupting the AI mid-response:
- VAD detects when you start speaking
- Pipeline sends an `InterruptionFrame`
- TTS stops immediately
- New transcription is processed

## Conversation Context

The system maintains conversation history:

```python
messages = [
    {"role": "system", "content": "You are a helpful voice assistant..."},
    {"role": "user", "content": "What's the weather?"},
    {"role": "assistant", "content": "I don't have access to weather data..."},
    {"role": "user", "content": "Tell me a joke then"},
    # ... continues
]
```

This allows for multi-turn conversations where the AI remembers what you've discussed.
