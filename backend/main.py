"""Local Wonderly Voice AI API. No paid cloud APIs."""
import json
import io
import wave
import threading
from collections import OrderedDict
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
from piper.config import SynthesisConfig

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
    ("location", "Which city is the property located in?"),
    ("size", "About how big is the room? An estimate in feet or square feet is fine, or say not sure."),
    ("priority", "What matters most to you: modern style, more storage, better functionality, or something else?")
]

def parse_budget(value):
    s = value.lower().replace("-", " ").strip()
    # Speech recognition may return "$50,000", "50 000", "50000", or "fifty thousand".
    digits = re.search(r"(?<!\d)(?:\$\s*)?(\d{1,3}(?:[ ,]\d{3})+|\d{4,7}|\d{1,3}\s*k)(?!\d)", s)
    if digits:
        raw = re.sub(r"[ ,]", "", digits.group(1))
        amount = int(raw[:-1])*1000 if raw.endswith("k") else int(raw)
        return f"${amount:,}" if amount >= 1000 else None
    tens = {"ten":10,"twenty":20,"thirty":30,"forty":40,"fifty":50,"sixty":60,"seventy":70,"eighty":80,"ninety":90}
    ones = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9}
    match = re.search(r"\b(" + "|".join(tens) + r")(?:\s+(" + "|".join(ones) + r"))?\s+thousand\b",s)
    if match:
        return f"${(tens[match.group(1)]+ones.get(match.group(2),0))*1000:,}"
    return None

def answer_field(key, value):
    s = value.strip(" .,!?:")
    low = s.lower()
    if not s:
        return None
    if key == "name":
        # Recognize natural first-turn introductions, including speech punctuation.
        value = re.sub(r"^(?:hello|hi|hey)[,!. ]+", "", s, flags=re.I)
        candidate = re.sub(r"^(?:my name is|i am|i'm|it's|this is|call me|my name's|name is)\s+", "", value, flags=re.I).strip()
        return candidate.title() if re.fullmatch(r"[A-Za-z][A-Za-z '-]{0,40}",candidate) and len(candidate.split()) <= 4 else None
    if key == "project":
        return "Kitchen" if "kitchen" in low else "Bathroom" if "bathroom" in low else None
    if key == "budget":
        return parse_budget(s)
    if key == "scope":
        return s[:140] if len(s) <= 140 else None
    if key == "timeline":
        return s[:80] if low in ("today","tomorrow","now","asap","immediately") or re.search(r"\b(next|this|within|in|week|month|year|spring|summer|fall|winter|january|february|march|april|may|june|july|august|september|october|november|december)\b|\d",low) else None
    if key == "size":
        if low in ("not sure", "unsure", "dont know", "don\'t know", "unknown", "skip", "no idea"):
            return "Not sure"
        return s[:70] if re.search(r"\d|feet|foot|square|sq\.?\s*ft",low) else None
    if key == "priority":
        return s[:100] if len(s) > 2 else None
    if key == "location":
        candidate = re.sub(r"^(?:i live in|i'm in|in|it's in|the property is in)\s+", "", s, flags=re.I)
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
        if not asked and "sorry, i didn't catch that clearly" in previous:
            for earlier in reversed(turns[:i-1]):
                if earlier.role == "assistant":
                    asked = next((key for key, question in FIELDS if question.lower() in earlier.content.lower()), None)
                    if asked:
                        break
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
    project = lead["project"].lower()
    scope = lead["scope"].lower()
    if project == "kitchen":
        suggestion = ("Start with cabinet refinishing or refacing, updated hardware, and targeted lighting. "
                      "Compare countertop options only after confirming measurements and labor costs."
                      if "cabinet" in scope else
                      "Start with cabinet finishes, lighting, and the most visible surfaces. "
                      "Avoid moving walls or plumbing until a contractor confirms the budget.")
    else:
        suggestion = ("Focus on fixtures, flooring, vanity finishes, and lighting. "
                      "Have a professional check waterproofing and plumbing before finalizing the scope.")
    return (f"Thanks, {lead['name']}! For your {project} remodel in {lead['location']}, "
            f"with a {lead['budget']} budget and a {lead['timeline']} start, "
            f"I suggest this direction: {suggestion} "
            "I've also displayed a design concept on the right. These are ideas, not a price quote. "
            "Would you like me to prepare a design consultation request?")

def contact_from_text(message):
    raw = message.strip()
    email = re.search(r"[A-Za-z0-9._%+-]+\s*@\s*[A-Za-z0-9.-]+\s*\.\s*[A-Za-z]{2,}", raw)
    if email:
        return "email", re.sub(r"\s+", "", email.group(0)).lower()
    # Speech transcription may say "at" and "dot".
    spoken = re.sub(r"\s+at\s+", "@", raw, flags=re.I)
    spoken = re.sub(r"\s+dot\s+", ".", spoken, flags=re.I)
    spoken = re.sub(r"\s+", "", spoken)
    email = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", spoken)
    if email:
        return "email", email.group(0).lower()
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10 or (len(digits) == 11 and digits.startswith("1")):
        return "phone", digits
    return None, None

def consultation_reply(history, message, lead):
    if not history:
        return None, None, None
    previous = history[-1].content.lower() if history[-1].role == "assistant" else ""
    lower = message.strip().lower().rstrip(".!? ")
    recent = [m.content.lower() for m in history[-16:] if m.role == "assistant"]
    already_finished = any("consultation summary is ready" in m or "thanks for chatting" in m for m in recent)
    if already_finished:
        return ("Thank you for chatting with Shekhar AI. Have a wonderful day!", None, "closed")
    if "consultation request?" in previous or "design consultation request?" in previous:
        if lower in ("no", "no thanks", "no thank you", "not now", "maybe later", "nope"):
            return (f"No problem, {lead['name']}! I hope these remodeling ideas were useful. "
                    "Thank you for chatting, and have a wonderful day!", None, "declined")
        if lower in ("yes", "yes please", "sure", "okay", "ok", "absolutely", "please do", "sounds good", "yep"):
            return (f"Wonderful, {lead['name']}! What's the best email address or phone number "
                    "for a remodeling specialist to contact you?", None, "collecting")
    waiting_for_contact = any(
        "email address or phone number" in m or "valid email or phone" in m
        or "couldn't recognize that contact" in m for m in recent
    )
    if waiting_for_contact:
        kind, contact = contact_from_text(message)
        if kind:
            return (f"Thank you, {lead['name']}! Your consultation summary is ready. "
                    "You can review it and use Send Email or Send Text on the right to submit it. "
                    "Once it's actually sent to a remodeling team, they can follow up with you. "
                    "Nothing has been sent automatically. It was a pleasure speaking with you!",
                    {"type":kind,"value":contact}, "ready")
        return ("Sorry, I couldn't recognize that contact detail. "
                "Could you repeat a valid email or phone number, or type it below?", None, "collecting")
    return None, None, None

@app.get("/api/health")
def health():
    return {"status":"ok", "male_voice_installed": any(p.exists() for p in MALE_MODELS)}

@app.post("/api/chat")
def chat(body: ChatRequest):
    start = time.perf_counter()
    lead = extract_lead(body.history[-30:], body.message)
    followup, contact, stage = consultation_reply(body.history, body.message, lead) if lead["completed"] == len(FIELDS) else (None, None, None)
    if followup:
        return {"reply":followup,"llm_ms":round((time.perf_counter()-start)*1000),"lead":lead,"contact":contact,"stage":stage,"recommended":True}
    if lead["completed"] == len(FIELDS):
        reply = recommendation(lead)
        return {"reply":reply,"llm_ms":round((time.perf_counter()-start)*1000),"lead":lead,"recommended":True}
    next_field = lead["next_field"]
    question = dict(FIELDS)[next_field]
    # Evaluate only the acknowledgement for the actual next field.
    # If an answer cannot be parsed, ask for clarification instead of repeating
    # the previous acknowledgement or silently accepting an incomplete amount.
    if body.history and body.history[-1].role == "assistant":
        last_question = next((key for key, q in FIELDS if q.lower() in body.history[-1].content.lower()), None)
        if last_question and last_question == next_field:
            example = " For example, fifty thousand dollars." if next_field == "budget" else ""
            return {"reply":f"Sorry, I didn't catch that clearly. Could you please repeat it?{example}",
                    "llm_ms":round((time.perf_counter()-start)*1000),"lead":lead}
    if next_field == "project":
        prefix = f"Nice to meet you, {lead['name']}!"
    elif next_field == "budget":
        prefix = "Sounds good!"
    elif next_field == "scope":
        prefix = f"Thanks, I've noted a budget of {lead['budget']}."
    elif next_field == "timeline":
        prefix = "Got it."
    elif next_field == "location":
        prefix = "That helps, thanks."
    elif next_field == "size":
        prefix = "Great, just two quick details left."
    elif next_field == "priority":
        prefix = "Perfect, one last question."
    else:
        prefix = "I'd be happy to help."

    return {"reply":prefix+" "+question,"llm_ms":round((time.perf_counter()-start)*1000),"lead":lead}

# Keep the voice model resident; reuse generated audio for repeated prompts.
_VOICE = None
_VOICE_ERROR = None
_VOICE_LOCK = threading.Lock()
_CACHE_LOCK = threading.Lock()
_AUDIO_CACHE = OrderedDict()
_CACHE_LIMIT = 256
WELCOME_TEXT = "Hi! I'm Shekhar AI, your virtual remodeling consultant. May I have your name?"
PREWARM_TEXTS = [WELCOME_TEXT, "Nice to meet you!", "Sounds good!", "Got it."] + [question for _, question in FIELDS]

def cache_key(text):
    return " ".join(text.split())

def get_voice():
    global _VOICE, _VOICE_ERROR
    if _VOICE is not None:
        return _VOICE
    with _VOICE_LOCK:
        if _VOICE is None:
            model = next((p for p in MALE_MODELS if p.exists()), None)
            if model is None:
                raise RuntimeError("Piper voice model is not installed")
            try:
                from piper.voice import PiperVoice
                _VOICE = PiperVoice.load(str(model))
                _VOICE_ERROR = None
            except Exception as exc:
                _VOICE_ERROR = str(exc)
                raise
    return _VOICE

def synthesize_audio(text):
    voice = get_voice()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file, syn_config=SynthesisConfig(length_scale=1.12))
    return buffer.getvalue()

@app.on_event("startup")
def preload_voice():
    # Warm the model once on server startup, before the first conversation.
    try:
        get_voice()
        def prime():
            for phrase in PREWARM_TEXTS:
                try:
                    key = cache_key(phrase)
                    with _VOICE_LOCK:
                        audio = synthesize_audio(phrase)
                    with _CACHE_LOCK:
                        _AUDIO_CACHE[key] = audio
                        _AUDIO_CACHE.move_to_end(key)
                except Exception as exc:
                    print(f"Piper audio prewarm failed: {exc}", file=sys.stderr)
        threading.Thread(target=prime, daemon=True).start()
    except Exception as exc:
        print(f"Piper preload failed; speech will report the error: {exc}", file=sys.stderr)

class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1500)

@app.post("/api/speak")
def speak(body: SpeechRequest):
    from fastapi.responses import Response
    text = cache_key(body.text)
    if not text:
        raise HTTPException(status_code=422, detail="Speech text cannot be blank")
    start = time.perf_counter()
    with _CACHE_LOCK:
        cached = _AUDIO_CACHE.get(text)
        if cached is not None:
            _AUDIO_CACHE.move_to_end(text)
    if cached is not None:
        return Response(cached, media_type="audio/wav",
                        headers={"X-TTS-Synthesis-Ms": "0", "X-TTS-Cache": "HIT",
                                 "Access-Control-Expose-Headers": "X-TTS-Synthesis-Ms, X-TTS-Cache"})
    try:
        # Serialize model inference: PiperVoice is shared across requests.
        with _VOICE_LOCK:
            # get_voice() acquires this lock during first load; startup preloads it.
            if _VOICE is None:
                raise RuntimeError(_VOICE_ERROR or "Piper model was not loaded")
            audio_bytes = synthesize_audio(text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Speech generation failed: {exc}")
    synthesis_ms = round((time.perf_counter() - start) * 1000)
    with _CACHE_LOCK:
        _AUDIO_CACHE[text] = audio_bytes
        _AUDIO_CACHE.move_to_end(text)
        while len(_AUDIO_CACHE) > _CACHE_LIMIT:
            _AUDIO_CACHE.popitem(last=False)
    return Response(audio_bytes, media_type="audio/wav",
                    headers={"X-TTS-Synthesis-Ms": str(synthesis_ms), "X-TTS-Cache": "MISS",
                             "Access-Control-Expose-Headers": "X-TTS-Synthesis-Ms, X-TTS-Cache"})
