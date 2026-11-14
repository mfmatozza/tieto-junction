"""One review: diff -> guard -> AI claims -> checks by code -> risk rules -> tests -> reading list -> tour steps.

Usage: python -m vouch.review 2283 [--no-ai] [--no-tests]
Writes packs/<id>.json, which the dashboard reads.
"""
import fnmatch
import json
import os
import re
import sys
import time
from pathlib import Path

from vouch import runners
from vouch.dotnet import TEST_PROJECTS, git, run_tests, worktree

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / "packs"
MODEL = "claude-opus-5-5"
READ_SPEED = 12  # lines a reviewer reads per minute, for the time estimate

# ---------------------------------------------------------------- diff


# Test files in every supported language: .NET, Python, JS/TS, Go, Java/Kotlin, Rust.
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]+\.py$|_test\.(py|go)$|\.(test|spec)\.[cm]?[jt]sx?$"
                       r"|/src/test/(java|kotlin)/|Tests?\.(java|kt|cs)$")


def kind_of(path: str) -> str:
    if "/Resources/" in path and path.startswith("tests/"):
        return "generated"
    if path.endswith((".md", ".txt")) and "PublicAPI" not in path:
        return "doc"
    if TEST_PATH.search(path):
        return "test"
    if path.endswith((".props", ".targets", ".csproj", ".json", ".yml", ".yaml")):
        return "build"
    return "code"


def parse_diff(text: str) -> list[dict]:
    """Unified diff -> [{path, kind, status, hunks:[{lines:[{t, old, new, text}]}]}]. New-file line numbers in `new`."""
    files, cur, hunk, old, new = [], None, None, 0, 0
    for line in text.splitlines():
        if line.startswith("diff --git "):
            cur = {"path": line.split(" b/", 1)[1], "status": "modified", "hunks": []}
            files.append(cur)
        elif cur is None:
            continue
        elif line.startswith("new file"):
            cur["status"] = "added"
        elif line.startswith("deleted file"):
            cur["status"] = "deleted"
        elif line.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)", line)
            old, new = int(m[1]), int(m[2])
            hunk = {"lines": []}
            cur["hunks"].append(hunk)
        elif hunk is not None and line[:1] in "+- " and not line.startswith(("+++", "---")):
            t = line[:1]
            hunk["lines"].append({"t": t, "old": old if t != "+" else None, "new": new if t != "-" else None, "text": line[1:]})
            old += t != "+"
            new += t != "-"
    for f in files:
        f["kind"] = kind_of(f["path"])
    return files


def added(f: dict) -> list[int]:
    return [l["new"] for h in f["hunks"] for l in h["lines"] if l["t"] == "+"]


TRIVIAL = re.compile(r"^\s*[{}()\[\];,]*\s*$")


def meaningful(f: dict) -> list[int]:
    """Added lines a human would actually read: not blank, not a lone brace."""
    return [l["new"] for h in f["hunks"] for l in h["lines"] if l["t"] == "+" and not TRIVIAL.match(l["text"])]


def ranges(nums: list[int]) -> list[list[int]]:
    out = []
    for n in sorted(set(nums)):
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return out


# ---------------------------------------------------------------- AI claims

CLAIM_TOOL = {
    "name": "submit_review_story",
    "description": "The change explained as a short story of narrow, checkable claims.",
    "input_schema": {
        "type": "object",
        "required": ["summary", "claims"],
        "properties": {
            "summary": {"type": "string", "description": "3 plain sentences: what was wrong or missing, what changed, how it is tested."},
            "claims": {"type": "array", "items": {
                "type": "object",
                "required": ["title", "text", "requirement_quote", "cites", "tests", "confidence"],
                "properties": {
                    "title": {"type": "string", "description": "At most 8 plain words, e.g. 'Crash fixed for structs from other assemblies'."},
                    "text": {"type": "string", "description": "One behaviour or one test, in plain words a manager understands."},
                    "requirement_quote": {"type": "string", "description": "Exact words copied from the requirement that this claim answers."},
                    "cites": {"type": "array", "items": {"type": "object", "required": ["path", "start", "end"], "properties": {
                        "path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}}},
                    "tests": {"type": "array", "items": {"type": "string"}, "description": "Test method names (Class.Method) that exercise this claim."},
                    "confidence": {"type": "number"},
                }}},
        },
    },
}

PROMPT = """You are explaining an AI-written code change to a human reviewer who has 5 minutes.
Tell the change as a story, in the order a reviewer should read it, as narrow claims.
Answer ONLY by calling the submit_review_story tool.

Rules:
- One claim = one behaviour or one test. Plain words.
- `requirement_quote`: copy exact words from the REQUIREMENT. Never paraphrase.
- `cites`: every new-file line range (path, start, end) the claim explains. Only lines marked + in the diff.
- `tests`: test methods that exercise the claim, as Class.Method, only ones visible in the diff or listed below.
- Do not claim things the diff does not do. Lines you cannot explain: leave them uncited.

REQUIREMENT:
{req}

TEST METHODS IN CHANGED TEST FILES:
{tests}

DIFF (new-file line numbers, + added, - removed):
{diff}
"""


def numbered_diff(files: list[dict]) -> str:
    out = []
    for f in files:
        if f["kind"] == "generated":
            continue
        out.append(f"### {f['path']} ({f['status']})")
        for h in f["hunks"]:
            for l in h["lines"]:
                n = l["new"] if l["new"] is not None else ""
                out.append(f"{n:>5} {l['t']} {l['text']}")
    return "\n".join(out)


def ask_claude(req: str, files: list[dict], tests: list[str]) -> tuple[dict | None, dict]:
    import anthropic
    t0 = time.time()
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL, max_tokens=16000,
        tools=[CLAIM_TOOL], tool_choice={"type": "auto"},  # this model refuses forced tool choice
        messages=[{"role": "user", "content": PROMPT.format(req=req, tests="\n".join(tests) or "(none)", diff=numbered_diff(files))}],
    )
    usage = {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens, "seconds": round(time.time() - t0)}
    block = next((b for b in msg.content if b.type == "tool_use"), None)
    return (block.input if block else None), usage


# ---------------------------------------------------------------- checks (code, not AI)


def norm(s: str) -> str:
    return re.sub(r"[\s`*_#>|]+", " ", s).strip().lower()


def test_methods(files: list[dict]) -> list[str]:
    """Class.Method for test methods declared on added lines of test files."""
    found = []
    for f in files:
        if f["kind"] != "test":
            continue
        cls = Path(f["path"]).stem
        lines = [l["text"] for h in f["hunks"] for l in h["lines"] if l["t"] != "-"]
        for text in lines:  # Python, Go, JS/TS, Rust test declarations
            m = (re.match(r"\s*(?:async\s+)?def (test_\w+)\s*\(", text) or re.match(r"\s*func (Test\w+)\s*\(", text)
                 or re.match(r"""\s*(?:it|test)\s*\(\s*["'`]([^"'`]+)["'`]""", text) or re.match(r"\s*(?:pub\s+)?fn (\w+)\s*\(\)", text))
            if m:
                found.append(f"{cls}.{m[1]}")
        for i, text in enumerate(lines):  # .NET [Fact]/[Theory] and Java/Kotlin @Test
            if re.search(r"\[(Fact|Theory)|@Test\b", text):
                for nxt in lines[i + 1:i + 4]:
                    m = re.search(r"\b(?:public|private|internal|protected|fun|void)\s+(?:async\s+)?(?:\w[\w<>]*\s+)?(\w+)\s*\(", nxt)
                    if m:
                        found.append(f"{cls}.{m[1]}")
                        break
    return found


def check_claim(c: dict, files: list[dict], req: str, known_tests: list[str]) -> list[dict]:
    by_path = {f["path"]: set(added(f)) for f in files}
    out = []
    bad = [x for x in c["cites"] if x["path"] not in by_path or not any(n in by_path[x["path"]] for n in range(x["start"], x["end"] + 1))]
    out.append({"id": "cite", "ok": bool(c["cites"]) and not bad,
                "msg": "Every cited line exists in the change." if c["cites"] and not bad else
                       ("No lines cited." if not c["cites"] else f"Cites lines that are not in the change: {bad[0]['path']} {bad[0]['start']}-{bad[0]['end']}.")})
    q = norm(c["requirement_quote"])
    ok = len(q) >= 8 and q in norm(req)
    out.append({"id": "quote", "ok": ok, "msg": "The quote is in the requirement, word for word." if ok else "The quote is NOT in the requirement. The AI made it up or paraphrased."})
    short = [t.split(".")[-1] for t in known_tests]
    missing = [t for t in c["tests"] if t.split(".")[-1] not in short]
    out.append({"id": "tests_exist", "ok": bool(c["tests"]) and not missing,
                "msg": "No test named." if not c["tests"] else ("Named tests exist." if not missing else f"Test not found: {missing[0]}.")})
    return out


# ---------------------------------------------------------------- risk rules (refuse to decide)

RULES = [
    ("public_api", "Changes the public API that every user depends on.",
     lambda f, text: fnmatch.fnmatch(f["path"], "*PublicAPI.*.txt") or (f["path"].startswith("src/MessagePack.Annotations/") and re.search(r"\bpublic\b", text))),
    ("analyzer_rules", "Adds or changes analyzer warnings that users will see.",
     lambda f, text: "AnalyzerReleases" in f["path"] or (f["path"].startswith("doc/analyzers/MsgPack") and f["status"] == "added") or "DiagnosticDescriptor" in text),
    ("unsafe_code", "Adds unsafe memory code.",
     lambda f, text: f["kind"] == "code" and re.search(r"\bunsafe\b|Unsafe\.|Marshal\.|stackalloc", text)),
    ("dependencies", "Changes third-party packages.",
     lambda f, text: f["path"].endswith(("Directory.Packages.props", ".csproj")) and "PackageReference" in text or f["path"].endswith("Directory.Packages.props")),
]


def refusals(files: list[dict]) -> list[dict]:
    out = []
    for f in files:
        text = "\n".join(l["text"] for h in f["hunks"] for l in h["lines"] if l["t"] == "+")
        for rule, why, hit in RULES:
            if hit(f, text):
                out.append({"rule": rule, "why": why, "path": f["path"], "ranges": ranges(added(f))})
        if f["kind"] == "test":
            gone = [l["text"] for h in f["hunks"] for l in h["lines"] if l["t"] == "-" and re.search(r"Assert|Verify|Should", l["text"])]
            if gone or f["status"] == "deleted":
                out.append({"rule": "weakened_tests", "why": "Removes test checks. The evidence itself is weaker.", "path": f["path"], "ranges": ranges(added(f))})
    return out


def generated_check(files: list[dict]) -> dict | None:
    """Generated snapshot files: most share one identical edit. Those are proven by code; any file that differs must be read."""
    from collections import Counter
    gen = [f for f in files if f["kind"] == "generated"]
    if not gen:
        return None

    def edit(f):  # lines that only moved (removed and re-added) are not edits
        plus = Counter(l["text"].strip() for h in f["hunks"] for l in h["lines"] if l["t"] == "+")
        minus = Counter(l["text"].strip() for h in f["hunks"] for l in h["lines"] if l["t"] == "-")
        return frozenset({"+ " + t for t in plus - minus if t} | {"- " + t for t in minus - plus if t})

    sigs = {f["path"]: edit(f) for f in gen}
    common, n = Counter(sigs.values()).most_common(1)[0]
    odd = [p for p, sig in sigs.items() if sig != common]
    return {"files": len(gen), "same": n, "lines": sum(len(added(f)) for f in gen), "distinct_edits": sorted(common), "odd": odd,
            "ok": n >= 2}


# ---------------------------------------------------------------- guard: did anything that worked break?


def guard(base: str, head: str, files: list[dict], use_tests: bool) -> dict:
    projects = sorted({p for f in files for src, p in TEST_PROJECTS.items() if f["path"].startswith(src)})
    if use_tests and not projects:  # not the .NET map: detect the language and run its own test tool
        return guard_any(base, head)
    if not use_tests or not projects:
        return {"ran": False, "why": "Tests were not run." if not use_tests else "No test project covers these files.", "projects": projects}
    before, after = {}, {}
    for p in projects:
        b, a = run_tests(base, p), run_tests(head, p)
        if b is None or a is None:
            return {"ran": False, "why": f"Tests did not run for {p}.", "projects": projects}
        before.update(b)
        after.update(a)
    rows = []
    for name, was in before.items():
        now = after.get(name, "Missing")
        verdict = ("kept" if was == "Passed" and now == "Passed" else
                   "regression" if was == "Passed" else
                   "fixed" if now == "Passed" else "already_broken")
        rows.append({"test": name, "before": was, "after": now, "verdict": verdict})
    count = lambda v: sum(r["verdict"] == v for r in rows)
    return {"ran": True, "projects": projects, "existing": len(rows), "kept": count("kept"), "regression": count("regression"),
            "fixed": count("fixed"), "already_broken": count("already_broken"), "new_tests": len(set(after) - set(before)),
            "regressions": [r for r in rows if r["verdict"] == "regression"], "head_results": after}


def guard_any(base: str, head: str) -> dict:
    """Python, JS/TS, Go, Java/Kotlin, Rust: the whole existing suite on base and on head, same verdict as .NET."""
    langs, before = runners.run_all(worktree(base))
    _, after = runners.run_all(worktree(head))
    if not langs:
        return {"ran": False, "why": "No supported test setup found in this repository.", "projects": []}
    if before is None or after is None:
        return {"ran": False, "why": f"The {', '.join(langs)} tests did not run on both commits.", "projects": langs}
    return {"ran": True, "projects": langs, **runners.compare(before, after), "head_results": after}


# ---------------------------------------------------------------- the review


def review(pr: str, use_ai: bool = True, use_tests: bool = True) -> dict:
    branch = f"ju26-issue-{pr}"
    head = git("rev-parse", branch).strip()
    base = git("rev-parse", f"{branch}~1").strip()
    author = git("log", "-1", "--format=%an", head).strip()
    trailers = git("log", "-1", "--format=%(trailers:key=Lanes-Agent,valueonly)", head).strip()
    files = parse_diff(git("diff", "-U3", base, head))
    req_path = ROOT / "requirements" / f"REQ-{pr}.md"
    req = req_path.read_text(encoding="utf-8")
    req_title = req.splitlines()[0].lstrip("# ").strip()
    missing = []

    g = guard(base, head, files, use_tests)
    if not g["ran"]:
        missing.append("guard")

    known_tests = test_methods(files)
    story, usage = None, {}
    if use_ai and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            story, usage = ask_claude(req, files, known_tests)
        except Exception as e:  # any model failure routes up, never down
            missing.append(f"ai ({type(e).__name__})")
    else:
        missing.append("ai")
    claims = (story or {}).get("claims", [])
    if story is not None and not claims:
        missing.append("ai (no claims)")

    # tests the claims name, run on the head commit
    head_results = g.get("head_results") or {}
    named = sorted({t for c in claims for t in c["tests"]})
    if use_tests and named and any(t not in head_results for t in named):
        project = TEST_PROJECTS.get("tests/MessagePack.SourceGenerator.Tests")
        head_results = {**head_results, **(run_tests(head, project, [t.split(".")[-1] for t in named]) or {})}
    if use_tests and named and not head_results:
        missing.append("tests")

    def passed(t: str) -> bool:
        return any(k.endswith(t.split(".")[-1]) and v == "Passed" for k, v in head_results.items())

    for i, c in enumerate(claims, 1):
        c["id"] = f"C{i}"
        c["checks"] = check_claim(c, files, req, known_tests)
        test_ok = bool(c["tests"]) and all(passed(t) for t in c["tests"])
        c["checks"].append({"id": "tests_passed", "ok": test_ok,
                            "msg": "Named tests ran and passed." if test_ok else "Named tests did not all pass (or did not run)."})
        disputed = any(not k["ok"] for k in c["checks"] if k["id"] in ("cite", "quote", "tests_exist"))
        c["status"] = "disputed" if disputed else "proven" if test_ok else "unproven"
        c["evidence"] = "test" if c["status"] == "proven" else "ai_only"

    refs = refusals(files)
    gen = generated_check(files)

    # reading list: every added line in code/test/doc/build files starts on it
    reading = {f["path"]: set(meaningful(f)) for f in files if f["kind"] != "generated"}
    if gen:  # the shared edit is proven by code; files that differ from it are read
        odd = set(gen["odd"]) if gen["ok"] else {f["path"] for f in files if f["kind"] == "generated"}
        reading.update({f["path"]: set(meaningful(f)) for f in files if f["path"] in odd})
    for c in claims:
        if c["status"] == "proven":
            for x in c["cites"]:
                reading.get(x["path"], set()).difference_update(range(x["start"], x["end"] + 1))
    for r in refs:  # refusals put lines back, always
        for a, b in r["ranges"]:
            f = next(x for x in files if x["path"] == r["path"])
            reading.setdefault(r["path"], set()).update(n for n in meaningful(f) if a <= n <= b)

    changed = sum(len(added(f)) for f in files)
    to_read = sum(len(v) for v in reading.values())
    if g.get("regression"):
        route = "blocked"
    elif refs or missing or not claims:
        route = "full"
    elif to_read == 0:
        route = "light"
    else:
        route = "focused"

    pack = {
        "id": pr, "branch": branch, "base": base, "head": head, "author": author, "agent": trailers or "unknown",
        "requirement": {"key": f"#{pr}", "title": req_title, "url": f"https://github.com/MessagePack-CSharp/MessagePack-CSharp/issues/{pr}", "text": req},
        "summary": (story or {}).get("summary", ""),
        "files": files, "claims": claims, "refusals": refs, "generated": gen, "guard": {k: v for k, v in g.items() if k != "head_results"},
        "reading": {p: ranges(sorted(v)) for p, v in reading.items() if v},
        "stats": {"files": len(files), "changed_lines": changed, "lines_to_read": to_read,
                  "minutes": max(1, round(to_read / READ_SPEED)), "minutes_full": max(1, round(changed / READ_SPEED))},
        "route": route, "missing": missing, "usage": usage, "reviewed_at": time.strftime("%Y-%m-%d %H:%M"),
    }
    pack["steps"] = tour(pack)
    return pack


# ---------------------------------------------------------------- tour


def tour(p: dict) -> list[dict]:
    steps = [{"kind": "guard", "title": "Nothing that worked before is broken"}]
    steps.append({"kind": "story", "title": "What this change does"})
    cited = {}
    for c in p["claims"]:
        steps.append({"kind": "claim", "claim": c["id"], "title": c.get("title") or c["text"].split(". ")[0][:80]})
        for x in c["cites"]:
            cited.setdefault(x["path"], set()).update(range(x["start"], x["end"] + 1))
    for i, r in enumerate(p["refusals"]):
        steps.append({"kind": "refusal", "refusal": i, "title": r["why"]})
    if p["generated"]:
        steps.append({"kind": "generated", "title": f"{p['generated']['files']} generated files"})
    left = []
    for f in p["files"]:
        if f["kind"] == "generated":
            continue
        rest = set(added(f)) - cited.get(f["path"], set())
        if rest:
            left.append({"path": f["path"], "ranges": ranges(sorted(rest))})
    if left:
        steps.append({"kind": "leftovers", "title": "Changes nobody explained", "items": left})
    steps.append({"kind": "sign", "title": "Sign off"})
    for i, s in enumerate(steps):
        s["id"] = f"S{i}"
    return steps


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for pr in args or ["2283"]:
        t0 = time.time()
        pack = review(pr, use_ai="--no-ai" not in sys.argv, use_tests="--no-tests" not in sys.argv)
        PACKS.mkdir(exist_ok=True)
        (PACKS / f"{pr}.json").write_text(json.dumps(pack, indent=1), encoding="utf-8")
        s = pack["stats"]
        print(f"#{pr}: route={pack['route']} read {s['lines_to_read']}/{s['changed_lines']} lines, "
              f"claims={len(pack['claims'])} refusals={len(pack['refusals'])} missing={pack['missing']} ({round(time.time()-t0)}s)")
