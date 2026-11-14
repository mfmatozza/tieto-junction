"""Dashboard server. Run: python -m uvicorn vouch.app:app --host 0.0.0.0 --port 8000

State = an append-only list of review events (vote, ask, signoff). Persisted to data/events.jsonl, and to Aiven
PostgreSQL (review_events) when AIVEN_PG_URL is set. Presence lives in memory with a 15 s timeout.
"""
import asyncio
import json
import os
import secrets
import urllib.parse
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

import vouch  # noqa: F401  (loads .env)

ROOT = Path(__file__).resolve().parents[1]
SERVERLESS = bool(os.environ.get("VERCEL"))  # read-only disk, many instances: Postgres is the source of truth
PACKS, DATA = ROOT / "packs", (Path("/tmp/vouch") if SERVERLESS else ROOT / "data")
LOG = DATA / "events.jsonl"
app = FastAPI()
subscribers: dict[str, set[asyncio.Queue]] = {}
presence: dict[str, dict[str, tuple[str, float]]] = {}  # pr -> user -> (step, seen_at)

# ---------------------------------------------------------------- storage

_pg = None


def pg():
    global _pg
    if _pg is None:
        _pg = False  # not configured or unreachable: fall back to the local log, don't retry on every request
        if os.environ.get("AIVEN_PG_URL"):
            try:
                import psycopg
                _pg = psycopg.connect(os.environ["AIVEN_PG_URL"], autocommit=True, connect_timeout=8)
            except Exception as e:
                print("Postgres off:", e)
    return _pg


_kafka = _kv = None
TOPIC = "review.events"


def kafka():
    """Producer for Aiven Kafka (SASL). False = not configured or unreachable, don't retry on every vote."""
    global _kafka
    if _kafka is None:
        _kafka = False
        if os.environ.get("AIVEN_KAFKA_PASSWORD"):
            try:
                from kafka import KafkaProducer
                from kafka.admin import KafkaAdminClient, NewTopic
                conf = dict(bootstrap_servers=os.environ["AIVEN_KAFKA_BOOTSTRAP"], security_protocol="SASL_SSL",
                            sasl_mechanism="SCRAM-SHA-256", sasl_plain_username=os.environ.get("AIVEN_KAFKA_USER", "avnadmin"),
                            sasl_plain_password=os.environ["AIVEN_KAFKA_PASSWORD"],
                            ssl_cafile=ca_file())
                try:
                    KafkaAdminClient(**conf).create_topics([NewTopic(TOPIC, 1, 2)])
                except Exception:
                    pass  # already exists
                _kafka = KafkaProducer(**conf, value_serializer=lambda v: json.dumps(v).encode())
            except Exception as e:
                print("Kafka off:", e)
    return _kafka


def kv():
    """Aiven Valkey for live presence. False = use the in-memory dict."""
    global _kv
    if _kv is None:
        _kv = False
        if os.environ.get("AIVEN_VALKEY_URL"):
            try:
                import redis
                _kv = redis.Redis.from_url(os.environ["AIVEN_VALKEY_URL"], decode_responses=True)
                _kv.ping()
            except Exception as e:
                print("Valkey off:", e)
                _kv = False
    return _kv


def set_presence(pr: str, user: str, step: str) -> str | None:
    """Returns the user's previous step. Valkey key expires after 15 s = user left."""
    if kv():
        try:
            return kv().set(f"presence:{pr}:{user}", step, ex=15, get=True)
        except Exception:
            pass
    old = presence.setdefault(pr, {}).get(user)
    presence[pr][user] = (step, time.time())
    return old[0] if old else None


def get_presence(pr: str) -> dict[str, str]:
    if kv():
        try:
            keys = list(kv().scan_iter(f"presence:{pr}:*"))
            return {k.split(":", 2)[2]: s for k, s in zip(keys, kv().mget(keys) if keys else []) if s}
        except Exception:
            pass
    now = time.time()
    return {u: s for u, (s, t) in presence.get(pr, {}).items() if now - t < 15}


def load_events() -> list[dict]:
    if not LOG.exists():
        return []
    return [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]


EVENTS = load_events()


def current_events() -> list[dict]:
    """Postgres is the shared log (laptop and Vercel see the same review); the local file is the fallback."""
    if pg():
        try:
            return [r[0] for r in pg().execute(
                "SELECT payload FROM review_events WHERE aggregate_type = 'pull_request' ORDER BY occurred_at").fetchall()]
        except Exception:
            pass
    return EVENTS


def ca_file() -> str:
    """AIVEN_KAFKA_CA_PEM is a path, or (on Vercel) the certificate itself."""
    v = os.environ.get("AIVEN_KAFKA_CA_PEM", "ca.pem")
    if v.lstrip().startswith("-----BEGIN"):
        f = Path("/tmp/aiven-ca.pem")
        f.write_text(v.replace("\\n", "\n"))  # env vars may carry the PEM with literal \n
        return str(f)
    return str(ROOT / v)


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
    try:
        if kafka():
            kafka().send(TOPIC, {"type": ev["type"], "id": ev["pr"],
                                 "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ev["at"])), "data": ev})
    except Exception:
        pass
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
    for ev in current_events():
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
    here = get_presence(pr)
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
def landing():
    return FileResponse(ROOT / "web" / "landing.html")


@app.get("/review")
def review_page():
    return FileResponse(ROOT / "web" / "index.html")


@app.get("/app")
def app_page(request: Request):
    if not session_of(request):
        return RedirectResponse("/")
    return FileResponse(ROOT / "web" / "app.html")


# ---------------------------------------------------------------- GitHub login (sessions in Valkey, else memory)

SESSIONS: dict[str, dict] = {}
COOKIE = "vouch_session"
CONNECTED_REPO = "te-industry-tech-office/junction26-messagepack-csharp"


def session_of(request: Request) -> dict | None:
    sid = request.cookies.get(COOKIE)
    if not sid:
        return None
    if kv():
        try:
            raw = kv().get(f"session:{sid}")
            return json.loads(raw) if raw else None
        except Exception:
            pass
    return SESSIONS.get(sid)


def start_session(user: dict) -> RedirectResponse:
    sid = secrets.token_urlsafe(32)
    SESSIONS[sid] = user
    if kv():
        try:
            kv().set(f"session:{sid}", json.dumps(user), ex=7 * 86400)
        except Exception:
            pass
    r = RedirectResponse("/app", status_code=303)
    r.set_cookie(COOKIE, sid, max_age=7 * 86400, httponly=True, samesite="lax")
    r.delete_cookie("oauth_state")
    return r


@app.get("/auth/github")
def gh_login(request: Request):
    cid = os.environ.get("GITHUB_CLIENT_ID")
    if not cid:  # no OAuth app configured: demo identity, so the flow still works offline
        return start_session({"login": "demo", "name": "Demo reviewer", "avatar": "", "token": "", "demo": True})
    state = secrets.token_urlsafe(16)
    q = urllib.parse.urlencode({"client_id": cid, "scope": "read:user", "state": state,
                                "redirect_uri": os.environ.get("GITHUB_REDIRECT_URI") or str(request.url_for("gh_callback"))})
    r = RedirectResponse(f"https://github.com/login/oauth/authorize?{q}")
    r.set_cookie("oauth_state", state, max_age=600, httponly=True, samesite="lax")
    return r


@app.get("/auth/github/callback")
def gh_callback(request: Request, code: str = "", state: str = ""):
    if not code or not state or state != request.cookies.get("oauth_state"):
        raise HTTPException(400, "GitHub login failed: state mismatch. Start again from the home page.")
    tok = httpx.post("https://github.com/login/oauth/access_token", headers={"Accept": "application/json"}, timeout=15,
                     data={"client_id": os.environ["GITHUB_CLIENT_ID"], "client_secret": os.environ["GITHUB_CLIENT_SECRET"],
                           "code": code}).json().get("access_token")
    if not tok:
        raise HTTPException(400, "GitHub did not return a token. Start again from the home page.")
    u = httpx.get("https://api.github.com/user", headers={"Authorization": f"Bearer {tok}"}, timeout=15).json()
    return start_session({"login": u["login"], "name": u.get("name") or u["login"], "avatar": u.get("avatar_url", ""), "token": tok})


@app.get("/auth/logout")
def logout(request: Request):
    sid = request.cookies.get(COOKIE)
    if sid:
        SESSIONS.pop(sid, None)
        if kv():
            try:
                kv().delete(f"session:{sid}")
            except Exception:
                pass
    r = RedirectResponse("/")
    r.delete_cookie(COOKIE)
    return r


@app.get("/api/me")
def me(request: Request):
    s = session_of(request)
    if not s:
        raise HTTPException(401, "Not signed in")
    return {k: v for k, v in s.items() if k != "token"}


@app.get("/api/repos")
def repos(request: Request):
    s = session_of(request)
    if not s:
        raise HTTPException(401, "Not signed in")
    out = [{"full_name": CONNECTED_REPO, "connected": True, "language": "C#", "private": False,
            "prs": len(list(PACKS.glob("*.json")))}]
    if s.get("token"):
        try:
            for r in httpx.get("https://api.github.com/user/repos?sort=updated&per_page=12",
                               headers={"Authorization": f"Bearer {s['token']}"}, timeout=15).json():
                if r["full_name"] != CONNECTED_REPO:
                    out.append({"full_name": r["full_name"], "connected": False, "language": r.get("language"),
                                "private": r["private"], "prs": 0})
        except Exception:
            pass  # GitHub down: still show the connected repo
    return out


@app.get("/api/prs")
def list_prs():
    out = []
    for f in sorted(PACKS.glob("*.json")):
        p = json.loads(f.read_text(encoding="utf-8"))
        st = state(p["id"], p["steps"])
        g = p["guard"]
        out.append({"id": p["id"], "title": p["requirement"]["title"], "author": p["author"], "route": p["route"],
                    "stats": p["stats"], "guard": {k: g.get(k) for k in ("ran", "existing", "kept", "regression", "new_tests")},
                    "done": st["done"], "total": st["total"], "signed": bool(st["signoff"]), "reviewers": sorted(st["presence"]),
                    "agent": p.get("agent", "unknown"), "decision": (st["signoff"] or {}).get("decision"),
                    "signed_by": (st["signoff"] or {}).get("user"), "flags": flags(p),
                    "proven": sum(c["status"] == "proven" for c in p["claims"]), "claims": len(p["claims"])})
    return out


def flags(p: dict) -> list[dict]:
    """Potential problems a reviewer should know before opening the PR. level: danger | warn."""
    out = []
    if p["guard"].get("regression"):
        out.append({"level": "danger", "text": f"{p['guard']['regression']} existing tests now fail"})
    by_rule: dict[str, set] = {}
    for r in p["refusals"]:
        by_rule.setdefault(r["why"], set()).add(r["path"])
    out += [{"level": "warn", "text": f"{why.rstrip('.')} ({len(paths)} file{'s' * (len(paths) > 1)})"} for why, paths in by_rule.items()]
    open_claims = sum(c["status"] != "proven" for c in p["claims"])
    if open_claims:
        out.append({"level": "warn", "text": f"{open_claims} of {len(p['claims'])} claims not proven by a test"})
    odd = (p.get("generated") or {}).get("odd") or []
    if odd:
        out.append({"level": "warn", "text": f"{len(odd)} generated file{'s differ' if len(odd) > 1 else ' differs'} from the rest"})
    return out


@app.get("/api/prs/{pr}")
def get_pr(pr: str):
    p = pack(pr)
    odd = set((p.get("generated") or {}).get("odd", []))
    p["files"] = [f for f in p["files"] if f["kind"] != "generated" or f["path"] in odd]  # identical generated files: not sent
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
    if set_presence(pr, h.user, h.step) != h.step:
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
