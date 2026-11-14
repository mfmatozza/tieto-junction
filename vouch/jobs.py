"""Review any GitHub pull request: fetch it, run Guardrail + Checkpoint, store the result in Aiven Postgres.

The website (Vercel) cannot run test suites, so it only queues a job:  website -> Aiven Kafka `review.jobs` -> worker.
Run the worker on any machine with git, the language toolchains and the Anthropic key:

    python -m vouch.jobs worker            # consume jobs from Kafka forever
    python -m vouch.jobs run owner/repo 12 # review one pull request now

Packs live in Postgres table `packs`, keyed "owner~repo~number". Status: queued | running | ready | failed.
"""
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

import httpx

import vouch  # noqa: F401  (loads .env)
from vouch import mutate, runners
from vouch.review import analyse, parse_diff

WORK = Path(os.environ.get("VOUCH_WORK", "C:/vw")) / "gh"
TOPIC = "review.jobs"


def pack_id(repo: str, number: int) -> str:
    return f"{repo.replace('/', '~')}~{number}"


def gh(path: str, token: str = "") -> dict | list:
    tok = token or os.environ.get("GITHUB_TOKEN", "")
    for attempt in range(3):  # GitHub network blips happen; a read is safe to retry
        try:
            r = httpx.get(f"https://api.github.com{path}", timeout=20, headers={"Accept": "application/vnd.github+json",
                                                                                **({"Authorization": f"Bearer {tok}"} if tok else {})})
            r.raise_for_status()
            return r.json()
        except (httpx.TransportError, httpx.HTTPStatusError) as e:
            if attempt == 2 or (isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500):
                raise
            time.sleep(3)


# ---------------------------------------------------------------- storage (Aiven Postgres)

_db = None


def q(query: str, params: tuple = (), fetch: str = ""):
    """One statement, reconnecting once if the connection dropped (a long test run leaves it idle for minutes)."""
    global _db
    import psycopg
    for attempt in (1, 2):
        try:
            if _db is None or _db.closed:
                _db = psycopg.connect(os.environ["AIVEN_PG_URL"], autocommit=True, connect_timeout=10)
                _db.execute("""CREATE TABLE IF NOT EXISTS packs (
                    id text PRIMARY KEY, repo text NOT NULL, number int NOT NULL, status text NOT NULL,
                    error text, pack jsonb, requested_by text, updated_at timestamptz NOT NULL DEFAULT now())""")
            cur = _db.execute(query, params)
            return cur.fetchone() if fetch == "one" else cur.fetchall() if fetch == "all" else None
        except psycopg.OperationalError:
            _db = None
            if attempt == 2:
                raise


def set_status(pid: str, repo: str, number: int, status: str, pack: dict | None = None, error: str = "", by: str = "") -> None:
    q("""INSERT INTO packs (id, repo, number, status, pack, error, requested_by, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, error = EXCLUDED.error, updated_at = now(),
            pack = COALESCE(EXCLUDED.pack, packs.pack), requested_by = COALESCE(NULLIF(EXCLUDED.requested_by, ''), packs.requested_by)""",
                 (pid, repo, number, status, json.dumps(pack) if pack else None, error[:2000], by))


def get(pid: str) -> dict | None:
    row = q("SELECT status, pack, error, updated_at FROM packs WHERE id = %s", (pid,), "one")
    return {"status": row[0], "pack": row[1], "error": row[2], "updated_at": row[3].isoformat()} if row else None


def statuses(repo: str) -> dict[int, dict]:
    rows = q("SELECT number, status, error, pack->'stats', pack->'guard', pack->>'route', pack->>'head', pack->>'agent', pack->'mutation' "
             "FROM packs WHERE repo = %s", (repo,), "all")
    return {r[0]: {"status": r[1], "error": r[2], "stats": r[3], "guard": r[4], "route": r[5], "head": r[6], "agent": r[7], "mutation": r[8]}
            for r in rows}


# ---------------------------------------------------------------- the review of one pull request

def git(repo_dir: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo_dir), "-c", "core.longpaths=true", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True).stdout


def lanes_agents(d: Path, head: str) -> str:
    """Which coding agents wrote this change, from Lanes provenance. A `lanes pr` squash names the checkpoint range
    on lanes/main; every checkpoint there carries `Lanes-Agent`. No trailer anywhere = unknown, trusted for nothing."""
    import re
    direct = git(d, "log", "-1", "--format=%(trailers:key=Lanes-Agent,valueonly)", head).strip()
    if direct:
        return re.sub(r"\s*\(session.*", "", direct).strip()
    m = re.search(r"Lanes checkpoint commits on (\S+) \(([0-9a-f]{7,40})\.\.([0-9a-f]{7,40})\)", git(d, "log", "-1", "--format=%B", head))
    if not m:
        return ""
    try:
        git(d, "fetch", "-q", "origin", m[1])
        found = git(d, "log", "--format=%(trailers:key=Lanes-Agent,valueonly)", f"{m[2]}^..{m[3]}")
    except subprocess.CalledProcessError:
        return ""
    agents = sorted({re.sub(r"\s*\(session.*", "", a).strip() for a in found.splitlines() if a.strip()})
    return ", ".join(agents)


def review_pr(repo: str, number: int, use_ai: bool = True) -> dict:
    pr = gh(f"/repos/{repo}/pulls/{number}")
    base, head = pr["base"]["sha"], pr["head"]["sha"]
    d = WORK / repo.replace("/", "__")
    if not (d / ".git").exists():
        WORK.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", pr["base"]["repo"]["clone_url"], str(d)], check=True)
    git(d, "fetch", "-q", "origin", base, f"pull/{number}/head")  # forks included: GitHub serves every PR head here
    base = git(d, "merge-base", base, head).strip()                 # diff from where the branch started
    files = parse_diff(git(d, "diff", "-U3", base, head))
    agent = lanes_agents(d, head)
    req = f"# {pr['title']}\n\n{pr.get('body') or ''}"

    v = runners.guard_repo(d, base, head)
    g = ({"ran": True, "projects": v["languages"], **{k: v[k] for k in ("existing", "kept", "regression", "fixed", "already_broken",
                                                                           "new_tests", "regressions", "head_results")}}
         if v["ran"] else {"ran": False, "why": v.get("why", "Tests did not run."), "projects": v["languages"]})

    p = analyse(pack_id(repo, number), pr["head"]["ref"], base, head, pr["user"]["login"], agent, files, req, pr["title"],
                f"#{number}", pr["html_url"], g, use_ai=use_ai,
                mutation=lambda targets: mutate.check(d, head, targets, g.get("head_results") or {}))
    p["github"] = {"repo": repo, "number": number, "url": pr["html_url"], "head_sha": pr["head"]["sha"],
                   "base_ref": pr["base"]["ref"], "head_ref": pr["head"]["ref"]}
    return p


SITE = os.environ.get("VOUCH_URL", "https://vouch-review-hazel.vercel.app")


def commit_status(repo: str, sha: str, state: str, text: str, pid: str) -> None:
    """The verdict on the pull request itself. Make `vouch/review` a required check and nothing merges without it."""
    tok = os.environ.get("GITHUB_TOKEN", "")
    if not tok or not sha:
        return
    try:
        httpx.post(f"https://api.github.com/repos/{repo}/statuses/{sha}", timeout=20,
                   headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {tok}"},
                   json={"state": state, "context": "vouch/review", "description": text[:140], "target_url": f"{SITE}/review#/pr/{pid}"})
    except Exception as e:
        print("status not posted:", e)


def run_job(job: dict) -> None:
    repo, number = job["repo"], int(job["number"])
    pid = pack_id(repo, number)
    set_status(pid, repo, number, "running")
    sha = ""
    try:
        sha = gh(f"/repos/{repo}/pulls/{number}")["head"]["sha"]
        commit_status(repo, sha, "pending", "Vouch is running the tests and checking the claims", pid)
        p = review_pr(repo, number)
        set_status(pid, repo, number, "ready", p)
        g, st = p["guard"], p["stats"]
        if g.get("regression"):
            commit_status(repo, p["github"]["head_sha"], "failure", f"Blocked: {g['regression']} existing test(s) broke", pid)
        else:
            commit_status(repo, p["github"]["head_sha"], "pending", f"Waiting for human sign-off: read {st['lines_to_read']} of {st['changed_lines']} lines", pid)
        print(f"ready {pid}")
    except Exception as e:  # any failure is shown on the site; nothing is folded for a review that did not finish
        traceback.print_exc()
        set_status(pid, repo, number, "failed", error=f"{type(e).__name__}: {e}")
        commit_status(repo, sha, "error", "Vouch could not finish the check", pid)


def worker() -> None:
    """Consume review jobs forever. Network drops (Wi-Fi, Kafka restarts) reconnect instead of killing the worker."""
    from kafka import KafkaConsumer
    from vouch.app import ca_file, kafka  # same Aiven connection settings as the website
    while True:
        try:
            kafka()  # creates the review.jobs topic on first run
            c = KafkaConsumer(TOPIC, group_id="vouch-workers", auto_offset_reset="earliest", enable_auto_commit=True,
                              bootstrap_servers=os.environ["AIVEN_KAFKA_BOOTSTRAP"], security_protocol="SASL_SSL", sasl_mechanism="SCRAM-SHA-256",
                              sasl_plain_username=os.environ.get("AIVEN_KAFKA_USER", "avnadmin"), sasl_plain_password=os.environ["AIVEN_KAFKA_PASSWORD"],
                              ssl_cafile=ca_file(), value_deserializer=lambda b: json.loads(b))
            print(f"worker listening on {TOPIC}", flush=True)
            for msg in c:
                run_job(msg.value)
        except KeyboardInterrupt:
            return
        except Exception as e:
            print(f"worker lost the connection ({type(e).__name__}: {e}); reconnecting in 10 s", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    if sys.argv[1:2] == ["worker"]:
        worker()
    elif sys.argv[1:2] == ["run"] and len(sys.argv) == 4:
        t0 = time.time()
        run_job({"repo": sys.argv[2], "number": sys.argv[3]})
        print(f"{round(time.time() - t0)}s")
    else:
        print(__doc__)
