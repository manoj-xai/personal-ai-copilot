# Personal AI Conversation Copilot

A real-time desktop assistant for live calls. It listens to the other person, understands Tamil or English speech, shows it in English, and suggests what you could say next.

> Status: working prototype (Windows). Built in Python with Tkinter and the Groq API.

## What it does

- **Listens to a call on your laptop.** It records the audio your laptop plays (the other person's voice) with Windows loopback capture, and also your microphone, so the two sides stay separate.
- **Waits for people to finish speaking.** It detects pauses and treats each speaker's turn as one unit, so suggestions never arrive mid-sentence.
- **Understands Tamil and English.** Speech is transcribed in the spoken language, then translated to natural English with a language model. The original text is shown beside the English.
- **Suggests what to say.** The *Say This* box gives one or two polite sentences that answer the other person's latest words and follow topic changes.
- **Shows what you said.** The *My Words* box lists your own speech from the microphone.
- **Handles noisy microphones.** A calibration button and a threshold slider stop background noise from being treated as speech, and a filter removes phrases Whisper invents from silence.

## The window

| Box | Shows |
|---|---|
| Other Person | The other person's words in English, with the original below in grey |
| Situation | A note you type about the call (who they are, what you offer) |
| Say This | The suggested next sentence |
| My Words | What you said, with the English version below in grey |

## How it works

```
Call audio (loopback) --\
                         +--> turn detection (wait for a pause)
Your microphone ---------/            |
                                      v
                     Groq Whisper large-v3 (speech to text)
                                      |
                     Groq chat model (Tamil -> English)
                                      |
                     Groq chat model (suggest the next sentence)
                                      |
                              Tkinter window
```

## Tech stack

- Python 3, Tkinter
- PyAudioWPatch (Windows WASAPI loopback and microphone capture)
- Groq API: `whisper-large-v3` for speech recognition, `openai/gpt-oss-120b` for translation and suggestions

Model names change over time. Run `experiments/list_models.py` to see which models your key can use.

## Setup (Windows)

1. Install Python 3.10 or newer.
2. Install the libraries:
   ```
   python -m pip install -r requirements.txt
   ```
3. Create a free API key at https://console.groq.com/keys and save it as an environment variable:
   ```
   setx GROQ_API_KEY "your_key_here"
   ```
   Close the terminal and open a new one. Never put the key in the code or commit it.
4. Run:
   ```
   python copilot_app.py
   ```

## How to use it

1. Wear earphones, so your microphone does not pick up the other person's voice.
2. Start a call on the laptop (WhatsApp Desktop, Meet, Zoom, or Phone Link).
3. Click **Start listening**, then stay silent and click **Calibrate mic**.
4. Set **Client speaks** and **I speak** to Tamil, English, or Auto. Choosing the real language gives the best accuracy.
5. Edit the **Situation** box, then talk. Use **Suggest now** if you turn **Auto suggest** off.

## Limitations

- Windows only.
- About 4 to 6 seconds of delay after someone stops speaking.
- Tamil recognition is good but not perfect, especially with fast speech, noise, or heavy Tamil-English mixing.
- In a conference call all remote voices arrive as one mixed stream, so the app cannot tell remote speakers apart yet.
- Needs an internet connection and uses the Groq free-tier limits.
- Suggestions are hints, not scripts.

## Privacy and ethics

Audio is sent to Groq's servers for transcription. Tell the other person when an AI assistant is in use, where the law or good practice requires it. Keep your API key private.

## Roadmap

- End-of-call summary and a saved transcript
- Separate labels for each remote speaker in conference calls
- A neater floating window design
- Support for more Indian languages

## Project structure

```
copilot_app.py     The main app: window, audio capture, speech to text, suggestions
ai_engine.py       The AI brain: keeps the conversation and writes the suggestion
experiments/       Small scripts used while testing audio capture and speech engines
requirements.txt   Python libraries
```

## Author

Manojkumar R, AI and ML undergraduate.
GitHub: https://github.com/manoj-xai
LinkedIn: https://www.linkedin.com/in/manojkumar-r-tech/
