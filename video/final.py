"""Final cut: the directed film fitted to the real voice-over, with the face clips and burned-in subtitles.

    python video/final.py   -> video/out/vouch-final.mp4

Inputs in video/in/: zip/<face A>.mp4, zip/<face B>.mp4, voice-0..6.mp4, transcripts.json (word timings).
Each screen block is stretched or shrunk to its voice clip; zooms and callouts move with it.
Subtitles use the script's exact words (docs/VIDEO.md), timed from the speech recogniser's word timings.
"""
import json
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

import produce as P

IN = P.HERE / "in"
FACE_A, FACE_B = sorted((IN / "zip").glob("*.mp4"))
PRE, POST = 0.35, 0.45   # breathing room around each voice clip

# block(s) -> voice file -> the words as written in the script (the one change the speaker made is kept)
VOICE = [
    (["hero"], "voice-6", "This is Vouch. Agents write. Vouch proves. Humans sign."),
    (["lanes"], "voice-5", "It starts before any code exists. With Lanes, built in house, every agent takes a lease on a file before it edits. "
                           "Here two Claude Code agents plan the same files at the same second. One holds the lease, the other waits, "
                           "then builds on top with context. No conflicting branches."),
    (["run"], "voice-4", "Each change becomes a pull request, and Vouch knows which agent wrote it. One click runs Vouch: "
                         "a worker fed by Aiven Kafka runs your existing tests before and after."),
    (["github"], "voice-3", "If anything that used to work breaks, the pull request is blocked on GitHub before a person looks."),
    (["review"], "voice-2", "Otherwise the AI explains the change as claims, and plain code checks every one: the lines exist, "
                            "the quote is in the issue, the test passed. Then Vouch breaks the code on purpose. Here one break went unnoticed, "
                            "so that line goes back to a person. The team reviews what's left, together, live."),
    (["sign", "merged"], "voice-1", "A named owner signs and writes down the risk. Vouch posts the review record and merges on GitHub, under their name."),
    (["results"], "voice-0", "On Tieto's repository: 76 percent fewer lines to read, every existing test kept. We planted ten bugs in our demo repo: "
                             "Vouch stopped all ten. Three blocked, seven put in front of a person."),
]
FACE_TEXT = {
    "FACE_A": "AI agents now write thousands of lines a day. Nobody can review that. So teams either slow the AI down, "
              "or merge code no one has read. We built a third option.",
    "FACE_B": "AI writes the code. Vouch makes sure a human can stand behind it. Built on Lanes, Claude and Aiven.",
}
F_SUB = P.font(P.FONT_SB, 38)


def dur(path: Path) -> float:
    err = subprocess.run([P.FF, "-i", str(path), "-f", "null", "-"], capture_output=True, text=True).stderr
    h, m, sec = re.findall(r"time=(\d+):(\d+):([\d.]+)", err)[-1]
    return int(h) * 3600 + int(m) * 60 + float(sec)


def chunks(script: str, words: list[dict], offset: float) -> list[tuple[float, float, str]]:
    """Script words, timed by the recogniser's words (mapped by position), cut into short readable lines."""
    sw = script.split()
    n = max(1, len(words))
    times = [words[min(n - 1, round(i * n / len(sw)))] for i in range(len(sw))]
    out, cur, start = [], [], None
    for i, w in enumerate(sw):
        if not cur:
            start = times[i]["s"]
        cur.append(w)
        line = " ".join(cur)
        if len(cur) >= 7 or len(line) > 44 or w[-1] in ".:," and len(cur) >= 3 or i == len(sw) - 1:
            end = times[i]["e"] + 0.12
            out.append((offset + start, offset + end, line))
            cur = []
    for k in range(len(out) - 1):  # a line stays until the next one starts (no flicker), never overlapping it
        a, b, t = out[k]
        out[k] = (a, min(out[k + 1][0], max(b, b + 0.4)), t)
    return out


def scale_block(blk: dict, k: float) -> dict:
    b = dict(blk)
    b["segments"] = [(a, e, o * k) for a, e, o in blk["segments"]]
    b["zooms"] = [(t * k, *rest) for t, *rest in blk.get("zooms", [])]
    b["callouts"] = [(a * k, e * k, *rest) for a, e, *rest in blk.get("callouts", [])]
    return b


def plan():
    trans = json.load(open(IN / "transcripts.json"))
    by_name = {b["name"]: b for b in P.BLOCKS}
    blocks, audio, subs, t = [], [], [], 0.0
    da = dur(FACE_A)
    blocks.append({"name": "FACE_A", "clip": FACE_A, "seconds": da})
    audio.append((FACE_A, 0.0, da))
    subs += chunks(FACE_TEXT["FACE_A"], trans[str(FACE_A).replace("/", "\\")] if str(FACE_A).replace("/", "\\") in trans else next(v for k, v in trans.items() if FACE_A.name in k), 0.0)
    t = da
    for names, vfile, text in VOICE:
        vpath = IN / f"{vfile}.mp4"
        dv = dur(vpath)
        group = [by_name[n] for n in names]
        old = sum(sum(s[2] for s in g["segments"]) for g in group)
        new = dv + PRE + POST
        for g in group:
            blocks.append(scale_block(g, new / old))
        audio.append((vpath, t + PRE, dv))
        subs += chunks(text, next(v for k, v in trans.items() if k.endswith(f"{vfile}.mp4")), t + PRE)
        t += new
    db = dur(FACE_B)
    blocks.append({"name": "FACE_B", "clip": FACE_B, "seconds": db})
    audio.append((FACE_B, t, db))
    subs += chunks(FACE_TEXT["FACE_B"], next(v for k, v in trans.items() if FACE_B.name in k), t)
    t += db
    return blocks, audio, subs, t


def draw_sub(canvas: Image.Image, subs, gt: float, face: bool):
    for a, b, text in subs:
        if a <= gt < b:
            d = ImageDraw.Draw(canvas)
            tw = d.textlength(text, font=F_SUB)
            y = P.WY + P.BAR + P.CH + 30 if not face else P.H - 120
            x = (P.W - tw) / 2
            d.rounded_rectangle([x - 22, y - 8, x + tw + 22, y + 54], 14, fill=(11, 21, 51))
            d.text((x, y), text, font=F_SUB, fill=(255, 255, 255))
            return


def render(enc, blocks, subs):
    bg = P.background()
    shadow, mask = P.window_layers()
    stage = Image.composite(Image.new("RGB", (P.W, P.H), (60, 75, 120)), bg, shadow)
    gt0 = 0.0
    for blk in blocks:
        if blk["name"].startswith("FACE"):
            n = int(round(blk["seconds"] * P.FPS))
            p = subprocess.Popen([P.FF, "-v", "error", "-i", str(blk["clip"]), "-vf",
                                  f"scale={P.W}:{P.H}:force_original_aspect_ratio=increase,crop={P.W}:{P.H},fps={P.FPS}",
                                  "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
            last = None
            for i in range(n):
                buf = p.stdout.read(P.W * P.H * 3)
                if len(buf) == P.W * P.H * 3:
                    last = Image.frombytes("RGB", (P.W, P.H), buf)
                frame = last.copy() if last else bg.copy()
                draw_sub(frame, subs, gt0 + i / P.FPS, face=True)
                enc.stdin.write(frame.tobytes())
            p.stdout.close(); p.wait()
            gt0 += n / P.FPS
            print(blk["name"], f"{blk['seconds']:.1f}s", flush=True)
            continue
        url_bar = P.bar(blk["url"])
        n_out = 0
        for i, frame in enumerate(P.retimed(blk)):
            t = i / P.FPS
            x, y, w, h = P.zoom_at(blk, t)
            screen = frame.resize((P.CW, P.CH), Image.BICUBIC, box=(x, y, x + w, y + h))  # sub-pixel: steady camera
            win = Image.new("RGB", (P.CW, P.BAR + P.CH))
            win.paste(url_bar, (0, 0)); win.paste(screen, (0, P.BAR))
            canvas = stage.copy()
            enter = P.ease(min(1, t / .45))
            canvas.paste(win, (P.WX, P.WY + int((1 - enter) * 30)), mask)
            ci, cm = P.chip(blk["chapter"], min(1, t / .3))
            canvas.paste(ci, (P.WX, 24), cm)
            sp = P.speed_at(blk, t)
            if sp >= 1.5:
                bi, bm = P.badge(f"sped up  ×{sp:.0f}")
                canvas.paste(bi, (P.WX + P.CW - bi.width - 18, P.WY + 7), bm)
            for a, b, text, *where in blk.get("callouts", []):
                if a <= t <= b:
                    fin, fout = min(1, (t - a) / .35), min(1, (b - t) / .3)
                    img, m, _ = P.callout(text, P.ease(min(fin, fout)), 0)
                    cy = (P.WY + P.BAR + 24 if where == ["top"] else P.WY + P.BAR + P.CH - 120) + int((1 - P.ease(fin)) * 24)
                    canvas.paste(img, ((P.W - img.width) // 2, cy), m)
            draw_sub(canvas, subs, gt0 + t, face=False)
            enc.stdin.write(canvas.tobytes())
            n_out += 1
        gt0 += n_out / P.FPS
        print(blk["name"], f"{n_out / P.FPS:.1f}s", flush=True)


if __name__ == "__main__":
    blocks, audio, subs, total = plan()
    print(f"total {total:.1f}s, {len(subs)} subtitle lines")
    silent = P.OUT / "vouch-final-video.mp4"
    enc = subprocess.Popen([P.FF, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{P.W}x{P.H}", "-r", str(P.FPS),
                            "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", str(silent)],
                           stdin=subprocess.PIPE)
    render(enc, blocks, subs)
    enc.stdin.close(); enc.wait()
    # one audio track: each source placed at its start time, levels evened out
    inputs, filters, labels = ["-i", str(silent)], [], []
    for k, (src, start, length) in enumerate(audio, 1):
        inputs += ["-i", str(src)]
        ms = int(start * 1000)
        filters.append(f"[{k}:a]atrim=0:{length:.2f},aresample=48000,pan=stereo|c0=c0|c1=c0,loudnorm=I=-16:TP=-1.5:LRA=11,adelay={ms}|{ms},apad[a{k}]")
        labels.append(f"[a{k}]")
    graph = ";".join(filters) + f";{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0,atrim=0:{total:.2f}[a]"
    final = P.OUT / "vouch-final.mp4"
    subprocess.run([P.FF, "-y", "-v", "error", *inputs, "-filter_complex", graph, "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.2f}", str(final)], check=True)
    srt = P.OUT / "vouch-final.srt"
    fmt = lambda x: f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{int(x % 60):02d},{int(x * 1000 % 1000):03d}"
    srt.write_text("".join(f"{i}\n{fmt(a)} --> {fmt(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(subs, 1)), encoding="utf-8")
    print(final, srt)
