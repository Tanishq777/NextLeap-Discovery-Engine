"""
api/index.py - FastAPI Serverless Endpoint for Groww SIP Retention AI Assistant on Vercel.
Serves static frontend assets (index.html, styles.css, app.js, data) and AI streaming endpoints (/api/chat, /api/health).
"""
import json, os, sys
from pathlib import Path
from typing import List, Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
    from pydantic import BaseModel
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn[standard]", "pydantic"])
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
    from pydantic import BaseModel

try:
    from groq import Groq
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "groq"])
    from groq import Groq

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LLM_PRIMARY  = os.getenv("CLASSIFIER_MODEL", "qwen/qwen3.8-27b")
LLM_FALLBACK = "openai/gpt-oss-120b"

app = FastAPI(title="Groww SIP Retention Discovery Engine & AI Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def find_file(rel_path: str) -> Optional[Path]:
    filename = Path(rel_path).name
    candidates = [
        Path(__file__).resolve().parent / rel_path,
        Path(__file__).resolve().parent / filename,
        Path(__file__).resolve().parent / "data" / filename,
        Path(__file__).resolve().parent.parent / rel_path,
        Path(__file__).resolve().parent.parent / filename,
        Path.cwd() / rel_path,
        Path.cwd() / filename,
        Path(rel_path),
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    for base in [Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent, Path.cwd()]:
        try:
            for root, _, files in os.walk(base):
                if filename in files:
                    return Path(root) / filename
        except Exception:
            pass
    return None

_BUNDLE: dict = {}
_DATA_CTX: str = ""

def load_bundle():
    global _BUNDLE, _DATA_CTX
    bundle_path = find_file("data/bundle.json") or find_file("bundle.json")
    if not bundle_path:
        _DATA_CTX = "No data bundle available. Answer general questions regarding Groww SIP retention."
        return

    try:
        with open(bundle_path, encoding="utf-8") as f:
            _BUNDLE = json.load(f)
        items  = _BUNDLE.get("items", [])
        opps   = _BUNDLE.get("opportunity_areas", [])
        report = _BUNDLE.get("synthesis_report", "")
        signal_lines = []
        for it in items[:60]:
            src   = it.get("source", "")
            txt   = (it.get("text") or "")[:280]
            stage = it.get("lifecycle_stage") or ""
            signals = ", ".join(it.get("behavioral_signals") or [])
            areas = ", ".join(it.get("assigned_areas") or [])
            risk  = it.get("retention_risk") or ""
            signal_lines.append(f'[{src}] "{txt}" | Stage: {stage} | Signals: {signals} | Risk: {risk} | Area: {areas}')
        opp_lines = []
        for o in opps:
            name = o.get("Opportunity Area") or o.get("name", "")
            desc = (o.get("Description") or o.get("description", ""))[:180]
            vol  = o.get("Evidence Volume") or o.get("evidence_count", "?")
            sev  = o.get("Severity Score") or o.get("severity_score", "?")
            opp_lines.append(f"- {name} (Vol:{vol}, Sev:{sev}/5.0) -- {desc}")
        _DATA_CTX = (
            f"=== GROWW SIP RETENTION DISCOVERY DATA ===\n"
            f"Dataset: {len(items)} verified investor signals across 6 channels (Play Store, App Store, Reddit, YouTube, Help Forums, Web)\n"
            f"Goal: Increase percentage of first-time mutual fund investors retaining an active SIP past 12 months.\n\n"
            f"OPPORTUNITY AREAS:\n" + "\n".join(opp_lines[:10]) + "\n\n"
            f"VERBATIM SIGNALS (sample {min(60, len(items))}):\n" + "\n".join(signal_lines) + "\n\n"
            f"EXECUTIVE SYNTHESIS:\n{report[:1400] if report else 'N/A'}\n"
            f"=== END DATA ==="
        )
    except Exception as e:
        _DATA_CTX = f"Error reading bundle: {e}"

load_bundle()

def system_prompt():
    return (
        "You are the **Groww SIP Retention Discovery Assistant** -- an expert Growth Product Manager and UX analyst embedded in Groww's research intelligence dashboard.\n\n"
        "Your mission is to help Groww product managers understand why first-time mutual fund investors stop or pause their SIP within the first 12 months, and identify concrete product interventions to improve retention.\n\n"
        "Rules:\n"
        "- For dataset questions: cite specific numbers, percentages, investor signals, and quotes from the data context.\n"
        "- Frame advice through the lens of fintech investor psychology: loss aversion, rupee cost averaging, goal anchoring, payment friction, and expectations calibration.\n"
        "- Always use clean markdown formatting: bold headers, comparison tables, bullet points, and blockquotes.\n"
        "- Be professional, strategic, and data-grounded.\n\n"
        + _DATA_CTX
    )

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]

def get_active_models(client: Groq) -> List[str]:
    preferred_order = [
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "allam-2-7b",
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
    ]
    try:
        remote_models = client.models.list()
        active_ids = {m.id for m in remote_models.data}
        matched = [m for m in preferred_order if m in active_ids]
        if matched:
            return matched
        return list(active_ids)[:4]
    except Exception:
        return ["qwen/qwen3.8-27b", "openai/gpt-oss-120b"]

async def handle_chat_stream(req: ChatRequest):
    api_key = os.getenv("GROQ_API_KEY", GROQ_API_KEY)
    if not api_key:
        import re
        from pipeline.chat_engine import answer_research_question
        user_query = req.messages[-1].content if req.messages else "SIP Retention Inquiry"
        ans_data = answer_research_question(user_query)
        answer_text = ans_data.get("answer", "")

        def gen_empirical():
            words = re.findall(r"\S+|\n", answer_text)
            for w in words:
                sep = "" if w.endswith("\n") else " "
                yield f"data: {json.dumps({'t': w + sep})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"

        return StreamingResponse(
            gen_empirical(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
            },
        )

    client = Groq(api_key=api_key)
    msgs = [{"role": "system", "content": system_prompt()}]
    msgs += [{"role": m.role, "content": m.content} for m in req.messages]

    models_to_try = get_active_models(client)

    def gen():
        last_err = ""
        for model in models_to_try:
            try:
                stream = client.chat.completions.create(
                    model=model, messages=msgs, temperature=0.7,
                    max_tokens=850, stream=True
                )
                stream_started = False
                for chunk in stream:
                    d = chunk.choices[0].delta
                    if d and d.content:
                        stream_started = True
                        yield f"data: {json.dumps({'t': d.content})}\n\n"
                if stream_started:
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    return
            except Exception as e:
                last_err = str(e)
                continue
        yield f"data: {json.dumps({'t': f'Error streaming response: {last_err}'})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    return await handle_chat_stream(req)

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "domain": "groww_sip_retention",
        "has_groq": bool(os.getenv("GROQ_API_KEY", GROQ_API_KEY)),
        "bundle_loaded": bool(_BUNDLE),
        "items_count": len(_BUNDLE.get("items", [])),
    }

@app.get("/api/bundle.json")
@app.get("/api/data/bundle.json")
def serve_api_bundle():
    p = find_file("data/bundle.json") or find_file("bundle.json")
    if p and p.is_file():
        return FileResponse(p, media_type="application/json")
    raise HTTPException(404, "Bundle not found")

@app.get("/data/{filename}")
def serve_data_file(filename: str):
    p = find_file(f"data/{filename}") or find_file(filename)
    if p and p.is_file():
        return FileResponse(p, media_type="application/json")
    raise HTTPException(404, f"Data file {filename} not found")

@app.get("/")
def serve_index():
    p = find_file("index.html")
    if p and p.is_file():
        return HTMLResponse(p.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Groww SIP Retention Discovery Engine API</h1><p>Visit /api/health</p>")

@app.get("/{filename:path}")
@app.head("/{filename:path}")
def serve_static(filename: str):
    if filename.startswith("api/"):
        raise HTTPException(404, "API route not found")
    p = find_file(filename)
    if p and p.is_file():
        mt = "text/html"
        if filename.endswith(".js"):
            mt = "application/javascript"
        elif filename.endswith(".css"):
            mt = "text/css"
        elif filename.endswith(".json"):
            mt = "application/json"
        elif filename.endswith(".svg"):
            mt = "image/svg+xml"
        elif filename.endswith(".png"):
            mt = "image/png"
        elif filename.endswith(".webp"):
            mt = "image/webp"
        elif filename.endswith(".ico"):
            mt = "image/x-icon"
        return FileResponse(p, media_type=mt)
    raise HTTPException(404, f"File {filename} not found")
