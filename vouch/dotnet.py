"""Run .NET tests in throwaway git worktrees and read TRX results. Results are cached per (sha, project, filter)."""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

TARGET = Path(os.environ.get("VOUCH_TARGET", Path(__file__).resolve().parents[2] / "tieto-messagepack"))
WORK = Path(os.environ.get("VOUCH_WORK", "C:/vw"))  # short root: the repo has paths near Windows' 260-char limit
CACHE = Path(__file__).resolve().parents[1] / ".cache"
DOTNET = "C:/Program Files/dotnet/dotnet.exe" if os.name == "nt" else "dotnet"

# Which test project covers which source folder.
TEST_PROJECTS = {
    "src/MessagePack.SourceGenerator": "tests/MessagePack.SourceGenerator.Tests/MessagePack.SourceGenerator.Tests.csproj",
    "src/MessagePack.Annotations": "tests/MessagePack.SourceGenerator.Tests/MessagePack.SourceGenerator.Tests.csproj",
    "tests/MessagePack.SourceGenerator.Tests": "tests/MessagePack.SourceGenerator.Tests/MessagePack.SourceGenerator.Tests.csproj",
}


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(TARGET), "-c", "core.longpaths=true", *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout


def worktree(sha: str) -> Path:
    path = WORK / sha[:10]
    if not (path / ".git").exists():
        WORK.mkdir(parents=True, exist_ok=True)
        git("worktree", "add", "-f", "--detach", str(path), sha)
    return path


def run_tests(sha: str, project: str, names: list[str] | None = None, timeout: int = 1500) -> dict[str, str] | None:
    """{test name: Passed|Failed|NotExecuted}, or None when the tests could not run (build error, timeout)."""
    key = hashlib.sha1(json.dumps([sha, project, sorted(names or [])]).encode()).hexdigest()[:16]
    cached = CACHE / f"tests-{key}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    wt = worktree(sha)
    out = WORK / f"r-{key}"
    cmd = [DOTNET, "test", project, "--logger", "trx;LogFileName=r.trx", "--results-directory", str(out)]
    if names:
        cmd += ["--filter", "|".join(f"FullyQualifiedName~{n}" for n in names)]
    env = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}
    try:
        subprocess.run(cmd, cwd=wt, capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return None
    trx = out / "r.trx"
    if not trx.exists():
        return None
    results = parse_trx(trx.read_text(encoding="utf-8", errors="replace"))
    if not results:
        return None
    CACHE.mkdir(exist_ok=True)
    cached.write_text(json.dumps(results))
    return results


def parse_trx(text: str) -> dict[str, str]:
    return {m[0]: m[1] for m in re.findall(r'<UnitTestResult [^>]*?testName="([^"]+)"[^>]*?outcome="([^"]+)"', text)}


if __name__ == "__main__":
    sample = '<UnitTestResult executionId="1" testName="A.B" computerName="x" outcome="Passed" /><UnitTestResult testName="A.C" outcome="Failed">'
    assert parse_trx(sample) == {"A.B": "Passed", "A.C": "Failed"}
    print("ok")
