import wave
import array

with wave.open("loopback_test.wav", "rb") as f:
    print("Channels:", f.getnchannels())
    print("Sample rate:", f.getframerate())
    print("Length (seconds):", round(f.getnframes() / f.getframerate(), 1))
    data = array.array("h", f.readframes(f.getnframes()))

peak = max(abs(x) for x in data)
print("Loudness peak (max 32767):", peak)