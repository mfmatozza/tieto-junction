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


PG_ON = bool(os.environ.get("AIVEN_PG_URL"))


def pg():
    """Live Postgres connection, reopened when it went stale (serverless instances sleep between requests)."""
    global _pg
    if not PG_ON:
        return None
    if _pg is None or _pg.closed:
        import psycopg
        _pg = psycopg.connect(os.environ["AIVEN_PG_URL"], autocommit=True, connect_timeout=8)
    return _pg


def sql(query: str, params: tuple = (), fetch: bool = False):
    """Run one statement; on a dropped connection reconnect and retry once. Errors are raised, never swallowed:
    a vote that did not reach Postgres must fail loudly, not vanish."""
    global _pg
    for attempt in (1, 2):
        try:
            cur = pg().execute(query, params)
            return cur.fetchall() if fetch else None
        except Exception:
            try:
                _pg and _pg.close()
            except Exception:
                pass
            _pg = None
            if attempt == 2:
                raise


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
                    admin = KafkaAdminClient(**conf)
                    for t in (TOPIC, "review.jobs"):
                        try:
                            admin.create_topics([NewTopic(t, 1, 2)])
                        except Exception:
                            pass  # already exists
                except Exception:
                    pass
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
    """Postgres is the one shared log: every browser, the laptop and every Vercel instance read the same review.
    The local file is used only when no Postgres is configured at all."""
    if not PG_ON:
        return EVENTS
    try:
        return [r[0] for r in sql("SELECT payload FROM review_events WHERE aggregate_type = 'pull_request' ORDER BY occurred_at", fetch=True)]
    except Exception as e:
        raise HTTPException(503, f"The review store is unreachable, try again in a moment ({type(e).__name__}).")


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
    if PG_ON:
        try:
            sql("INSERT INTO review_events (event_type, aggregate_type, payload) VALUES (%s, 'pull_request', %s)",
                (ev["type"], json.dumps(ev)))
        except Exception as e:  # loud, so the reviewer knows to retry: a silently lost vote is the worst outcome
            raise HTTPException(503, f"Your {ev['type']} was not saved: the review store is unreachable. Try again ({type(e).__name__}).")
    else:
        EVENTS.append(ev)
        DATA.mkdir(exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev) + "\n")
    publish(TOPIC, {"type": ev["type"], "id": ev["pr"], "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ev["at"])), "data": ev})
    notify(ev["pr"])


def publish(topic: str, msg: dict) -> bool:
    """Send to Aiven Kafka and wait for the broker (a serverless instance may freeze right after the response)."""
    try:
        if kafka():
            kafka().send(topic, msg).get(timeout=8)
            return True
    except Exception as e:
        print("Kafka send failed:", e)
    return False


def notify(pr: str) -> None:
    for q in subscribers.get(pr, set()):
        q.put_nowait("changed")


def pack(pr: str) -> dict:
    if "~" in pr:  # a GitHub pull request reviewed by the worker: owner~repo~number, stored in Aiven Postgres
        from vouch import jobs
        row = jobs.get(pr)
        if not row:
            raise HTTPException(404, "This pull request has not been checked yet. Run Vouch on it first.")
        if row["status"] != "ready":
            raise HTTPException(409, f"Vouch is still working on this pull request ({row['status']}). {row['error'] or ''}".strip())
        return row["pack"]
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
    q = urllib.parse.urlencode({"client_id": cid, "scope": "read:user public_repo", "state": state,
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


def review_record(p: dict, st: dict, s: Signoff, by: str) -> str:
    """The comment Vouch leaves on the pull request: what was proven, by what, and who accepted which risk."""
    g = p["guard"]
    lines = [f"## Vouch review: {'accepted' if s.decision == 'accept' else 'rejected'} by @{by}", ""]
    lines.append(f"**Guardrail:** {g['kept']}/{g['existing']} existing tests still pass, {g['regression']} regression(s)." if g.get("ran")
                 else f"**Guardrail:** not run ({g.get('why', '')}). Every line was open for review.")
    proven = sum(c["status"] == "proven" for c in p["claims"])
    lines.append(f"**Checkpoint:** {proven}/{len(p['claims'])} AI claims proven by code. AI confidence was not used.")
    lines.append(f"**Read by people:** {p['stats']['lines_to_read']} of {p['stats']['changed_lines']} changed lines.")
    lines += ["", "| Step | Reviewed by |", "|---|---|"]
    for x in p["steps"]:
        if x["kind"] == "sign":
            continue
        v = st["votes"].get(x["id"], {})
        who = ", ".join(f"{u} ({'ok' if y['vote'] == 'ok' else y['vote']})" for u, y in v.items()) or "nobody"
        lines.append(f"| {x['title'][:80].replace('|', '/')} | {who} |")
    lines += ["", f"**{'Risk accepted' if s.decision == 'accept' else 'Reason'}:** {s.risk.strip()}", "",
              "<sub>Posted by Vouch. Proven means: the cited lines exist, the quote is in the issue, and the named test passed.</sub>"]
    return "\n".join(lines)


def gh_call(method: str, path: str, token: str, body: dict | None = None) -> httpx.Response:
    return httpx.request(method, f"https://api.github.com{path}", json=body, timeout=20,
                         headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"})


@app.post("/api/prs/{pr}/signoff")
def signoff(pr: str, s: Signoff, request: Request):
    p = pack(pr)
    st = state(pr, p["steps"])
    if s.decision == "accept" and not st["ready"]:
        raise HTTPException(400, f"{st['total'] - st['done']} steps are not approved yet")
    if p["route"] == "blocked" and s.decision == "accept":
        raise HTTPException(400, "A test that passed before now fails. This change cannot be accepted.")
    if not s.risk.strip():
        raise HTTPException(400, "Write the risk you accept, in one sentence")
    out = {"ok": True}
    gh = p.get("github")
    if gh:  # a real pull request: the decision goes to GitHub, under the signer's own account
        sess = session_of(request) or {}
        tok = sess.get("token")
        if not tok:
            raise HTTPException(403, "Sign in with GitHub to sign this pull request: Vouch merges it under your own account.")
        repo, n, sha = gh["repo"], gh["number"], gh["head_sha"]
        by = sess.get("login", s.user)
        c = gh_call("POST", f"/repos/{repo}/issues/{n}/comments", tok, {"body": review_record(p, st, s, by)})
        if c.status_code >= 300:
            raise HTTPException(c.status_code if c.status_code < 500 else 502, f"GitHub refused the review comment: {c.json().get('message', c.text)[:200]}")
        target = str(request.base_url).rstrip("/") + f"/review#/pr/{pr}"
        if s.decision == "accept":
            gh_call("POST", f"/repos/{repo}/statuses/{sha}", tok, {"state": "success", "context": "vouch/review", "target_url": target,
                                                                    "description": f"Signed by {by}"[:140]})
            m = gh_call("PUT", f"/repos/{repo}/pulls/{n}/merge", tok, {"sha": sha, "merge_method": "squash",
                                                                      "commit_title": f"{p['requirement']['title']} (#{n})"[:250]})
            if m.status_code >= 300:  # e.g. new commits since the review (sha mismatch), conflicts, no write access
                raise HTTPException(409, f"Signed, but GitHub did not merge: {m.json().get('message', m.text)[:200]}. "
                                         "If the branch changed, run Vouch again: the review only covers the commit it checked.")
            out["merged"] = m.json().get("sha")
        else:
            gh_call("POST", f"/repos/{repo}/statuses/{sha}", tok, {"state": "failure", "context": "vouch/review", "target_url": target,
                                                                    "description": f"Rejected by {by}"[:140]})
        out["comment"] = c.json().get("html_url")
    record({"type": "signoff", "pr": pr, **s.model_dump(), **{k: v for k, v in out.items() if k != "ok"}})
    return out


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


# ---------------------------------------------------------------- your own repositories: pull requests, run, status

def _token(request: Request) -> str:
    s = session_of(request)
    if not s:
        raise HTTPException(401, "Not signed in")
    return s.get("token") or os.environ.get("GITHUB_TOKEN", "")


@app.get("/api/gh/{owner}/{name}/pulls")
def gh_pulls(owner: str, name: str, request: Request):
    from vouch import jobs
    repo, tok = f"{owner}/{name}", _token(request)
    hdr = {"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {tok}"} if tok else {})}
    info = httpx.get(f"https://api.github.com/repos/{repo}", headers=hdr, timeout=20)
    if info.status_code >= 300:
        raise HTTPException(info.status_code, f"GitHub: {info.json().get('message', info.text)[:200]}")
    prs = httpx.get(f"https://api.github.com/repos/{repo}/pulls?state=all&per_page=30&sort=updated&direction=desc", headers=hdr, timeout=20).json()
    try:
        st = jobs.statuses(repo)
    except Exception:
        st = {}
    out = []
    for p in prs:
        v = st.get(p["number"])
        if p["state"] != "open" and not v:
            continue  # closed pull requests Vouch never saw are not interesting here
        row = {"number": p["number"], "title": p["title"], "author": p["user"]["login"], "url": p["html_url"], "state": p["state"],
               "merged": bool(p.get("merged_at")), "draft": p.get("draft", False), "head_sha": p["head"]["sha"], "vouch": v}
        if v and v["status"] == "ready":
            row["stale"] = v.get("head") != p["head"]["sha"]  # new commits since the check: the review no longer covers them
            try:
                pk = jobs.get(jobs.pack_id(repo, p["number"]))["pack"]
                s2 = state(pk["id"], pk["steps"])
                row["review"] = {"done": s2["done"], "total": s2["total"], "signoff": s2["signoff"], "reviewers": sorted(s2["presence"])}
                row["flags"] = flags(pk)
            except Exception:
                pass
        out.append(row)
    perm = (info.json().get("permissions") or {})
    return {"repo": repo, "language": info.json().get("language"), "can_run": bool(perm.get("push")), "pulls": out}


@app.post("/api/gh/{owner}/{name}/pulls/{number}/run")
def gh_run(owner: str, name: str, number: int, request: Request):
    from vouch import jobs
    s = session_of(request) or {}
    if not s.get("token"):
        raise HTTPException(403, "Sign in with GitHub to run Vouch on your repositories.")
    repo = f"{owner}/{name}"
    info = gh_call("GET", f"/repos/{repo}", s["token"])
    if not (info.json().get("permissions") or {}).get("push"):  # it runs the pull request's code: only people who can merge may start it
        raise HTTPException(403, "Only people who can merge into this repository can run Vouch on it.")
    pid = jobs.pack_id(repo, number)
    jobs.set_status(pid, repo, number, "queued", by=s["login"])
    job = {"repo": repo, "number": number, "by": s["login"]}
    if publish("review.jobs", job):
        return {"queued": pid, "via": "kafka"}
    if not SERVERLESS:  # no queue reachable but we are on a machine that can run tests: do it here
        import threading
        threading.Thread(target=jobs.run_job, args=(job,), daemon=True).start()
        return {"queued": pid, "via": "local"}
    jobs.set_status(pid, repo, number, "failed", error="The job queue is unreachable. Try again.")
    raise HTTPException(503, "The job queue is unreachable. Try again.")
