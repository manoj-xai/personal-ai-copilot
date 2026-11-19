import io
import os
import re
import time
import wave
import array
import queue
import threading
import tkinter as tk
from tkinter import ttk
from collections import deque
import pyaudiowpatch as pyaudio
from groq import Groq
from ai_engine import suggest_reply, add_line, clear_history, MODEL as CHAT_MODEL

client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=30)
STT_MODEL = "whisper-large-v3"

MAX_SECONDS = 30      # a very long turn is cut here and sent
MIN_SECONDS = 0.6     # shorter sounds (coughs, clicks) are ignored
MIN_VOICED = 0.5      # a turn needs at least this much real loud sound (seconds)
MIC_INDEX = None      # None = Windows default microphone, or a number from list_mics.py

LANGS = {"Auto": None, "Tamil": "ta", "English": "en"}

# Phrases Whisper often invents from silence or noise (backup filter)
HALLUCINATIONS = {"thank you", "thanks", "thank you very much", "thanks for watching",
                  "thank you for watching", "you", "bye", "bye bye", "okay", "ok",
                  "please subscribe", "the end", "நன்றி", "வணக்கம்", "நன்றி வணக்கம்"}

TRANSLATE_PROMPT = """You translate speech from a phone call into natural English.
The text was produced by automatic speech recognition (usually Tamil, possibly mixed with English
words) and may contain small recognition errors. Translate the meaning faithfully into everyday
English. Keep numbers, names and English words as they are. Do not add, explain or answer anything.
Reply with only the translation."""

utter_q = queue.Queue()    # finished turns from both sources
ui_q = queue.Queue()       # messages for the window
state = {"listening": False, "started": False, "pause": 1.5, "use_mic": True,
         "last_client": "", "situation": "", "lang_client": "Auto", "lang_you": "Auto"}


class Source:
    """One audio source: the call audio ('Client') or the microphone ('You')."""

    def __init__(self, label, level):
        self.label = label
        self.level = level          # sound louder than this counts as speech
        self.blocks = queue.Queue()
        self.channels = 2
        self.rate = 48000
        self.speaking = False
        self.peak = 0               # current loudness, shown in the window
        self.peak_hold = 0          # loudest sound since last reset (calibration)

    def callback(self, in_data, frame_count, time_info, status):
        if state["listening"] and (self.label == "Client" or state["use_mic"]):
            self.blocks.put(in_data)
        return (None, pyaudio.paContinue)

    def open(self, p, dev):
        self.channels = min(dev["maxInputChannels"], 2)
        self.rate = int(dev["defaultSampleRate"])
        self.stream = p.open(format=pyaudio.paInt16, channels=self.channels,
                             rate=self.rate, input=True, frames_per_buffer=2048,
                             input_device_index=dev["index"],
                             stream_callback=self.callback)
        self.stream.start_stream()


client_src = Source("Client", 500)
mic_src = Source("You", 1500)


def find_loopback(p):
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    speakers = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
    if not speakers["isLoopbackDevice"]:
        for lb in p.get_loopback_device_info_generator():
            if speakers["name"] in lb["name"]:
                return lb
        raise RuntimeError("No loopback device found")
    return speakers


def start_audio():
    try:
        state["pa"] = p = pyaudio.PyAudio()
    except Exception as e:
        ui_q.put(("status", f"Audio problem: {e}"))
        return
    try:
        dev = find_loopback(p)
        client_src.open(p, dev)
        msg = "Client: " + dev["name"]
    except Exception as e:
        ui_q.put(("status", f"Call audio problem: {e}"))
        return
    try:
        if MIC_INDEX is None:
            mic = p.get_default_input_device_info()
        else:
            mic = p.get_device_info_by_index(MIC_INDEX)
        mic_src.open(p, mic)
        msg += "  |  You: " + mic["name"]
    except Exception as e:
        msg += f"  |  Mic problem: {e}"
    ui_q.put(("status", "Listening - " + msg))


def block_peak(data):
    a = array.array("h", data)
    return max(max(a), -min(a)) if len(a) else 0


def segmenter(src):
    """Collects one person's turn and sends it on after a pause."""
    preroll = deque(maxlen=4)
    buf, speaking = [], False
    start = last_voice = 0.0
    voiced = 0.0            # seconds of real loud sound in this turn
    seg_peak = 0
    while True:
        try:
            data = src.blocks.get(timeout=0.25)
            t = time.time()
            peak = block_peak(data)
            src.peak = peak
            src.peak_hold = max(src.peak_hold, peak)
            if peak >= src.level:
                if not speaking:
                    speaking = True
                    start = t
                    buf = list(preroll)
                    voiced, seg_peak = 0.0, 0
                    src.speaking = True
                last_voice = t
                voiced += len(data) / (src.channels * 2 * src.rate)
                seg_peak = max(seg_peak, peak)
            if speaking:
                buf.append(data)
            else:
                preroll.append(data)
        except queue.Empty:
            src.peak = 0

        now = time.time()
        if speaking and (now - last_voice >= state["pause"]
                         or now - start >= MAX_SECONDS):
            raw = b"".join(buf)
            seconds = len(raw) / (src.channels * 2 * src.rate)
            if seconds >= MIN_SECONDS and voiced >= MIN_VOICED:
                utter_q.put((src.label, raw, src.channels, src.rate, seg_peak))
            buf, speaking = [], False
            src.speaking = False
            preroll.clear()


def to_wav_bytes(raw, channels, rate):
    data = array.array("h", raw)
    factor = max(1, rate // 16000)
    group = channels * factor
    mono = array.array("h")
    for i in range(0, len(data) - group + 1, group):
        mono.append(sum(data[i:i + group]) // group)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate // factor)
        w.writeframes(mono.tobytes())
    return buf.getvalue()


def clean_text(result):
    """Join the segments, dropping those Whisper thinks are not speech."""
    segs = getattr(result, "segments", None)
    if not segs:
        return (getattr(result, "text", "") or "").strip()
    keep = []
    for s in segs:
        def g(k):
            return s.get(k) if isinstance(s, dict) else getattr(s, k, None)
        nsp, lp = g("no_speech_prob"), g("avg_logprob")
        if nsp is not None and lp is not None and nsp > 0.6 and lp < -1.0:
            continue
        keep.append((g("text") or "").strip())
    return " ".join(t for t in keep if t).strip()


def looks_invented(text, seg_peak):
    plain = re.sub(r"[.,!?;:\"'\-]", "", text.lower()).strip()
    return plain in HALLUCINATIONS and seg_peak < 4000


def needs_translation(text):
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    non_latin = sum(1 for c in letters if ord(c) > 0x024F)
    return non_latin / len(letters) > 0.2


def translate_to_english(text, situation):
    try:
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": TRANSLATE_PROMPT},
                {"role": "user",
                 "content": f"Call context: {situation}\n\nSpeech to translate:\n{text}"},
            ],
            temperature=0.2,
            max_tokens=800,
            reasoning_effort="low",
        )
        return (resp.choices[0].message.content or "").strip() or text
    except Exception:
        return text            # if translation fails, keep the original


def transcribe_loop():
    while True:
        label, raw, channels, rate, seg_peak = utter_q.get()
        wav_bytes = to_wav_bytes(raw, channels, rate)
        lang = LANGS[state["lang_client"] if label == "Client" else state["lang_you"]]
        kwargs = dict(file=("turn.wav", wav_bytes), model=STT_MODEL,
                      response_format="verbose_json", temperature=0)
        if lang:
            kwargs["language"] = lang
        try:
            result = client.audio.transcriptions.create(**kwargs)
            original = clean_text(result)
            if not original or looks_invented(original, seg_peak):
                continue
            english = (translate_to_english(original, state["situation"])
                       if needs_translation(original) else original)
            ui_q.put(("turn", label, original, english))
        except Exception as e:
            ui_q.put(("status", f"Speech problem: {type(e).__name__}"))


def request_suggestion():
    latest = state["last_client"]
    if not latest:
        status_var.set("No client words yet")
        return
    situation = situation_box.get("1.0", "end").strip()
    status_var.set("Thinking...")

    def work():
        ui_q.put(("suggest", suggest_reply(situation, latest), latest))

    threading.Thread(target=work, daemon=True).start()


def auto_suggest():
    if client_src.speaking:        # the client is still talking
        return
    request_suggestion()


def set_text(box, text, append=False, tag=None):
    box.config(state="normal")
    if not append:
        box.delete("1.0", "end")
    box.insert("end", text, tag)
    box.see("end")
    box.config(state="disabled")


def on_turn(label, original, english):
    add_line(label, english)
    same = original.strip() == english.strip()
    if label == "Client":
        state["last_client"] = english
        set_text(other_box, english + "\n", True)
        if not same:
            set_text(other_box, original + "\n", True, "grey")
        set_text(other_box, "\n", True)
        if auto_var.get():
            root.after(700, auto_suggest)
    else:
        set_text(mine_box, original + "\n", True)
        if not same:
            set_text(mine_box, "English: " + english + "\n", True, "grey")
        set_text(mine_box, "\n", True)


def poll():
    state["situation"] = situation_box.get("1.0", "end").strip()
    try:
        while True:
            kind, *data = ui_q.get_nowait()
            if kind == "turn":
                on_turn(*data)
            elif kind == "suggest":
                short = data[1] if len(data[1]) < 90 else data[1][:90] + "..."
                set_text(say_box, f"(Replying to: {short})\n\n{data[0]}")
                status_var.set("Listening..." if state["listening"] else "Stopped")
            elif kind == "status":
                status_var.set(data[0])
    except queue.Empty:
        pass
    level_var.set(f"Level now - call: {client_src.peak}   mic: {mic_src.peak}"
                  f"   | speech counts above: call {client_src.level}, "
                  f"mic {mic_src.level}")
    root.after(200, poll)


def toggle_listening():
    if state["listening"]:
        state["listening"] = False
        start_btn.config(text="▶ Start listening")
        status_var.set("Stopped")
    else:
        state["listening"] = True
        start_btn.config(text="■ Stop listening")
        status_var.set("Starting...")
        if not state["started"]:
            state["started"] = True
            start_audio()


def calibrate_mic():
    if not state["listening"]:
        status_var.set("Click Start listening first, then Calibrate")
        return
    status_var.set("Calibrating: stay completely silent for 3 seconds...")
    mic_src.peak_hold = 0

    def finish():
        new = int(mic_src.peak_hold * 2 + 200)
        mic_scale.set(max(300, min(8000, new)))
        status_var.set(f"Mic threshold set to {mic_src.level} "
                       f"(your silent noise peaked at {mic_src.peak_hold})")

    root.after(3000, finish)


def clear_all():
    set_text(other_box, "")
    set_text(mine_box, "")
    set_text(say_box, "")
    state["last_client"] = ""
    clear_history()


root = tk.Tk()
root.title("Personal AI Copilot")
root.geometry("500x940")
root.attributes("-topmost", True)
FONT = ("Segoe UI", 10)
TAMIL_FONT = ("Nirmala UI", 10)       # shows Tamil letters clearly


def make_box(label, height, editable=False, font=FONT):
    tk.Label(root, text=label, font=("Segoe UI", 10, "bold"),
             anchor="w").pack(fill="x", padx=10, pady=(8, 0))
    box = tk.Text(root, height=height, wrap="word", font=font)
    box.pack(fill="both", expand=True, padx=10)
    box.tag_config("grey", foreground="#777777")
    if not editable:
        box.config(state="disabled")
    return box


top = tk.Frame(root)
top.pack(fill="x", padx=10, pady=8)
start_btn = tk.Button(top, text="▶ Start listening", command=toggle_listening)
start_btn.pack(side="left")
auto_var = tk.BooleanVar(value=True)
tk.Checkbutton(top, text="Auto suggest", variable=auto_var).pack(side="left", padx=4)
tk.Button(top, text="Suggest now", command=request_suggestion).pack(side="left")
tk.Button(top, text="Clear", command=clear_all).pack(side="left", padx=4)

lang_row = tk.Frame(root)
lang_row.pack(fill="x", padx=10)
for text, key in (("Client speaks:", "lang_client"), ("I speak:", "lang_you")):
    tk.Label(lang_row, text=text).pack(side="left")
    box = ttk.Combobox(lang_row, values=list(LANGS), width=8, state="readonly")
    box.set("Auto")
    box.bind("<<ComboboxSelected>>",
             lambda e, k=key, b=box: state.__setitem__(k, b.get()))
    box.pack(side="left", padx=(2, 12))

mic_row = tk.Frame(root)
mic_row.pack(fill="x", padx=10, pady=(6, 0))
mic_var = tk.BooleanVar(value=True)
tk.Checkbutton(mic_row, text="Listen to my mic (use earphones)",
               variable=mic_var,
               command=lambda: state.__setitem__("use_mic", mic_var.get())
               ).pack(side="left")
tk.Button(mic_row, text="Calibrate mic", command=calibrate_mic).pack(side="left", padx=6)

mic_scale = tk.Scale(root, from_=300, to=8000, resolution=50, orient="horizontal",
                     label="Mic threshold (must be above your silent level)",
                     command=lambda v: setattr(mic_src, "level", int(float(v))))
mic_scale.set(1500)
mic_scale.pack(fill="x", padx=10)

pause_scale = tk.Scale(root, from_=0.8, to=4.0, resolution=0.1,
                       orient="horizontal",
                       label="Wait after a speaker stops (seconds)",
                       command=lambda v: state.__setitem__("pause", float(v)))
pause_scale.set(1.5)
pause_scale.pack(fill="x", padx=10)

level_var = tk.StringVar(value="")
tk.Label(root, textvariable=level_var, anchor="w", fg="#555555",
         font=("Segoe UI", 8), wraplength=470, justify="left").pack(
    fill="x", padx=10)

other_box = make_box("Other Person (English, original below in grey)", 7, font=TAMIL_FONT)
situation_box = make_box("Situation (you can edit this)", 3, editable=True)
situation_box.insert("1.0", "I am talking to a client on a phone call.")
say_box = make_box("Say This", 5)
mine_box = make_box("My Words (what I said, English below in grey)", 6, font=TAMIL_FONT)

status_var = tk.StringVar(value="Ready")
tk.Label(root, textvariable=status_var, anchor="w", fg="gray",
         wraplength=470, justify="left").pack(fill="x", padx=10, pady=6)

for src in (client_src, mic_src):
    threading.Thread(target=segmenter, args=(src,), daemon=True).start()
threading.Thread(target=transcribe_loop, daemon=True).start()
poll()
root.mainloop()