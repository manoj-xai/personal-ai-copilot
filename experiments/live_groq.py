import io
import os
import sys
import wave
import array
import queue
import threading
import pyaudiowpatch as pyaudio
from groq import Groq

sys.stdout.reconfigure(encoding="utf-8")

client = Groq(api_key=os.environ["GROQ_API_KEY"])

CHUNK_SECONDS = 6
MIN_LOUDNESS = 500       # chunks quieter than this are treated as silence
MODEL = "whisper-large-v3"

audio_queue = queue.Queue()


def find_loopback(p):
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    speakers = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
    if not speakers["isLoopbackDevice"]:
        for lb in p.get_loopback_device_info_generator():
            if speakers["name"] in lb["name"]:
                return lb
        raise SystemExit("No loopback device found.")
    return speakers


def record_loop():
    p = pyaudio.PyAudio()
    dev = find_loopback(p)
    channels = dev["maxInputChannels"]
    rate = int(dev["defaultSampleRate"])
    stream = p.open(format=pyaudio.paInt16, channels=channels, rate=rate,
                    input=True, frames_per_buffer=1024,
                    input_device_index=dev["index"])
    needed = int(rate / 1024 * CHUNK_SECONDS)
    print("Listening to:", dev["name"])
    while True:
        frames = [stream.read(1024, exception_on_overflow=False)
                  for _ in range(needed)]
        audio_queue.put((b"".join(frames), channels, rate))


def to_wav_bytes(raw, channels, rate):
    data = array.array("h", raw)
    factor = max(1, rate // 16000)
    group = channels * factor
    mono = array.array("h")
    for i in range(0, len(data) - group + 1, group):
        mono.append(sum(data[i:i + group]) // group)
    peak = max((abs(x) for x in mono), default=0)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate // factor)
        w.writeframes(mono.tobytes())
    return buf.getvalue(), peak


threading.Thread(target=record_loop, daemon=True).start()
print("Ready. Play the call audio. Press Ctrl+C to stop.\n")

try:
    while True:
        raw, channels, rate = audio_queue.get()
        wav_bytes, peak = to_wav_bytes(raw, channels, rate)
        if peak < MIN_LOUDNESS:
            continue                      # silence, skip it
        try:
            result = client.audio.translations.create(
                file=("chunk.wav", wav_bytes),
                model=MODEL,
                response_format="json",
            )
            text = result.text.strip()
            if text:
                print("Client:", text)
                with open("transcript.txt", "a", encoding="utf-8") as f:
                    f.write(text + "\n")
        except Exception as e:
            print("Groq problem:", e)
except KeyboardInterrupt:
    print("\nStopped.")