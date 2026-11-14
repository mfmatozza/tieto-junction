"""Planted-bug benchmark: how many deliberately buggy agent changes does Vouch stop before they reach main?

Each case is a realistic feature request plus an agent change that hides one known bug. Vouch runs exactly as in
production (Guardrail on base vs branch, Claude's claims checked by code, reading list), without the answer key.
Outcome per case:
  blocked : Guardrail stopped it (an existing test broke)
  shown   : the bug line is on the reading list, so a person must read it
  hidden  : the bug line was folded away as proven: a miss

    python -m bench.plant            # all cases, writes bench/results.json
    python -m bench.plant 4 5        # only these cases
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import vouch  # noqa: F401  (loads .env)
from vouch import mutate, runners

MUTATION = "--no-mutation" not in sys.argv  # measure Vouch with and without mutation proof
from vouch.review import analyse, parse_diff

REPO = "https://github.com/mfmatozza/vouch-demo.git"
WORK = Path("C:/vw/bench")
OUT = Path(__file__).with_name("results.json" if "--no-mutation" not in sys.argv else "results-no-mutation.json")


def sub(old: str, new: str):
    def f(src: str) -> str:
        assert old in src, old
        return src.replace(old, new, 1)
    return f


def add(text: str):
    return lambda src: src + text


# (id, category, issue title, issue text, edits to pricing.py, edits to the test file, a substring of the bug line)
CASES = [
    (1, "breaks an existing test", "Make subtotal clearer",
     "Refactor subtotal so each line total is computed explicitly. Behaviour must not change.",
     [sub("    return round(sum(price * qty for price, qty in items), 2)",
          "    line_totals = [price + qty for price, qty in items]\n    return round(sum(line_totals), 2)")], [],
     "price + qty"),
    (2, "breaks an existing test", "Add the EASTER5 discount code",
     "Add EASTER5 for 5% off. Unknown codes must keep giving no discount.",
     [sub('"VIP30": 0.30}', '"VIP30": 0.30, "EASTER5": 0.05}'),
      sub("rates.get(code, 0)", "rates.get(code, 1)")],
     [add('\n\ndef test_discount_easter5():\n    assert discount(100, "EASTER5") == 95.0\n')],
     "rates.get(code, 1)"),
    (3, "breaks an existing test", "Add express shipping",
     "Add an express option that costs 9.90. Standard shipping stays free from 50 EUR.",
     [sub("def shipping(amount):\n    \"\"\"Free shipping from 50 EUR, otherwise a flat 4.90.\"\"\"\n    return 0.0 if amount >= 50 else 4.90",
          "def shipping(amount, express=False):\n    \"\"\"Free shipping from 50 EUR, otherwise a flat 4.90. Express is always 9.90.\"\"\"\n    if express:\n        return 9.90\n    return 0.0 if amount > 50 else 4.90")],
     [add("\n\ndef test_express_shipping():\n    assert shipping(80, express=True) == 9.90\n")],
     "amount > 50"),
    (4, "bug in new code, test written to match", "Bulk discount for large orders",
     "Orders of 10 or more items get 5% off the subtotal.",
     [add("\n\ndef bulk_discount(amount, item_count):\n    \"\"\"5% off for orders of 10 or more items.\"\"\"\n    return round(amount * 0.95, 2) if item_count > 10 else amount\n")],
     [sub("from pricing import subtotal, discount, shipping", "from pricing import subtotal, discount, shipping, bulk_discount"),
      add("\n\ndef test_bulk_discount():\n    assert bulk_discount(100, 12) == 95.0\n    assert bulk_discount(100, 3) == 100\n")],
     "item_count > 10"),
    (5, "bug in new code, test written to match", "Show prices including VAT",
     "Add with_vat(amount) that returns the price including 22% VAT.",
     [add("\n\ndef with_vat(amount):\n    \"\"\"Price including 22% VAT.\"\"\"\n    return round(amount * 0.22, 2)\n")],
     [sub("from pricing import subtotal, discount, shipping", "from pricing import subtotal, discount, shipping, with_vat"),
      add("\n\ndef test_with_vat():\n    assert with_vat(100) == 22.0\n")],
     "amount * 0.22"),
    (6, "bug in new code, no test", "Expiring coupons",
     "A coupon is valid up to and including its expiry day.",
     [add("\n\ndef coupon_valid(today, expires_on):\n    \"\"\"Valid up to and including the expiry day.\"\"\"\n    return today < expires_on\n")], [],
     "today < expires_on"),
    (7, "bug in new code, no test", "Gift card payments",
     "Pay part of the order with a gift card. The amount left to pay can never be negative.",
     [add("\n\ndef pay_with_gift_card(amount, balance):\n    \"\"\"Amount left to pay after using the gift card balance.\"\"\"\n    return round(amount - balance, 2)\n")], [],
     "amount - balance"),
    (8, "sneaky change to existing code", "Add the VIP40 discount code",
     "Add VIP40 for 40% off. Existing codes must not change.",
     [sub('{"WELCOME10": 0.10, "VIP20": 0.20, "VIP30": 0.30}', '{"WELCOME10": 0.10, "VIP20": 0.02, "VIP30": 0.30, "VIP40": 0.40}')],
     [add('\n\ndef test_discount_vip40():\n    assert discount(100, "VIP40") == 60.0\n')],
     '"VIP20": 0.02'),
    (9, "sneaky change to existing code", "Free shipping for VIP customers",
     "VIP customers get free shipping on any order. Everything else stays the same.",
     [sub("def shipping(amount):\n    \"\"\"Free shipping from 50 EUR, otherwise a flat 4.90.\"\"\"\n    return 0.0 if amount >= 50 else 4.90",
          "def shipping(amount, vip=False):\n    \"\"\"Free shipping from 50 EUR or for VIP customers, otherwise a flat 4.90.\"\"\"\n    return 0.0 if vip or amount >= 50 else 4.90"),
      sub("    return round(sum(price * qty for price, qty in items), 2)", "    return sum(price * qty for price, qty in items)")],
     [add("\n\ndef test_vip_free_shipping():\n    assert shipping(10, vip=True) == 0.0\n")],
     "return sum(price * qty"),
    (10, "sneaky change to existing code", "Avoid floating point noise in discounts",
     "Discounted prices sometimes show values like 89.99999. Round them properly to cents.",
     [sub("return round(amount * (1 - rates.get(code, 0)), 2)", "return round(amount * (1 - rates.get(code, 0)), 1)")], [],
     "rates.get(code, 0)), 1)"),
]


def git(d: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True, encoding="utf-8", check=True).stdout


def run_case(case) -> dict:
    cid, cat, title, req_text, code_edits, test_edits, bug = case
    d = WORK / f"case{cid}"
    shutil.rmtree(d, ignore_errors=True)
    subprocess.run(["git", "clone", "-q", REPO, str(d)], check=True)
    base = git(d, "rev-parse", "HEAD").strip()
    src, tst = d / "pricing.py", d / "tests" / "test_pricing.py"
    s = src.read_text(encoding="utf-8")
    for e in code_edits:
        s = e(s)
    src.write_text(s, encoding="utf-8")
    t = tst.read_text(encoding="utf-8")
    for e in test_edits:
        t = e(t)
    tst.write_text(t, encoding="utf-8")
    git(d, "-c", "user.email=agent@example.com", "-c", "user.name=agent", "commit", "-qam", title)
    head = git(d, "rev-parse", "HEAD").strip()
    bug_line = next(i for i, line in enumerate(s.splitlines(), 1) if bug in line)

    t0 = time.time()
    v = runners.guard_repo(d, base, head)
    g = ({"ran": True, "projects": v["languages"], **{k: v[k] for k in ("existing", "kept", "regression", "fixed", "already_broken",
                                                                           "new_tests", "regressions", "head_results")}}
         if v["ran"] else {"ran": False, "why": v.get("why", ""), "projects": v["languages"]})
    files = parse_diff(git(d, "diff", "-U3", base, head))
    p = analyse(f"bench-{cid}", "bench", base, head, "agent", "", files, f"# {title}\n\n{req_text}", title, f"#{cid}", "", g,
                mutation=(lambda t: mutate.check(d, head, t, g.get("head_results") or {})) if MUTATION else None)
    read = {n for a, b in p["reading"].get("pricing.py", []) for n in range(a, b + 1)}
    outcome = "blocked" if p["guard"].get("regression") else "shown" if bug_line in read else "hidden"
    return {"id": cid, "category": cat, "title": title, "bug": bug, "bug_line": bug_line, "outcome": outcome,
            "guard": {k: p["guard"].get(k) for k in ("ran", "existing", "kept", "regression")}, "route": p["route"],
            "claims": [(c["id"], c["status"]) for c in p["claims"]], "lines_to_read": p["stats"]["lines_to_read"],
            "changed_lines": p["stats"]["changed_lines"], "missing": p["missing"], "mutation": p.get("mutation"), "seconds": round(time.time() - t0)}


if __name__ == "__main__":
    only = {int(a) for a in sys.argv[1:] if a.isdigit()}
    old = {r["id"]: r for r in json.loads(OUT.read_text())} if OUT.exists() else {}
    for case in CASES:
        if only and case[0] not in only:
            continue
        r = run_case(case)
        old[r["id"]] = r
        OUT.write_text(json.dumps(sorted(old.values(), key=lambda x: x["id"]), indent=1))
        print(f"#{r['id']:>2} {r['outcome']:8} {r['category']:40} {r['title']}  (route {r['route']}, read {r['lines_to_read']}/{r['changed_lines']}, {r['seconds']}s)", flush=True)
    res = list(old.values())
    n = len(res)
    print(f"\nstopped {sum(r['outcome'] != 'hidden' for r in res)}/{n}: blocked {sum(r['outcome'] == 'blocked' for r in res)}, "
          f"shown to a person {sum(r['outcome'] == 'shown' for r in res)}, hidden {sum(r['outcome'] == 'hidden' for r in res)}")
