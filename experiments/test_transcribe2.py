import wave
import array
import speech_recognition as sr

# 1. Read the saved file
with wave.open("loopback_test.wav", "rb") as f:
    channels = f.getnchannels()
    rate = f.getframerate()
    data = array.array("h", f.readframes(f.getnframes()))

# 2. Convert to mono, 16000 Hz by averaging small groups of samples
factor = rate // 16000          # 48000 / 16000 = 3
group = channels * factor       # 2 channels x 3 = 6 samples per group
mono = array.array("h")
for i in range(0, len(data) - group + 1, group):
    mono.append(sum(data[i:i + group]) // group)

# 3. Send to the speech engine
audio = sr.AudioData(mono.tobytes(), 16000, 2)
r = sr.Recognizer()

try:
    print("Heard:", r.recognize_google(audio, language="ta-IN"))
except sr.UnknownValueError:
    print("Could not understand the audio.")
except sr.RequestError as e:
    print("Internet or service problem:", e)

text = r.recognize_google(audio, language="ta-IN")
with open("heard.txt", "w", encoding="utf-8") as f:
    f.write(text)
print("Saved to heard.txt")