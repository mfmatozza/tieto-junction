"""Guardrail test runners for every ecosystem: run the existing tests in a checkout, return {test: Passed|Failed|Skipped}.

Each runner is plain subprocess + a parser for the tool's own machine-readable output. No AI anywhere.
detect(repo) picks the runners from marker files; run_all(repo) runs them and merges the results.
Results are None when the suite could not run (build error, timeout, tool missing): Guardrail then fails closed.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

TIMEOUT = 1500


# ---------------------------------------------------------------- parsers (pure functions, tested below)

def parse_junit(xml_text: str) -> dict[str, str]:
    """JUnit XML (pytest, Vitest, Maven Surefire, Gradle, many more) -> {Class.test: status}."""
    out = {}
    root = ET.fromstring(xml_text)
    for tc in root.iter("testcase"):
        cls, name = tc.get("classname") or "", tc.get("name") or ""
        key = f"{cls}.{name}" if cls else name
        if tc.find("failure") is not None or tc.find("error") is not None:
            out[key] = "Failed"
        elif tc.find("skipped") is not None:
            out[key] = "Skipped"
        else:
            out[key] = "Passed"
    return out


def parse_go_json(text: str) -> dict[str, str]:
    """`go test -json` event stream -> {pkg.TestName: status}."""
    out = {}
    for line in text.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("Test") and ev.get("Action") in ("pass", "fail", "skip"):
            out[f"{ev.get('Package', '')}.{ev['Test']}"] = {"pass": "Passed", "fail": "Failed", "skip": "Skipped"}[ev["Action"]]
    return out


def parse_jest_json(text: str) -> dict[str, str]:
    """`jest --json` report -> {file > full test name: status}."""
    out = {}
    for f in json.loads(text).get("testResults", []):
        for a in f.get("assertionResults", []):
            out[f"{Path(f.get('name', '')).name} > {a.get('fullName') or a.get('title')}"] = (
                {"passed": "Passed", "failed": "Failed"}.get(a.get("status"), "Skipped"))
    return out


def parse_cargo(text: str) -> dict[str, str]:
    """`cargo test` text output (stable Rust has no JSON) -> {test path: status}."""
    out = {}
    for name, res in re.findall(r"^test (\S+) \.\.\. (ok|FAILED|ignored)\s*$", text, flags=re.M):
        out[name] = {"ok": "Passed", "FAILED": "Failed", "ignored": "Skipped"}[res]
    return out


# ---------------------------------------------------------------- runners

# A pull request's tests never see our keys.
# ponytail: same OS user, so a hostile test could still read the parent process; a container per run if that matters.
CLEAN_ENV = {k: v for k, v in os.environ.items()
             if not (k.startswith(("AIVEN_", "ANTHROPIC_", "VOUCH_")) or k in ("GITHUB_TOKEN", "GH_TOKEN"))}


def _run(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess | None:
    if not shutil.which(cmd[0]):
        return None
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=TIMEOUT, env={**CLEAN_ENV, **(env or {})})
    except subprocess.TimeoutExpired:
        return None


def _junit_files(paths: list[Path]) -> dict[str, str] | None:
    out = {}
    for p in paths:
        try:
            out.update(parse_junit(p.read_text(encoding="utf-8", errors="replace")))
        except ET.ParseError:
            pass
    return out or None


def run_python(repo: Path) -> dict[str, str] | None:
    py = os.environ.get("VOUCH_PYTHON", "python")
    reqs = [f for f in ("requirements.txt", "requirements-dev.txt", "requirements_dev.txt") if (repo / f).exists()]
    if reqs or (repo / "pyproject.toml").exists():  # fresh clone: its own venv, so a PR's dependencies never touch ours
        venv = repo / ".vouch-venv"
        vpy = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not vpy.exists():  # first run in this checkout: build it once (mutants reuse it)
            if _run([py, "-m", "venv", str(venv)], repo) is None:
                return None
            _run([str(vpy), "-m", "pip", "install", "-q", "pytest", *sum((["-r", r] for r in reqs), [])], repo)
            if (repo / "pyproject.toml").exists():
                _run([str(vpy), "-m", "pip", "install", "-q", "-e", "."], repo)  # best effort: not every pyproject is installable
        py = str(vpy)
    with tempfile.TemporaryDirectory() as d:
        xml = Path(d) / "r.xml"
        if _run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml}"], repo) is None:
            return None
        return _junit_files([xml]) if xml.exists() else None


def run_node(repo: Path) -> dict[str, str] | None:
    pkg = json.loads((repo / "package.json").read_text(encoding="utf-8"))
    if not (repo / "node_modules").exists() and (pkg.get("dependencies") or pkg.get("devDependencies")):
        npm = "npm.cmd" if os.name == "nt" else "npm"  # --ignore-scripts: install hooks never run
        _run([npm, "ci" if (repo / "package-lock.json").exists() else "install", "--ignore-scripts", "--no-audit", "--no-fund"], repo)
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "r"
        if "vitest" in deps:
            r = _run(["npx.cmd" if os.name == "nt" else "npx", "vitest", "run", "--reporter=junit", f"--outputFile={out}.xml"], repo)
            return _junit_files([Path(f"{out}.xml")]) if r is not None and Path(f"{out}.xml").exists() else None
        if "jest" in deps:
            r = _run(["npx.cmd" if os.name == "nt" else "npx", "jest", "--ci", "--json", f"--outputFile={out}.json"], repo)
            return parse_jest_json(Path(f"{out}.json").read_text(encoding="utf-8")) if r is not None and Path(f"{out}.json").exists() else None
        # Node's built-in test runner (node --test), JUnit reporter since Node 20
        r = _run(["node", "--test", "--test-reporter=junit", f"--test-reporter-destination={out}.xml"], repo)
        return _junit_files([Path(f"{out}.xml")]) if r is not None and Path(f"{out}.xml").exists() else None


def run_go(repo: Path) -> dict[str, str] | None:
    r = _run(["go", "test", "-json", "./..."], repo)
    return (parse_go_json(r.stdout) or None) if r is not None else None


def run_maven(repo: Path) -> dict[str, str] | None:
    if _run(["mvn", "-q", "-B", "test", "-Dmaven.test.failure.ignore=true"], repo) is None:
        return None
    return _junit_files(list(repo.glob("**/target/surefire-reports/TEST-*.xml")))


def run_gradle(repo: Path) -> dict[str, str] | None:
    exe = str(repo / ("gradlew.bat" if os.name == "nt" else "gradlew")) if (repo / "gradlew").exists() else "gradle"
    if _run([exe, "test", "--continue", "-q"], repo) is None:
        return None
    return _junit_files(list(repo.glob("**/build/test-results/test/TEST-*.xml")))


def run_cargo(repo: Path) -> dict[str, str] | None:
    r = _run(["cargo", "test", "--no-fail-fast"], repo)
    return (parse_cargo(r.stdout) or None) if r is not None else None


def run_dotnet(repo: Path) -> dict[str, str] | None:
    from vouch.dotnet import DOTNET, parse_trx
    with tempfile.TemporaryDirectory() as d:
        if _run([DOTNET, "test", "--logger", "trx", "--results-directory", d], repo,
                {"DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}) is None:
            return None
        out = {}
        for f in Path(d).glob("**/*.trx"):
            out.update(parse_trx(f.read_text(encoding="utf-8", errors="replace")))
        return out or None


def _is_dotnet(repo: Path) -> bool:
    return any(repo.glob("*.sln")) or any(repo.glob("*.slnx")) or any(repo.glob("*/*.csproj")) or any(repo.glob("*/*/*.csproj"))


# marker file(s) -> (language, runner)
RUNNERS = [
    (("pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini", "conftest.py"), "Python", run_python),
    (("package.json",), "JavaScript / TypeScript", run_node),
    (("go.mod",), "Go", run_go),
    (("pom.xml",), "Java / Kotlin (Maven)", run_maven),
    (("build.gradle", "build.gradle.kts"), "Java / Kotlin (Gradle)", run_gradle),
    (("Cargo.toml",), "Rust", run_cargo),
]


def detect(repo: Path) -> list[tuple[str, callable]]:
    found = [(".NET", run_dotnet)] if _is_dotnet(repo) else []
    return found + [(lang, fn) for markers, lang, fn in RUNNERS if any((repo / m).exists() for m in markers)]


def run_all(repo: Path) -> tuple[list[str], dict[str, str] | None]:
    """(languages found, merged results). None results = at least one suite could not run: fail closed."""
    langs, merged = [], {}
    for lang, fn in detect(repo):
        langs.append(lang)
        res = fn(repo)
        if res is None:
            return langs, None
        merged.update({f"[{lang}] {k}": v for k, v in res.items()})
    return langs, (merged if langs else None)


def compare(before: dict[str, str], after: dict[str, str]) -> dict:
    """The Guardrail verdict, identical for every language: passed before and not after = regression."""
    rows = []
    for name, was in before.items():
        now = after.get(name, "Missing")
        verdict = ("kept" if was == "Passed" and now == "Passed" else
                   "regression" if was == "Passed" else
                   "fixed" if now == "Passed" else "already_broken")
        rows.append({"test": name, "before": was, "after": now, "verdict": verdict})
    count = lambda v: sum(r["verdict"] == v for r in rows)
    return {"existing": len(rows), "kept": count("kept"), "regression": count("regression"), "fixed": count("fixed"),
            "already_broken": count("already_broken"), "new_tests": len(set(after) - set(before)),
            "regressions": [r for r in rows if r["verdict"] == "regression"]}


def guard_repo(repo: Path, base: str, head: str) -> dict:
    """Guardrail on any local git repo: python -m vouch.runners <repo> <base> <head>"""
    trees = {}
    for ref in (base, head):
        wt = Path(tempfile.mkdtemp(prefix="vouch-"))
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "-f", "--detach", str(wt), ref], capture_output=True, check=True)
        trees[ref] = run_all(wt)
    langs, before = trees[base]
    after = trees[head][1]
    if before is None or after is None:
        return {"ran": False, "languages": langs, "why": f"The {', '.join(langs) or 'repository'} tests did not run on both commits."}
    return {"ran": True, "languages": langs, **compare(before, after), "head_results": after}


if __name__ == "__main__" and len(__import__("sys").argv) == 4:
    import sys
    v = guard_repo(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
    if not v["ran"]:
        sys.exit(f"Guardrail could not run the tests ({', '.join(v['languages']) or 'no supported language'}). Fail closed.")
    print(f"{', '.join(v['languages'])}: {v['kept']}/{v['existing']} existing tests still pass, {v['regression']} regression(s), {v['new_tests']} new")
    for r in v["regressions"]:
        print(f"  BLOCKED  {r['test']}: {r['before']} -> {r['after']}")
    sys.exit(1 if v["regression"] else 0)
elif __name__ == "__main__":  # self-check of every parser and of the verdict
    junit = """<testsuites><testsuite><testcase classname="t.test_m" name="test_ok"/>
      <testcase classname="t.test_m" name="test_bad"><failure message="x"/></testcase>
      <testcase classname="t.test_m" name="test_skip"><skipped/></testcase></testsuite></testsuites>"""
    assert parse_junit(junit) == {"t.test_m.test_ok": "Passed", "t.test_m.test_bad": "Failed", "t.test_m.test_skip": "Skipped"}
    go = '{"Action":"run","Package":"m/p","Test":"TestA"}\n{"Action":"pass","Package":"m/p","Test":"TestA"}\n{"Action":"fail","Package":"m/p","Test":"TestB"}\n{"Action":"pass","Package":"m/p"}'
    assert parse_go_json(go) == {"m/p.TestA": "Passed", "m/p.TestB": "Failed"}
    jest = json.dumps({"testResults": [{"name": "/r/sum.test.js", "assertionResults": [{"fullName": "sum adds", "status": "passed"}, {"fullName": "sum neg", "status": "failed"}]}]})
    assert parse_jest_json(jest) == {"sum.test.js > sum adds": "Passed", "sum.test.js > sum neg": "Failed"}
    cargo = "running 3 tests\ntest a::works ... ok\ntest a::breaks ... FAILED\ntest a::later ... ignored\n"
    assert parse_cargo(cargo) == {"a::works": "Passed", "a::breaks": "Failed", "a::later": "Skipped"}
    v = compare({"a": "Passed", "b": "Passed", "c": "Failed"}, {"a": "Passed", "b": "Failed", "c": "Passed", "d": "Passed"})
    assert (v["kept"], v["regression"], v["fixed"], v["new_tests"]) == (1, 1, 1, 1), v
    print("ok: junit, go, jest, cargo parsers and the verdict")
