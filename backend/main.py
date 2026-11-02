"""Local Wonderly Voice AI API. No paid cloud APIs."""
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
VOICE_DIR = ROOT / "voice"
MODELS = VOICE_DIR / "models"
AUDIO_DIR = ROOT / ".audio"
AUDIO_DIR.mkdir(exist_ok=True)
MALE_MODELS = [MODELS / "en_US-ryan-medium.onnx", MODELS / "en_US-ryan-high.onnx"]
SYSTEM = """You are Shekhar AI, a virtual home-remodeling sales consultant for a Wonderly demo.
Be friendly, empathetic, persuasive without pressure, and concise (1-3 sentences).
Qualify kitchen or bathroom project, approximate budget, timeline, location, and scope naturally.
Ask only one follow-up question per turn. When enough information is available,
offer to REQUEST a consultation, never claim a booking is confirmed.
Do not pretend to be a human or the real Shekhar. Do not invent pricing, discounts,
contractors, project guarantees, or real appointment availability."""
app = FastAPI(title="Wonderly Voice AI")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173","http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=3000)
    history: list[Message] = Field(default_factory=list, max_length=30)

def extract_lead(history, message):
    combined = " ".join([m.content for m in history if m.role == "user"] + [message])
    lower = combined.lower()
    project = "Kitchen" if "kitchen" in lower else "Bathroom" if "bathroom" in lower else None
    budget_match = re.search(r"\$\s?[\d,]+(?:\s?[kK])?", combined)
    timeline_match = re.search(r"(?:next|within|in)\s+\d+\s+(?:weeks?|months?)|as soon as possible|this (?:month|year|summer|winter|fall|spring)", lower)
    return {"project": project, "budget": budget_match.group(0) if budget_match else None,
            "timeline": timeline_match.group(0) if timeline_match else None,
            "location": None, "consultation": "Not requested"}

@app.get("/api/health")
def health():
    return {"status":"ok", "male_voice_installed": any(p.exists() for p in MALE_MODELS)}

@app.post("/api/chat")
def chat(body: ChatRequest):
    start = time.perf_counter()
    turns = body.history[-12:]
    conversation = "\n".join(f"{'Homeowner' if m.role == 'user' else 'Shekhar AI'}: {m.content}" for m in turns)
    prompt = f"{conversation}\nHomeowner: {body.message}\nShekhar AI:"
    data = json.dumps({"model":"gemma3:4b","system":SYSTEM,"prompt":prompt,
                       "stream":False,"options":{"num_predict":120,"temperature":0.5}}).encode()
    try:
        req = urllib.request.Request("http://localhost:11434/api/generate", data=data,
                                     headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=120) as response:
            answer = json.load(response)["response"].strip()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Local Ollama unavailable: {exc}")
    return {"reply":answer, "llm_ms":round((time.perf_counter()-start)*1000),
            "lead":extract_lead(turns,body.message)}

class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1500)

@app.post("/api/speak")
def speak(body: SpeechRequest):
    model = next((p for p in MALE_MODELS if p.exists()), None)
    if not model:
        raise HTTPException(status_code=503, detail="Install voice/models/en_US-ryan-medium.onnx and its .json file")
    import uuid
    path = AUDIO_DIR / f"{uuid.uuid4().hex}.wav"
    try:
        subprocess.run([sys.executable,"-m","piper","--model",str(model),
                        "--output-file",str(path)], input=body.text,
                       text=True, check=True, capture_output=True, timeout=90)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Speech generation failed: {exc}")
    return FileResponse(path, media_type="audio/wav", filename="shekhar-ai.wav")
