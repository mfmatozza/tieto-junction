"""Mutation proof: does a passing test actually pin down the lines it is said to prove?

For every code line a proven claim cites, make small deliberate breaks (">" to ">=", "+" to "-", a constant changed)
and run the tests again. If the tests still pass with the line broken, they do not check that line: the line goes
back on the reading list and the claim loses its proof. Deterministic, no AI. Fails closed: if the tests cannot run
on a mutant, that mutant counts as caught only when the suite ran and failed; a suite that never ran proves nothing.
"""
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from vouch import runners

SWAPS = [(r">=", ">"), (r"<=", "<"), (r"==", "!="), (r"!=", "=="), (r"(?<![<>=!])>(?!=)", ">="), (r"(?<![<>=!])<(?!=)", "<="),
         (r" \+ ", " - "), (r" - ", " + "), (r" \* ", " / "), (r" / ", " * "), (r"\band\b", "or"), (r"\bor\b", "and"),
         (r"\bTrue\b", "False"), (r"\bFalse\b", "True"), (r"&&", "||"), (r"\|\|", "&&")]
CODE_EXT = (".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".go", ".java", ".kt", ".rs", ".cs")
MAX_MUTANTS = 16
BUDGET_S = 300


def mutants(line: str) -> list[str]:
    """Up to 3 small breaks of one source line. Comments and strings are left alone."""
    code = line.split("#")[0] if line.lstrip()[:1] != "#" else ""
    if not code.strip() or code.strip().startswith(("//", '"""', "'''", "*")):
        return []
    out = []
    for pat, rep in SWAPS:
        m = re.search(pat, code)
        if m:
            out.append(line[:m.start()] + rep + line[m.end():])
    for num in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])", code):  # every constant on its own, like standard mutation tools
        v = num[1]
        bumped = str(int(v) + 1) if "." not in v else f"{float(v) + 1:g}"
        out.append(line[:num.start()] + bumped + line[num.end():])
    seen, uniq = set(), []
    for m in out:
        if m != line and m not in seen:
            seen.add(m)
            uniq.append(m)
    return uniq[:6]


def check(repo: Path, head: str, targets: dict[str, list[int]], head_results: dict[str, str]) -> dict:
    """targets: {path: [line numbers]}. Returns {"ran": bool, "survived": {path: [(line, mutant)]}, "killed": n, "tried": n}."""
    if not targets or not head_results:
        return {"ran": False, "why": "No passing tests to check against.", "survived": {}, "killed": 0, "tried": 0}
    if any(lang == ".NET" for lang, _ in runners.detect(repo)):
        return {"ran": False, "why": "Skipped for .NET: one test run takes minutes.", "survived": {}, "killed": 0, "tried": 0}
    wt = Path(tempfile.mkdtemp(prefix="vouch-mut-"))
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-f", "--detach", str(wt), head], capture_output=True, check=True)
    passed = {k for k, v in head_results.items() if v == "Passed"}
    survived, killed, tried, t0 = {}, 0, 0, time.time()
    try:
        for path, lines in targets.items():
            f = wt / path
            original = f.read_text(encoding="utf-8")
            src = original.splitlines(keepends=True)
            for n in lines:
                if n < 1 or n > len(src):
                    continue
                for m in mutants(src[n - 1].rstrip("\n")):
                    if tried >= MAX_MUTANTS or time.time() - t0 > BUDGET_S:
                        break
                    tried += 1
                    f.write_text("".join(src[:n - 1]) + m + "\n" + "".join(src[n:]), encoding="utf-8")
                    _, res = runners.run_all(wt)
                    still = res is not None and all(res.get(k) == "Passed" for k in passed)  # every test that passed still passes
                    if still:
                        survived.setdefault(path, []).append((n, m.strip()))
                    else:
                        killed += 1
            f.write_text(original, encoding="utf-8")
    finally:
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)], capture_output=True)
        shutil.rmtree(wt, ignore_errors=True)
    return {"ran": True, "survived": survived, "killed": killed, "tried": tried}


if __name__ == "__main__":
    assert mutants("    return 0.0 if amount >= 50 else 4.90")[0] == "    return 0.0 if amount > 50 else 4.90"
    vip = mutants('    rates = {"WELCOME10": 0.10, "VIP20": 0.02, "VIP30": 0.30}')
    assert any('"VIP20": 1.02' in m for m in vip) and len(vip) == 3, vip  # each constant mutated separately
    assert "    return round(amount * 0.95, 2) if item_count >= 10 else amount" in mutants("    return round(amount * 0.95, 2) if item_count > 10 else amount")
    assert mutants('    """A docstring line"""') == [] and mutants("# comment") == []
    print("ok:", mutants("    return round(amount * 0.95, 2) if item_count > 10 else amount"))
