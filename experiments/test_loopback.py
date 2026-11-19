import wave
import pyaudiowpatch as pyaudio

DURATION = 5  # seconds to record

p = pyaudio.PyAudio()

# Find the default speakers, then their loopback version
wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
speakers = p.get_device_info_by_index(wasapi["defaultOutputDevice"])

if not speakers["isLoopbackDevice"]:
    for lb in p.get_loopback_device_info_generator():
        if speakers["name"] in lb["name"]:
            speakers = lb
            break
    else:
        raise SystemExit("No loopback device found.")

print("Recording from:", speakers["name"])

channels = speakers["maxInputChannels"]
rate = int(speakers["defaultSampleRate"])

stream = p.open(
    format=pyaudio.paInt16,
    channels=channels,
    rate=rate,
    input=True,
    frames_per_buffer=1024,
    input_device_index=speakers["index"],
)

frames = []
for _ in range(int(rate / 1024 * DURATION)):
    frames.append(stream.read(1024))

stream.stop_stream()
stream.close()
p.terminate()

with wave.open("loopback_test.wav", "wb") as f:
    f.setnchannels(channels)
    f.setsampwidth(2)  # 16-bit audio
    f.setframerate(rate)
    f.writeframes(b"".join(frames))

print("Saved loopback_test.wav")