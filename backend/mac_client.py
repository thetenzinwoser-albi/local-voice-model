#!/usr/bin/env python3
"""Mac client for voice chat - records audio, sends to server, plays response."""

import asyncio
import subprocess
import tempfile
import os
import wave
import websockets
import pyaudio
import sys
import select
import termios
import tty

# Import Pipecat protobuf frames
sys.path.insert(0, '/Users/tenzinwoser/projects-local/openrouter-but-voice-chat/backend/venv/lib/python3.13/site-packages')
from pipecat.frames.protobufs import frames_pb2 as frame_protos

# Audio settings - Pipecat expects 16kHz mono 16-bit PCM for input
# Output from ElevenLabs is 24kHz
SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK = 640  # 40ms at 16kHz (better for STT)
FORMAT = pyaudio.paInt16

def is_key_pressed():
    """Check if a key has been pressed (non-blocking)."""
    return select.select([sys.stdin], [], [], 0)[0]

class VoiceChatClient:
    def __init__(self, server_url="ws://localhost:8765"):
        self.server_url = server_url
        self.audio = pyaudio.PyAudio()
        self.ws = None

    async def connect(self):
        """Connect to the voice chat server."""
        print(f"Connecting to {self.server_url}...")
        self.ws = await websockets.connect(self.server_url)
        print("✓ Connected!")

    async def record_and_send(self):
        """Record audio from mic until user presses Enter again."""
        print("\n🎤 Recording... (press Enter to stop)")

        stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK
        )

        # Set terminal to raw mode to detect keypress
        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setcbreak(sys.stdin.fileno())

            chunk_count = 0
            while True:
                # Check for keypress to stop
                if is_key_pressed():
                    sys.stdin.read(1)  # Consume the keypress
                    break

                data = stream.read(CHUNK, exception_on_overflow=False)

                # Create Pipecat protobuf frame
                proto_frame = frame_protos.Frame()
                proto_frame.audio.audio = data
                proto_frame.audio.sample_rate = SAMPLE_RATE
                proto_frame.audio.num_channels = CHANNELS

                # Send serialized protobuf
                await self.ws.send(proto_frame.SerializeToString())
                chunk_count += 1

                # Small delay to prevent busy loop
                await asyncio.sleep(0.001)

        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

        # Send a brief silence buffer to let VAD properly detect end of speech
        for _ in range(10):  # ~400ms of silence
            silence = b'\x00' * (CHUNK * 2)
            proto_frame = frame_protos.Frame()
            proto_frame.audio.audio = silence
            proto_frame.audio.sample_rate = SAMPLE_RATE
            proto_frame.audio.num_channels = CHANNELS
            await self.ws.send(proto_frame.SerializeToString())
            await asyncio.sleep(0.04)

        stream.stop_stream()
        stream.close()

        duration = chunk_count * CHUNK / SAMPLE_RATE
        print(f"✓ Recording complete ({duration:.1f}s), processing...")

    async def receive_response(self):
        """Receive and play audio response from server."""
        print("⏳ Waiting for response...")

        audio_chunks = []
        text_response = ""

        try:
            while True:
                try:
                    message = await asyncio.wait_for(self.ws.recv(), timeout=15.0)

                    if isinstance(message, bytes):
                        # Try to parse as protobuf
                        try:
                            proto = frame_protos.Frame.FromString(message)
                            which = proto.WhichOneof("frame")

                            if which == "audio":
                                audio_chunks.append(proto.audio.audio)
                                print(".", end="", flush=True)
                            elif which == "text":
                                text_response = proto.text.text
                                print(f"\n📝 Response: {text_response}")
                            elif which == "transcription":
                                print(f"\n🎤 You said: {proto.transcription.text}")
                        except Exception as e:
                            # Raw audio bytes
                            audio_chunks.append(message)
                    else:
                        print(f"Received text: {message[:100]}")

                except asyncio.TimeoutError:
                    if audio_chunks:
                        print("\n✓ Response received")
                    else:
                        print("\n⚠️  Response timeout")
                    break

        except Exception as e:
            print(f"Error receiving: {e}")

        if audio_chunks:
            await self.play_audio(b''.join(audio_chunks))
        elif not text_response:
            print("No response received")

    async def play_audio(self, audio_data):
        """Play received audio data."""
        print(f"🔊 Playing response ({len(audio_data)} bytes)...")

        # Save to temp WAV file and play with afplay
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            with wave.open(f.name, 'wb') as wav_file:
                wav_file.setnchannels(CHANNELS)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(OUTPUT_SAMPLE_RATE)
                wav_file.writeframes(audio_data)
            temp_path = f.name

        subprocess.run(["afplay", temp_path], check=True)
        os.unlink(temp_path)
        print("✓ Playback complete")

    async def chat_loop(self):
        """Main chat loop."""
        await self.connect()

        print("\n" + "=" * 50)
        print("Voice Chat Client Ready")
        print("=" * 50)
        print("Press Enter to start recording, Enter again to stop")
        print("Type 'q' and Enter to quit\n")

        while True:
            user_input = input("→ ").strip().lower()

            if user_input == 'q':
                print("Goodbye!")
                break

            await self.record_and_send()
            await self.receive_response()

    def cleanup(self):
        """Clean up audio resources."""
        self.audio.terminate()

async def main():
    client = VoiceChatClient()
    try:
        await client.chat_loop()
    finally:
        client.cleanup()
        if client.ws:
            await client.ws.close()

if __name__ == "__main__":
    asyncio.run(main())
