import asyncio
import os
import ssl
import certifi
import time
from dotenv import load_dotenv

from pipecat.frames.frames import EndFrame, TextFrame, TranscriptionFrame, TTSStartedFrame, TTSStoppedFrame, LLMFullResponseStartFrame, LLMFullResponseEndFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.aggregators.sentence import SentenceAggregator
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.websocket.server import (
    WebsocketServerTransport,
    WebsocketServerParams,
)
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.audio.vad.silero import SileroVADAnalyzer

load_dotenv()

# Fix SSL certificate issues on macOS
ssl_context = ssl.create_default_context(cafile=certifi.where())

class TimingLogger(FrameProcessor):
    """Logs timing between pipeline stages."""

    def __init__(self):
        super().__init__()
        self.transcription_time = None
        self.llm_start_time = None
        self.llm_first_token_time = None
        self.tts_start_time = None

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            self.transcription_time = time.time()
            print(f"\n⏱️  [STT] Transcription received: \"{frame.text}\"")

        elif isinstance(frame, LLMFullResponseStartFrame):
            self.llm_start_time = time.time()
            if self.transcription_time:
                elapsed = (self.llm_start_time - self.transcription_time) * 1000
                print(f"⏱️  [LLM] Started generating (STT→LLM: {elapsed:.0f}ms)")

        elif isinstance(frame, LLMFullResponseEndFrame):
            if self.llm_start_time:
                elapsed = (time.time() - self.llm_start_time) * 1000
                print(f"⏱️  [LLM] Finished generating ({elapsed:.0f}ms)")

        elif isinstance(frame, TTSStartedFrame):
            self.tts_start_time = time.time()
            if self.transcription_time:
                elapsed = (self.tts_start_time - self.transcription_time) * 1000
                print(f"⏱️  [TTS] Started speaking (Total STT→TTS: {elapsed:.0f}ms)")

        elif isinstance(frame, TTSStoppedFrame):
            if self.tts_start_time:
                elapsed = (time.time() - self.tts_start_time) * 1000
                total = (time.time() - self.transcription_time) * 1000 if self.transcription_time else 0
                print(f"⏱️  [TTS] Finished speaking ({elapsed:.0f}ms, Total: {total:.0f}ms)\n")

        await self.push_frame(frame, direction)

async def main():
    # WebSocket transport for mobile app connection
    transport = WebsocketServerTransport(
        params=WebsocketServerParams(
            host="0.0.0.0",
            port=8765,
            audio_in_enabled=True,
            audio_out_enabled=True,
            serializer=ProtobufFrameSerializer(),
            vad_analyzer=SileroVADAnalyzer(),
        )
    )

    # Speech-to-Text: Deepgram Nova-2
    stt = DeepgramSTTService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        model="nova-2",
    )

    # LLM: OpenRouter (access to multiple models)
    llm = OpenAILLMService(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
        model=os.getenv("LLM_MODEL", "google/gemini-2.0-flash-001"),
    )

    # Text-to-Speech: ElevenLabs
    tts = ElevenLabsTTSService(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
        voice_id=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
        model="eleven_turbo_v2",
        output_format="pcm_24000",  # Higher quality audio
        params=ElevenLabsTTSService.InputParams(
            stability=0.5,  # Lower = more expressive
            similarity_boost=0.75,  # Higher = closer to original voice
            style=0.3,  # Add some style/emotion
            use_speaker_boost=True,  # Enhance clarity
        ),
    )

    # Conversation context with system prompt
    messages = [
        {
            "role": "system",
            "content": """You are a helpful voice assistant. Keep responses concise
and conversational since they will be spoken aloud. Aim for 1-3 sentences
unless the user asks for detailed information. Be friendly and natural.""",
        }
    ]

    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    # Timing logger for performance monitoring
    timing_logger = TimingLogger()

    # Build pipeline: Audio In → STT → LLM → TTS → Audio Out
    pipeline = Pipeline([
        transport.input(),
        stt,
        timing_logger,  # Log after STT
        context_aggregator.user(),
        llm,
        SentenceAggregator(),
        tts,
        transport.output(),
        context_aggregator.assistant(),
    ])

    runner = PipelineRunner()
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        print(f"Client connected: {client}")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        print(f"Client disconnected: {client}")

    print("=" * 50)
    print("Voice Chat Server Starting")
    print("=" * 50)
    print(f"WebSocket: ws://0.0.0.0:8765")
    print(f"LLM Model: {os.getenv('LLM_MODEL', 'anthropic/claude-sonnet-4-20250514')}")
    print("=" * 50)

    await runner.run(task)

if __name__ == "__main__":
    asyncio.run(main())
