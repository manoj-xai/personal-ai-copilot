import os
import sys
from groq import Groq

sys.stdout.reconfigure(encoding="utf-8")

client = Groq(api_key=os.environ["GROQ_API_KEY"])

with open("loopback_test.wav", "rb") as f:
    result = client.audio.transcriptions.create(
        file=("loopback_test.wav", f.read()),
        model="whisper-large-v3",
        language="ta",
        response_format="json",
    )

print(result.text)
