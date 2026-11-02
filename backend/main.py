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
    ("project", "Are you planning a kitchen remodel or a bathroom remodel?"),
    ("budget", "What approximate budget are you comfortable investing in the project?"),
    ("scope", "What would you like to change — for example cabinets, countertops, flooring, shower, or the full room?"),
    ("timeline", "When would you ideally like the remodeling work to begin?"),
    ("location", "Which city is the property located in?")
]

def extract_lead(history, message):
    """Extract the latest explicit answer, including answers to guided questions."""
    user_turns = [m.content for m in history if m.role == "user"] + [message]
    combined = " ".join(user_turns)
    lower = combined.lower()
    project = "Kitchen" if "kitchen" in lower else "Bathroom" if "bathroom" in lower else None
    budget_match = re.search(r"\\$\\s?[\\d,]+(?:\\s?[kK])?|\\b\\d{2,3}\\s?k\\b", combined, re.I)
    timeline_match = re.search(r"(?:next|within|in)\\s+\\d+\\s+(?:days?|weeks?|months?)|as soon as possible|\\basap\\b|this (?:month|year|summer|winter|fall|spring)|next (?:month|year|summer|winter|fall|spring)|\\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\\b", lower)
    scope_terms = ["cabinets","countertops","flooring","tile","shower","bathtub","sink","appliances","plumbing","painting","layout","full remodel","complete renovation","everything","full kitchen","full bathroom"]
    scope = ", ".join(term for term in scope_terms if term in lower) or None
    location_match = re.search(r"(?:located in|property is in|house is in|home is in|i live in|i'm in|i am in)\\s+([A-Za-z][A-Za-z .-]{1,40})(?=[,.!?]|$)", combined, re.I)
    location = location_match.group(1).strip() if location_match else None
    lead = {"project":project,"budget":budget_match.group(0) if budget_match else None,"scope":scope,"timeline":timeline_match.group(0) if timeline_match else None,"location":location}
    # Associate a short reply with the field explicitly asked in the preceding AI turn.
    # Do not infer location from an arbitrary utterance.
    for i, turn in enumerate(history):
        if turn.role != "assistant" or i + 1 >= len(history) or history[i+1].role != "user":
            continue
        answer = history[i+1].content.strip()
        for key, question in FIELDS:
            if question.lower() in turn.content.lower() and answer:
                if key == "location" and not lead["location"]:
                    candidate = re.sub(r"^(?:i live in|i'm in|in|it's in|the property is in)\\s+", "", answer, flags=re.I).strip(" .,!") 
                    if re.fullmatch(r"[A-Za-z][A-Za-z .-]{1,45}", candidate):
                        lead["location"] = candidate
                elif key == "scope" and not lead["scope"] and len(answer) < 180:
                    lead["scope"] = answer
                elif key == "timeline" and not lead["timeline"] and len(answer) < 100:
                    lead["timeline"] = answer
                elif key == "budget" and not lead["budget"] and re.search(r"\\d", answer):
                    lead["budget"] = answer
    if not lead["budget"] and re.fullmatch(r"\s*\$?\s*\d{1,3}(?:,\d{3})+\s*|\s*\$?\s*\d{4,7}\s*", message):
        lead["budget"] = message.strip()
    lead["completed"] = sum(bool(lead[key]) for key,_ in FIELDS)
    lead["next_field"] = next((key for key,_ in FIELDS if not lead[key]), None)
    return lead

def recommendation(lead):
    scope = lead["scope"]
    return (f"Based on your {lead['project'].lower()} project in {lead['location']}, "
            f"with a budget of {lead['budget']} and a target start of {lead['timeline']}, "
            f"I recommend starting with a design consultation to review {scope}, "
            "prioritize the highest-impact improvements, and validate the budget and timeline with a local professional. "
            "Would you like to request a consultation? This demo cannot confirm an appointment.")

@app.get("/api/health")
def health():
    return {"status":"ok", "male_voice_installed": any(p.exists() for p in MALE_MODELS)}

@app.post("/api/chat")
def chat(body: ChatRequest):
    start = time.perf_counter()
    turns = body.history[-12:]
    lead = extract_lead(turns, body.message)
    # A complete qualification produces a concrete recommendation instead of another question.
    if lead["completed"] == 5:
        return {"reply":recommendation(lead), "llm_ms":round((time.perf_counter()-start)*1000), "lead":lead, "recommended":True}
    next_question = next(question for key, question in FIELDS if key == lead["next_field"])
    # Deterministic guided questions avoid Gemma repeating the initial greeting,
    # re-asking completed fields, or asking several qualification questions at once.
    acknowledgements = {
        "budget": f"Great, you're planning a {lead['project'].lower()} remodel!",
        "scope": "Thanks, that gives me a sense of your budget.",
        "timeline": "Got it, I understand what you'd like to remodel.",
        "location": "That timeline is helpful."
    }
    prefix = acknowledgements.get(lead["next_field"], "I'd be happy to help plan your remodel.")
    reply = prefix + " " + next_question
    return {"reply": reply, "llm_ms": round((time.perf_counter()-start)*1000),
            "lead": lead}

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
