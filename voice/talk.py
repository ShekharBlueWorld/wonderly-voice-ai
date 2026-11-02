"""Wonderly Voice AI: local Gemma 3 + Piper female voice proof of concept."""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

VOICE_DIR = Path(__file__).resolve().parent
MODELS_DIR = VOICE_DIR / "models"
VOICES = [
    MODELS_DIR / "en_US-hfc_female-medium.onnx",
    MODELS_DIR / "en_US-amy-medium.onnx",
]

SYSTEM_PROMPT = (
    "You are Ava, Wonderly's friendly home remodeling sales assistant. "
    "Help homeowners explore kitchen and bathroom remodeling. "
    "Speak warmly and naturally, in two or three short sentences. "
    "Ask only one useful follow-up question at a time. "
    "Do not invent prices, appointment availability, or project guarantees."
)

def generate_reply(question, history):
    prompt = "\n".join(
        [f"{role}: {message}" for role, message in history[-8:]]
        + [f"Homeowner: {question}", "Ava:"]
    )
    payload = json.dumps({
        "model": "gemma3:4b",
        "system": SYSTEM_PROMPT,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": 110, "temperature": 0.5},
    }).encode("utf-8")
    request = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)["response"].strip()


def speak(reply, model):
    output = VOICE_DIR / "response.wav"
    subprocess.run(
        [sys.executable, "-m", "piper", "--model", str(model),
         "--output-file", str(output)],
        input=reply, text=True, check=True,
    )
    subprocess.run(["afplay", str(output)], check=True)


def main():
    model = next((candidate for candidate in VOICES if candidate.is_file()), None)
    if model is None:
        sys.exit("No female Piper model found under voice/models/.")
    print("Wonderly Voice AI — Ava")
    print(f"Voice: {model.name}")
    print("Type 'exit' to quit. Make sure Ollama is running.")
    history = []
    while True:
        try:
            question = input("\nHomeowner: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if question.lower() in {"exit", "quit"}:
            break
        if not question:
            continue
        try:
            start = time.perf_counter()
            reply = generate_reply(question, history)
            llm_seconds = time.perf_counter() - start
            print(f"\nAva: {reply}")
            history.extend([("Homeowner", question), ("Ava", reply)])
            start_tts = time.perf_counter()
            speak(reply, model)
            print(
                f"LLM: {llm_seconds:.2f}s | "
                f"TTS + playback: {time.perf_counter() - start_tts:.2f}s"
            )
        except urllib.error.URLError as exc:
            print(f"Ollama connection error: {exc}. Start Ollama and try again.")
        except subprocess.CalledProcessError as exc:
            print(f"Voice playback error: {exc}")
        except Exception as exc:
            print(f"Error: {exc}")


if __name__ == "__main__":
    main()
