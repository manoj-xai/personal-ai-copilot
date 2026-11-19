import sys
import wave
import array
import numpy as np
from faster_whisper import WhisperModel

sys.stdout.reconfigure(encoding="utf-8")

# 1. Read the saved file
with wave.open("loopback_test.wav", "rb") as f:
    channels = f.getnchannels()
    rate = f.getframerate()
    data = array.array("h", f.readframes(f.getnframes()))

# 2. Convert to mono, 16000 Hz (same as before)
factor = max(1, rate // 16000)
group = channels * factor
mono = array.array("h")
for i in range(0, len(data) - group + 1, group):
    mono.append(sum(data[i:i + group]) // group)

# 3. Turn into numbers between -1 and 1, which Whisper expects
audio = np.array(mono, dtype=np.float32) / 32768.0

# 4. Transcribe
model = WhisperModel("small", device="cpu", compute_type="int8")
segments, info = model.transcribe(audio, language="ta")

for seg in segments:
    print(seg.text)