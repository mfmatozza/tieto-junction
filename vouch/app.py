"""Dashboard server. Run: python -m uvicorn vouch.app:app --host 0.0.0.0 --port 8000

State = an append-only list of review events (vote, ask, signoff). Persisted to data/events.jsonl, and to Aiven
PostgreSQL (review_events) when AIVEN_PG_URL is set. Presence lives in memory with a 15 s timeout.
"""
import asyncio
import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import vouch  # noqa: F401  (loads .env)

ROOT = Path(__file__).resolve().parents[1]
PACKS, DATA = ROOT / "packs", ROOT / "data"
LOG = DATA / "events.jsonl"
app = FastAPI()
subscribers: dict[str, set[asyncio.Queue]] = {}
presence: dict[str, dict[str, tuple[str, float]]] = {}  # pr -> user -> (step, seen_at)

# ---------------------------------------------------------------- storage

_pg = None


def pg():
    global _pg
    if _pg is None and os.environ.get("AIVEN_PG_URL"):
        import psycopg
        _pg = psycopg.connect(os.environ["AIVEN_PG_URL"], autocommit=True)
    return _pg


def load_events() -> list[dict]:
    if not LOG.exists():
        return []
    return [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]


EVENTS = load_events()


def record(ev: dict) -> None:
    ev["at"] = time.time()
    EVENTS.append(ev)
    DATA.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev) + "\n")
    try:
        if pg():
            pg().execute("INSERT INTO review_events (event_type, aggregate_type, payload) VALUES (%s, 'pull_request', %s)",
                         (ev["type"], json.dumps(ev)))
    except Exception:
        pass  # the local log is the fallback; a DB hiccup must not lose a reviewer's vote
    notify(ev["pr"])


def notify(pr: str) -> None:
    for q in subscribers.get(pr, set()):
        q.put_nowait("changed")


def pack(pr: str) -> dict:
    f = PACKS / f"{pr}.json"
    if not f.exists():
        raise HTTPException(404, "No review for this PR yet")
    return json.loads(f.read_text(encoding="utf-8"))


def state(pr: str, steps: list[dict]) -> dict:
    votes: dict[str, dict[str, dict]] = {}  # step -> user -> latest vote
    asks, signoff = [], None
    for ev in EVENTS:
        if ev["pr"] != pr:
            continue
        if ev["type"] == "vote":
            votes.setdefault(ev["step"], {})[ev["user"]] = ev
        elif ev["type"] == "ask":
            asks.append(ev)
        elif ev["type"] == "signoff":
            signoff = ev
        elif ev["type"] == "reset":
            votes, asks, signoff = {}, [], None
    now = time.time()
    here = {u: s for u, (s, t) in presence.get(pr, {}).items() if now - t < 15}
    status = {}
    for s in steps:
        vs = list(votes.get(s["id"], {}).values())
        status[s["id"]] = ("problem" if any(v["vote"] == "problem" for v in vs) else
                           "ok" if any(v["vote"] == "ok" for v in vs) else
                           "question" if vs else "open")
    review_steps = [s for s in steps if s["kind"] != "sign"]
    done = sum(status[s["id"]] == "ok" for s in review_steps)
    return {"votes": votes, "asks": asks, "signoff": signoff, "presence": here, "status": status,
            "done": done, "total": len(review_steps), "ready": done == len(review_steps)}


# ---------------------------------------------------------------- API


@app.get("/")
def index():
    return FileResponse(ROOT / "web" / "index.html")


@app.get("/api/prs")
def list_prs():
    out = []
    for f in sorted(PACKS.glob("*.json")):
        p = json.loads(f.read_text(encoding="utf-8"))
        st = state(p["id"], p["steps"])
        g = p["guard"]
        out.append({"id": p["id"], "title": p["requirement"]["title"], "author": p["author"], "route": p["route"],
                    "stats": p["stats"], "guard": {k: g.get(k) for k in ("ran", "existing", "kept", "regression", "new_tests")},
                    "done": st["done"], "total": st["total"], "signed": bool(st["signoff"]), "reviewers": sorted(st["presence"])})
    return out


@app.get("/api/prs/{pr}")
def get_pr(pr: str):
    p = pack(pr)
    return {"pack": p, "state": state(pr, p["steps"])}


class Vote(BaseModel):
    user: str
    step: str
    vote: str  # ok | question | problem
    note: str = ""


@app.post("/api/prs/{pr}/vote")
def vote(pr: str, v: Vote):
    if v.vote not in ("ok", "question", "problem") or not v.user.strip():
        raise HTTPException(400, "bad vote")
    if v.vote == "problem" and not v.note.strip():
        raise HTTPException(400, "Say what the problem is")
    record({"type": "vote", "pr": pr, **v.model_dump()})
    return {"ok": True}


class Here(BaseModel):
    user: str
    step: str


@app.post("/api/prs/{pr}/presence")
def here(pr: str, h: Here):
    old = presence.setdefault(pr, {}).get(h.user)
    presence[pr][h.user] = (h.step, time.time())
    if not old or old[0] != h.step:
        notify(pr)
    return {"ok": True}


class Ask(BaseModel):
    user: str
    step: str
    question: str


@app.post("/api/prs/{pr}/ask")
def ask(pr: str, a: Ask):
    p = pack(pr)
    step = next((s for s in p["steps"] if s["id"] == a.step), None)
    if not step:
        raise HTTPException(404, "no such step")
    claim = next((c for c in p["claims"] if c["id"] == step.get("claim")), None)
    context = json.dumps({"step": step, "claim": claim, "code": code_for(p, claim)}, indent=1)[:60000]
    import anthropic
    msg = anthropic.Anthropic().messages.create(
        model="claude-opus-5-5", max_tokens=600,
        messages=[{"role": "user", "content": f"A reviewer asks about one step of a code review. Answer in at most 4 short sentences, "
                   f"plainly, using only the context. If the context does not show it, say so.\n\nCONTEXT:\n{context}\n\nQUESTION: {a.question}"}])
    answer = "".join(b.text for b in msg.content if b.type == "text")
    record({"type": "ask", "pr": pr, "user": a.user, "step": a.step, "question": a.question, "answer": answer})
    return {"answer": answer}


def code_for(p: dict, claim: dict | None) -> list[dict]:
    if not claim:
        return []
    want = {(x["path"]) for x in claim["cites"]}
    return [{"path": f["path"], "hunks": f["hunks"]} for f in p["files"] if f["path"] in want]


class Signoff(BaseModel):
    user: str
    decision: str  # accept | reject
    risk: str


@app.post("/api/prs/{pr}/signoff")
def signoff(pr: str, s: Signoff):
    p = pack(pr)
    st = state(pr, p["steps"])
    if s.decision == "accept" and not st["ready"]:
        raise HTTPException(400, f"{st['total'] - st['done']} steps are not approved yet")
    if p["route"] == "blocked" and s.decision == "accept":
        raise HTTPException(400, "A test that passed before now fails. This change cannot be accepted.")
    if not s.risk.strip():
        raise HTTPException(400, "Write the risk you accept, in one sentence")
    record({"type": "signoff", "pr": pr, **s.model_dump()})
    return {"ok": True}


@app.post("/api/prs/{pr}/reset")
def reset(pr: str):
    record({"type": "reset", "pr": pr})
    return {"ok": True}


@app.get("/api/prs/{pr}/stream")
async def stream(pr: str):
    q: asyncio.Queue = asyncio.Queue()
    subscribers.setdefault(pr, set()).add(q)

    async def gen():
        try:
            yield "data: hello\n\n"
            while True:
                try:
                    yield f"data: {await asyncio.wait_for(q.get(), 20)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            subscribers[pr].discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream")
