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
Be friendly, empathetic, persuasive without pressure, and concise (1-3 sentences). Focus on kitchen and bathroom remodeling. Answer homeowner questions first, including objections, material comparisons, pricing uncertainty and changes of mind. Return naturally to qualification only when appropriate.
Qualify kitchen or bathroom project, approximate budget, timeline, location, and scope naturally.
Ask at most one follow-up question per turn, and only about missing details. If the homeowner asks for information, answer it before continuing qualification. Never repeat answered questions. After collecting project, budget, scope, timeline and location, summarize and offer a consultation instead of asking further qualification questions. When enough information is available,
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

FIELDS = [
    ("name", "May I have your name?"),
    ("project", "Are you planning a kitchen remodel or a bathroom remodel?"),
    ("budget", "What approximate budget are you comfortable investing in the project?"),
    ("scope", "What would you like to change — for example cabinets, countertops, flooring, shower, or the full room?"),
    ("timeline", "When would you ideally like the remodeling work to begin?"),
    ("location", "Which city is the property located in?")
]

def parse_budget(value):
    s = value.lower().replace("-", " ").strip()
    digits = re.search(r"(?<!\\d)(?:\\$\\s*)?(\\d{1,3}(?:,\\d{3})+|\\d{4,7}|\\d{2,3}\\s*k)(?!\\d)", s)
    if digits:
        raw = digits.group(1).replace(",", "").replace(" ", "")
        amount = int(raw[:-1])*1000 if raw.endswith("k") else int(raw)
        return f"${amount:,}" if amount >= 1000 else None
    tens = {"ten":10,"twenty":20,"thirty":30,"forty":40,"fifty":50,"sixty":60,"seventy":70,"eighty":80,"ninety":90}
    ones = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9}
    match = re.search(r"\\b(" + "|".join(tens) + r")(?:\\s+(" + "|".join(ones) + r"))?\\s+thousand\\b",s)
    if match:
        return f"${(tens[match.group(1)]+ones.get(match.group(2),0))*1000:,}"
    return None

def answer_field(key, value):
    s = value.strip(" .,!?:")
    low = s.lower()
    if not s:
        return None
    if key == "name":
        candidate = re.sub(r"^(?:my name is|i am|i'm|it's|this is|call me)\\s+", "", s, flags=re.I).strip()
        return candidate.title() if re.fullmatch(r"[A-Za-z][A-Za-z '-]{0,40}",candidate) and len(candidate.split()) <= 4 else None
    if key == "project":
        return "Kitchen" if "kitchen" in low else "Bathroom" if "bathroom" in low else None
    if key == "budget":
        return parse_budget(s)
    if key == "scope":
        return s[:140] if len(s) <= 140 else None
    if key == "timeline":
        return s[:80] if low in ("today","tomorrow","now","asap","immediately") or re.search(r"\\b(next|this|within|in|week|month|year|spring|summer|fall|winter|january|february|march|april|may|june|july|august|september|october|november|december)\\b|\\d",low) else None
    if key == "location":
        candidate = re.sub(r"^(?:i live in|i'm in|in|it's in|the property is in)\\s+", "", s, flags=re.I)
        return candidate.title() if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,50}",candidate) else None

def extract_lead(history, message):
    lead = {key:None for key,_ in FIELDS}
    # Reconstruct each answer from the assistant question immediately before it.
    turns = list(history) + [Message(role="user", content=message)]
    for i, turn in enumerate(turns):
        if turn.role != "user":
            continue
        previous = turns[i-1].content.lower() if i and turns[i-1].role == "assistant" else ""
        asked = next((key for key, question in FIELDS if question.lower() in previous), None)
        if not asked and i == 1 and "name" in previous:
            asked = "name"
        if asked:
            value = answer_field(asked, turn.content)
            if value:
                lead[asked] = value
        # Also recognize explicit statements without overwriting the conversational state.
        if not lead["project"] and re.search(r"\\b(kitchen|bathroom)\\b",turn.content,re.I):
            lead["project"] = answer_field("project",turn.content)
        if not lead["budget"]:
            lead["budget"] = parse_budget(turn.content)
    lead["completed"] = sum(bool(lead[key]) for key,_ in FIELDS)
    lead["next_field"] = next((key for key,_ in FIELDS if not lead[key]),None)
    return lead

def recommendation(lead):
    return (f"Thank you, {lead['name']}! For your {lead['project'].lower()} remodel in {lead['location']}, "
            f"with a budget of {lead['budget']} and a desired start of {lead['timeline']}, "
            f"I recommend a design consultation focused on {lead['scope']}. "
            "Would you like to request a consultation? I cannot confirm an appointment in this demo.")

@app.get("/api/health")
def health():
    return {"status":"ok", "male_voice_installed": any(p.exists() for p in MALE_MODELS)}

@app.post("/api/chat")
def chat(body: ChatRequest):
    start = time.perf_counter()
    lead = extract_lead(body.history[-30:], body.message)
    if lead["completed"] == len(FIELDS):
        reply = recommendation(lead)
        return {"reply":reply,"llm_ms":round((time.perf_counter()-start)*1000),"lead":lead,"recommended":True}
    next_field = lead["next_field"]
    question = dict(FIELDS)[next_field]
    # Evaluate only the acknowledgement for the actual next field.
    if next_field == "project":
        prefix = f"Nice to meet you, {lead['name']}!"
    elif next_field == "budget":
        prefix = f"Great, {lead['name']} — a {lead['project'].lower()} remodel!"
    elif next_field == "scope":
        prefix = f"Thanks, I've noted your budget of {lead['budget']}."
    elif next_field == "timeline":
        prefix = "Got it, I've noted your remodeling priorities."
    elif next_field == "location":
        prefix = "Thanks, I've noted your preferred start date."
    else:
        prefix = "I'd be happy to help."

    return {"reply":prefix+" "+question,"llm_ms":round((time.perf_counter()-start)*1000),"lead":lead}

class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1500)

@app.post("/api/speak")
def speak(body: SpeechRequest):
    model = next((p for p in MALE_MODELS if p.exists()), None)
    if not model:
        raise HTTPException(status_code=503, detail="Install voice/models/en_US-ryan-medium.onnx and its .json file")
    import uuid
    path = AUDIO_DIR / f"{uuid.uuid4().hex}.wav"
    start = time.perf_counter()
    try:
        subprocess.run([sys.executable,"-m","piper","--model",str(model),
                        "--output-file",str(path)], input=body.text,
                       text=True, check=True, capture_output=True, timeout=90)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Speech generation failed: {exc}")
    synthesis_ms = round((time.perf_counter() - start) * 1000)
    return FileResponse(path, media_type="audio/wav", filename="shekhar-ai.wav", headers={"X-TTS-Synthesis-Ms": str(synthesis_ms), "Access-Control-Expose-Headers": "X-TTS-Synthesis-Ms"})
