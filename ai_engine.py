import json
import os
from groq import Groq

client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=20)
MODEL = "openai/gpt-oss-120b"

SYSTEM = """You are a live conversation copilot helping the user ("You") during a call with a client.
You receive the user's situation (background only), the earlier conversation, and the Client's latest words.
Lines start with "Client:" or "You:". The text is auto-transcribed and translated, so small errors are possible.
Base your reply on the Client's LATEST words. If the client has changed the subject, answer the new
subject and ignore the old topic. Earlier lines are background only. Do not repeat what the user already said.
Reply ONLY with JSON containing one key:
"say_this": one or two short, natural sentences the user can say next, in simple polite English."""

_history = []   # lines such as "Client: ..." and "You: ..."


def add_line(speaker, text):
    _history.append(f"{speaker}: {text}")
    del _history[:-8]           # keep the last 8 lines


def clear_history():
    _history.clear()


def suggest_reply(situation, latest=None):
    if latest is None:
        clients = [l for l in _history if l.startswith("Client:")]
        latest = clients[-1][len("Client:"):].strip() if clients else ""
    earlier = "\n".join(_history) or "(nothing yet)"
    prompt = (f"Situation (background): {situation}\n\n"
              f"Conversation so far:\n{earlier}\n\n"
              f"Client's LATEST words: {latest}")
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.5,
            max_tokens=600,
            reasoning_effort="low",
        )
        return json.loads(resp.choices[0].message.content)["say_this"]
    except Exception as e:
        return (f"(AI not available: {type(e).__name__}) "
                "Could you tell me a little more about what you need?")


if __name__ == "__main__":
    add_line("Client", "Your price is a bit high for me.")
    print(suggest_reply("I sell website design."))
    add_line("Client", "Also, when can you start?")
    print(suggest_reply("I sell website design."))