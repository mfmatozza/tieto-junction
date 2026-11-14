"""Record the demo video's screen blocks from the live product (1920x1080, real data, no mock-ups).

    python video/record.py <block>...      blocks: hero lanes run github review sign results
Each block writes video/raw/<block>.webm. video/assemble.py trims, times and joins them with the face slots.
Needs: a Vouch session id in video/.sid (Valkey session with a GitHub token), the worker running, the Lanes server running.
"""
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = "https://vouch-review-hazel.vercel.app"
HERE = Path(__file__).parent
RAW = HERE / "raw"
SID = (HERE / ".sid").read_text().strip() if (HERE / ".sid").exists() else ""
CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe"
LANES = ["node", "C:/Users/mfmat/Desktop/lanes/dist/lanes.cjs"]
LANES_RUN = Path("C:/vw/lanesrun")
RUN_PR = "GIFT25"  # the Lanes pull request we run Vouch on, live, in the video
SIZE = {"width": 1440, "height": 810}  # recorded at 1440x810, scaled to 1080p: bigger, more readable UI

CURSOR = """
(() => { if (window.__cur) return; window.__cur = 1;
  const c = document.createElement('div');
  c.style.cssText = 'position:fixed;z-index:2147483647;width:22px;height:22px;border-radius:50%;background:rgba(15,31,77,.25);border:2px solid #0f1f4d;pointer-events:none;transform:translate(-50%,-50%);transition:transform .08s;left:-50px;top:-50px';
  addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  addEventListener('mousedown', () => c.style.transform = 'translate(-50%,-50%) scale(.75)', true);
  addEventListener('mouseup', () => c.style.transform = 'translate(-50%,-50%) scale(1)', true);
  (document.body || document.documentElement).appendChild(c); })();
"""


def ctx(b, name, cookie=True):
    c = b.new_context(viewport=SIZE, record_video_dir=str(RAW / f"_{name}"), record_video_size=SIZE, device_scale_factor=1)
    if cookie and SID:
        c.add_cookies([{"name": "vouch_session", "value": SID, "url": SITE}])
    c.add_init_script(CURSOR)
    return c


def finish(c, name):
    page = c.pages[0]
    path = page.video.path()
    c.close()
    RAW.mkdir(exist_ok=True)
    shutil.move(path, RAW / f"{name}.webm")
    shutil.rmtree(RAW / f"_{name}", ignore_errors=True)
    print("recorded", name)


class Snaps:
    """Screenshot timeline for blocks that mostly wait: Playwright's video only stores frames on repaint,
    so a still page would shrink to seconds. Frames every 0.5 s keep real time; assemble.py speeds it up visibly."""
    def __init__(self, page, name):
        self.page, self.name, self.dir, self.n = page, name, RAW / f"_{name}_snaps", 0
        shutil.rmtree(self.dir, ignore_errors=True); self.dir.mkdir(parents=True)

    def tick(self, seconds=0.5):
        end = time.time() + seconds
        self.page.screenshot(path=str(self.dir / f"{self.n:05d}.png")); self.n += 1
        time.sleep(max(0, end - time.time()))

    def hold(self, seconds):
        t = time.time()
        while time.time() - t < seconds:
            self.tick()

    def save(self):
        import imageio_ffmpeg
        r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-framerate", "2", "-i", str(self.dir / "%05d.png"),
                            "-c:v", "libvpx-vp9", "-b:v", "3M", "-pix_fmt", "yuv420p", str(RAW / f"{self.name}.webm")], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(r.stderr[-800:])
        shutil.rmtree(self.dir, ignore_errors=True)
        print("recorded", self.name, f"({self.n / 2:.0f}s of real time)")


def glide(page, sel, steps=25, click=True):
    box = page.locator(sel).first.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=steps)
    time.sleep(.35)
    if click:  # exactly one click, on the element itself (robust to a page that is still scrolling)
        page.locator(sel).first.click()
        time.sleep(.4)


def smooth_scroll(page, y, ms=1600):
    page.evaluate(f"window.scrollTo({{top: {y}, behavior: 'smooth'}})")
    time.sleep(ms / 1000)


# ---------------------------------------------------------------- blocks

def hero(b):
    c = ctx(b, "hero", cookie=False); p = c.new_page()
    p.goto(SITE + "/", wait_until="networkidle"); time.sleep(4)
    p.mouse.move(960, 700, steps=30); time.sleep(4)
    finish(c, "hero")


def lanes_status() -> tuple[int, int]:
    out = subprocess.run(LANES + ["status"], capture_output=True, text=True).stdout
    import re
    m = re.search(r"(\d+) agents? \((\d+) waiting\)", out)
    return (int(m[1]), int(m[2])) if m else (0, 0)


def lanes(b):
    """A fresh real collision: two Claude Code agents, same file, recorded on the Lanes board."""
    run_id = time.strftime("%H%M%S")
    dirs = {}
    for who in ("ana", "bea"):  # fresh checkouts of main: Lanes is already set up there
        d = LANES_RUN / f"{who}-{run_id}"
        subprocess.run(["git", "clone", "-q", "https://github.com/mfmatozza/vouch-demo.git", str(d)], check=True)
        subprocess.run(["git", "config", "user.name", f"{who.title()} (agent)"], cwd=d)
        subprocess.run(["git", "config", "user.email", f"{who}@vouch-demo.dev"], cwd=d)
        subprocess.run(LANES + ["init", "--user", who, "--no-commit"], cwd=d, capture_output=True)
        dirs[who] = d
    url = subprocess.run(LANES + ["app", "--print"], cwd=dirs["ana"], capture_output=True, text=True).stdout.strip().splitlines()[0]
    c = b.new_context(viewport=SIZE); p = c.new_page()
    p.goto(url); time.sleep(2)
    snaps = Snaps(p, "lanes"); snaps.hold(2)
    tasks = {
        "ana": "Task: in pricing.py, make subtotal() ignore items with a quantity of 0 or less. Add a test in tests/test_pricing.py. Keep it small.",
        "bea": "Task: in pricing.py, add a NEWYEAR20 code worth 20% off to discount(). Add a test in tests/test_pricing.py. Do not change other codes. Keep it small.",
    }
    claude = shutil.which("claude") or "claude"
    procs = [subprocess.Popen([claude, "-p", t, "--permission-mode", "acceptEdits"], cwd=dirs[who], stdin=subprocess.DEVNULL,
                              stdout=open(LANES_RUN / f"{who}-{run_id}.log", "w"), stderr=subprocess.STDOUT)
             for who, t in tasks.items()]
    t0, seen, waited = time.time(), False, False
    while time.time() - t0 < 300:  # follow the Lanes server, not the launcher: record until both agents are done
        agents, waiting = lanes_status()
        seen |= agents > 0
        waited |= waiting > 0
        if all(pr.poll() is not None for pr in procs):  # both agents' processes have really exited
            break
        snaps.tick()
    snaps.hold(3)
    snaps.save(); c.close()
    print("collision seen live:", waited)
    for who in dirs:
        print(who, (LANES_RUN / f"{who}-{run_id}.log").read_text(errors="replace")[-250:])


def run(b):
    """The repository page: Lanes provenance on each PR, click Run Vouch, watch it finish."""
    c = b.new_context(viewport=SIZE); c.add_cookies([{"name": "vouch_session", "value": SID, "url": SITE}]); c.add_init_script(CURSOR)
    p = c.new_page()
    p.goto(SITE + "/app#/gh/mfmatozza/vouch-demo", wait_until="networkidle"); time.sleep(2)
    snaps = Snaps(p, "run"); snaps.hold(3)
    target = p.locator(".pr.gh", has_text=RUN_PR)
    if not target.count():
        target = p.locator(".pr.gh").first
    btn = target.locator("button:has-text('Run Vouch'), button:has-text('Run again')")
    if btn.count():
        box = btn.first.bounding_box()
        for k in range(1, 7):  # glide the cursor in, frame by frame
            p.mouse.move(box["x"] + 40 * k / 6, box["y"] + 18 * k / 6 + (6 - k) * 30); snaps.tick(.25)
        btn.first.click(); snaps.hold(2)
    import httpx
    t0 = time.time()
    while time.time() - t0 < 600:  # ask the API, not the DOM: the page re-renders this row every few seconds
        try:
            rows = httpx.get(f"{SITE}/api/gh/mfmatozza/vouch-demo/pulls", cookies={"vouch_session": SID}, timeout=30).json()["pulls"]
            st = next(((r["vouch"] or {}).get("status") for r in rows if RUN_PR in r["title"]), None)
        except Exception:
            st = None
        if st in ("ready", "failed"):
            break
        for _ in range(4):
            snaps.tick()
    snaps.hold(6)  # the page polls every 4 s: let the finished row appear
    snaps.save(); c.close()


def github(b):
    """GitHub's own page for the PR that broke a test: open the red check, it says why."""
    c = b.new_context(viewport={"width": 1440, "height": 810}, record_video_dir=str(RAW / "_github"), record_video_size={"width": 1440, "height": 810})
    c.add_init_script(CURSOR)
    p = c.new_page()
    p.goto("https://github.com/mfmatozza/vouch-demo/pull/2", wait_until="domcontentloaded"); time.sleep(3)
    x = p.locator("svg.octicon-x:visible").first
    box = x.bounding_box()
    p.mouse.move(box["x"] + 8, box["y"] + 8, steps=35); time.sleep(.6)
    x.click(); time.sleep(5)
    finish(c, "github")


def review(b, pr="mfmatozza~vouch-demo~5"):
    """EasyReview with a second reviewer live on the page; stop on the claim mutation proof rejected."""
    luca = b.new_context(viewport=SIZE); lp = luca.new_page()
    lp.goto(f"{SITE}/review?as=Luca#/pr/{pr}/4", wait_until="networkidle")
    c = ctx(b, "review"); p = c.new_page()
    p.goto(f"{SITE}/review#/pr/{pr}", wait_until="networkidle"); time.sleep(3.5)

    def approve(pause):
        time.sleep(pause)
        glide(p, ".actbar button:has-text('Looks right')", steps=18)
        time.sleep(1.6)

    approve(2.5)   # Guardrail
    approve(2.5)   # what this change does
    # the claim whose proof failed: show why, and the lines that went back on the reading list
    time.sleep(1.5)
    bad = p.locator(".checks li", has_text="did not make any test fail")
    if bad.count():
        box = bad.first.bounding_box(); p.mouse.move(box["x"] + 200, box["y"] + 10, steps=30)
        time.sleep(3)
        p.evaluate("window.scrollBy({top: 340, behavior: 'smooth'})"); time.sleep(3)
        p.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})"); time.sleep(1.2)
    approve(0.5)
    for _ in range(6):  # the rest, briskly
        time.sleep(1.4)
        if p.locator(".pane h2").first.inner_text().startswith("Sign this"):
            break
        glide(p, ".actbar button:has-text('Looks right')", steps=10)
    time.sleep(2.5)
    finish(c, "review"); luca.close()


def sign(b, pr="mfmatozza~vouch-demo~5", number=5):
    c = ctx(b, "sign"); p = c.new_page()
    p.goto(f"{SITE}/review#/pr/{pr}", wait_until="networkidle"); time.sleep(2)
    p.locator(".step").last.click(); time.sleep(2.5)
    glide(p, "#risk")
    assert p.evaluate("document.activeElement && document.activeElement.id") == "risk", "risk box not focused"
    p.keyboard.type("Small, isolated change; all existing tests kept and every proven line survived mutation.", delay=28)
    time.sleep(.8)
    glide(p, ".actbar button:has-text('Approve and merge')")
    t0 = time.time()
    while time.time() - t0 < 60 and "Merged on GitHub" not in p.locator(".pane").inner_text():
        time.sleep(1)
    time.sleep(3)
    p.goto(f"https://github.com/mfmatozza/vouch-demo/pull/{number}", wait_until="domcontentloaded"); time.sleep(3)
    p.evaluate("window.scrollTo({top: document.body.scrollHeight - 2200, behavior: 'smooth'})"); time.sleep(5)
    finish(c, "sign")


def results(b):
    c = ctx(b, "results", cookie=False); p = c.new_page()
    p.goto(SITE + "/#results", wait_until="networkidle"); time.sleep(1)
    p.evaluate("document.querySelectorAll('.reveal').forEach(e => e.classList.add('in'))")
    p.evaluate("document.querySelector('#results').scrollIntoView()"); time.sleep(4)
    smooth_scroll(p, p.evaluate("document.querySelector('.e2e').getBoundingClientRect().top + scrollY - 120"), 2500); time.sleep(4)
    finish(c, "results")


BLOCKS = {"hero": hero, "lanes": lanes, "run": run, "github": github, "review": review, "sign": sign, "results": results}

if __name__ == "__main__":
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME)
        for name in sys.argv[1:] or BLOCKS:
            BLOCKS[name](browser)
        browser.close()
