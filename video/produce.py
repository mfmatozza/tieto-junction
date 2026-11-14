"""Produce the 2:00 demo: real screen recordings, directed. Stage, camera zooms, time remapping, callouts, chapters.

    python video/produce.py                          -> video/out/vouch-film.mp4 (face slots as placeholders, silent)
    python video/produce.py faceA.mp4 faceB.mp4 [voice.m4a]

Every frame comes from video/raw/*.webm (recorded from the live product by video/record.py). Nothing is mocked:
the camera only moves over real footage. Parts that run faster than real time carry a "sped up" badge.
"""
import math
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FF = imageio_ffmpeg.get_ffmpeg_exe()
HERE = Path(__file__).parent
RAW, OUT = HERE / "raw", HERE / "out"
W, H, FPS = 1920, 1080, 30
SW, SH = 1440, 810                      # source frame size (recordings)
MIN_ZOOM = 0.66                         # tightest camera framing, as a share of the screen
CW, CH = 1440, 810                      # screen size on stage: the recordings' native size, so no upscaling blur
BAR = 44                                # browser bar height
WX, WY = (W - CW) // 2, 92              # window position; subtitles live in the band below it
NAVY, GREEN, TEXT, MUTED = (15, 31, 77), (21, 128, 61), (11, 21, 51), (75, 86, 117)
FONT = "C:/Windows/Fonts/segoeui.ttf"
FONT_SB = "C:/Windows/Fonts/seguisb.ttf"
FONT_B = "C:/Windows/Fonts/segoeuib.ttf"


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(FONT_B, size)


F_CHIP, F_CHIP_N = font(FONT_SB, 26), font(FONT_B, 26)
F_CALL, F_URL, F_BADGE = font(FONT_B, 44), font(FONT, 20), font(FONT_SB, 20)
F_SLATE_H, F_SLATE = font(FONT_B, 40), font(FONT, 40)

# ---------------------------------------------------------------- the direction
# segments: (source start s, source end s, output seconds). zooms: (output s, cx, cy, size) as fractions of the frame.
# callouts: (from s, to s, text). Times inside a block's own output timeline.
BLOCKS = [
    dict(name="FACE_A", seconds=12, lines=["AI agents now write thousands of lines a day. Nobody can review that.",
                                            "So teams either slow the AI down, or merge code no one has read.", "We built a third option."]),
    dict(name="hero", chapter="Vouch", url="vouch-review-hazel.vercel.app",
         segments=[(0.4, 8.4, 8)], zooms=[(0, .5, .5, 1), (1.2, .5, .5, 1), (4.5, .5, .36, .66), (8, .5, .38, .62)],
         callouts=[(4.8, 8, "Agents write. Vouch proves. Humans sign.")]),
    dict(name="lanes", chapter="01  ·  Lanes", url="Lanes  ·  live coordination board",
         segments=[(5.5, 9.5, 3.5), (9.5, 14.8, 9.5), (14.8, 19.5, 5)],
         zooms=[(0, .5, .5, 1), (1.6, .36, .2, .62), (11.5, .36, .2, .62), (13.2, .27, .74, .5), (16.2, .27, .74, .5), (18, .5, .5, 1)],
         callouts=[(4.2, 10.8, "Two agents, one file: one holds the lease, the other waits"), (13.4, 17.6, "No overwrites. No conflicting branches.")]),
    dict(name="run", chapter="02  ·  Guardrail", url="vouch-review-hazel.vercel.app/app#/gh/mfmatozza/vouch-demo",
         segments=[(0, 2.5, 2), (5.5, 82, 7.5), (82, 90, 4.5)], snaps=True,
         zooms=[(0, .5, .5, 1), (1.6, .5, .5, 1), (3, .5, .58, .8), (9.2, .5, .58, .8), (10.6, .5, .66, .76), (14, .5, .66, .74)],
         callouts=[(2.6, 9, "One click: a worker runs your existing tests, before and after"), (10.6, 14, "Written by claude-code through Lanes  ·  mutation proof")]),
    dict(name="github", chapter="02  ·  Guardrail", url="github.com/mfmatozza/vouch-demo/pull/2",
         segments=[(2.4, 12.8, 8)], zooms=[(0, .5, .5, 1), (2.2, .5, .5, 1), (4.2, .5, .62, .62), (8, .5, .62, .58)],
         callouts=[(4.4, 8, "Something broke? Blocked on GitHub. No human time spent.")]),
    dict(name="review", chapter="03  ·  Checkpoint  ·  EasyReview", url="vouch-review-hazel.vercel.app/review#/pr/5",
         segments=[(1.8, 8.6, 3.5), (10.2, 17.4, 5), (17.4, 28.4, 9.5), (28.4, 41.8, 6)],
         zooms=[(0, .6, .45, .78), (3.2, .6, .45, .78), (4.4, .62, .5, .8), (8.2, .62, .5, .8), (9.2, .62, .6, .78), (16.5, .62, .6, .78),
                (18.2, .5, .5, 1), (24, .5, .5, .96)],
         callouts=[(4.6, 8.4, "Lanes records which agent wrote it"), (9.6, 17.4, "Vouch broke this line on purpose. No test noticed: a person reads it."),
                   (21.6, 24, "Your team reviews together, live")]),
    dict(name="sign", chapter="04  ·  Sign and merge", url="vouch-review-hazel.vercel.app/review#/pr/4",
         segments=[(6.2, 15.4, 4.6), (15.4, 21, 3.4)], zooms=[(0, .6, .62, .72), (4.4, .6, .62, .72), (5, .55, .42, .76), (8, .55, .42, .74)],
         callouts=[(0.4, 4.4, "A named owner signs and writes down the risk", "top")]),
    dict(name="merged", chapter="04  ·  Sign and merge", url="github.com/mfmatozza/vouch-demo/pull/4",
         segments=[(5.6, 10.1, 4)], zooms=[(0, .42, .4, .7), (4, .42, .4, .64)],
         callouts=[(0.3, 4, "Review record on GitHub. Merged.")]),
    dict(name="results", chapter="05  ·  Results", url="vouch-review-hazel.vercel.app/#results",
         segments=[(3.3, 8.2, 4.6), (8.2, 15.4, 7.4)],
         zooms=[(0, .5, .5, 1), (1.4, .5, .5, .76), (4.6, .5, .5, .74), (6.2, .5, .34, .86), (8.6, .5, .34, .86), (9.8, .7, .32, .68), (12, .7, .32, .66)],
         callouts=[(1.6, 4.6, "76% fewer lines to read  ·  every existing test kept"), (9.4, 12, "10 of 10 planted bugs stopped")]),
    dict(name="FACE_B", seconds=12, lines=["AI writes the code. Vouch makes sure a human can stand behind it.", "Built on Lanes, Claude and Aiven."]),
]

# ---------------------------------------------------------------- stage


def lerp(a, b, t):
    return a + (b - a) * t


def ease(t):
    return 4 * t * t * t if t < .5 else 1 - (-2 * t + 2) ** 3 / 2


def background() -> Image.Image:
    bg = Image.new("RGB", (W, H))
    px = bg.load()
    top, bot = (238, 242, 251), (214, 224, 244)
    for y in range(H):
        c = tuple(int(lerp(top[i], bot[i], y / H)) for i in range(3))
        for x in range(W):
            px[x, y] = c
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([W * .15, H * .55, W * .85, H * 1.5], fill=120)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    bg = Image.composite(Image.new("RGB", (W, H), (190, 205, 238)), bg, glow)
    return bg


def window_layers():
    """Shadow, frame (with bar) and the rounded mask for the screen area."""
    shadow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shadow).rounded_rectangle([WX + 10, WY + 26, WX + CW - 10, WY + BAR + CH + 30], 26, fill=110)
    shadow = shadow.filter(ImageFilter.GaussianBlur(28))
    mask = Image.new("L", (CW, BAR + CH), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, CW - 1, BAR + CH - 1], 18, fill=255)
    return shadow, mask


def bar(url: str) -> Image.Image:
    b = Image.new("RGB", (CW, BAR), (248, 249, 252))
    d = ImageDraw.Draw(b)
    for i, c in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
        d.ellipse([18 + i * 22, 16, 30 + i * 22, 28], fill=c)
    d.rounded_rectangle([CW // 2 - 360, 9, CW // 2 + 360, 35], 13, fill=(236, 239, 245))
    tw = d.textlength(url, font=F_URL)
    d.text((CW // 2 - tw / 2, 10), url, font=F_URL, fill=MUTED)
    d.line([0, BAR - 1, CW, BAR - 1], fill=(222, 226, 235))
    return b


def chip(text: str, alpha: float) -> tuple[Image.Image, Image.Image]:
    d0 = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    w = int(d0.textlength(text, font=F_CHIP)) + 44
    img = Image.new("RGB", (w, 50), NAVY)
    d = ImageDraw.Draw(img)
    d.text((22, 8), text, font=F_CHIP, fill=(255, 255, 255))
    m = Image.new("L", (w, 50), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, 49], 25, fill=int(255 * alpha))
    return img, m


def callout(text: str, alpha: float, lift: float) -> tuple[Image.Image, Image.Image, int]:
    d0 = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    tw = int(d0.textlength(text, font=F_CALL))
    w, h = tw + 72, 84
    img = Image.new("RGB", (w, h), NAVY)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([18, 30, 30, 54], 6, fill=(134, 239, 172))
    d.text((44, 14), text, font=F_CALL, fill=(255, 255, 255))
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], 22, fill=int(240 * alpha))
    return img, m, int(lift)


def badge(text: str) -> tuple[Image.Image, Image.Image]:
    d0 = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    w = int(d0.textlength(text, font=F_BADGE)) + 28
    img = Image.new("RGB", (w, 30), (254, 243, 199))
    ImageDraw.Draw(img).text((14, 2), text, font=F_BADGE, fill=(146, 64, 14))
    m = Image.new("L", (w, 30), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, 29], 15, fill=255)
    return img, m


# ---------------------------------------------------------------- source frames, retimed by ffmpeg


def retimed(blk: dict):
    """Yield source frames (PIL, SWxSH) at the output frame rate, following the block's segments."""
    src = RAW / f"{blk['name']}.webm"
    parts, labels = [], []
    for i, (a, b, out) in enumerate(blk["segments"]):
        speed = (b - a) / out
        parts.append(f"[0:v]trim=start={a}:end={b},setpts=(PTS-STARTPTS)/{speed:.5f},fps=60,scale={SW}:{SH}[s{i}]")
        labels.append(f"[s{i}]")
    graph = ";".join(parts) + f";{''.join(labels)}concat=n={len(labels)}:v=1:a=0,framerate=fps={FPS}:interp_start=0:interp_end=255[v]"
    total = sum(s[2] for s in blk["segments"])
    p = subprocess.Popen([FF, "-v", "error", "-i", str(src), "-filter_complex", graph, "-map", "[v]", "-t", str(total),
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    n, last = int(round(total * FPS)), None
    for _ in range(n):
        buf = p.stdout.read(SW * SH * 3)
        if len(buf) < SW * SH * 3:
            yield last  # hold the last frame if the source ran short
            continue
        last = Image.frombytes("RGB", (SW, SH), buf)
        yield last
    p.stdout.close(); p.wait()


def speed_at(blk, t):
    acc = 0
    for a, b, out in blk["segments"]:
        if t < acc + out:
            return (b - a) / out
        acc += out
    return 1.0


def zoom_at(blk, t):
    keys = blk.get("zooms") or [(0, .5, .5, 1)]
    if t <= keys[0][0]:
        k = keys[0]
    elif t >= keys[-1][0]:
        k = keys[-1]
    else:
        for k0, k1 in zip(keys, keys[1:]):
            if k0[0] <= t <= k1[0]:
                u = ease((t - k0[0]) / max(1e-6, k1[0] - k0[0]))
                k = (t, lerp(k0[1], k1[1], u), lerp(k0[2], k1[2], u), lerp(k0[3], k1[3], u))
                break
    _, cx, cy, s = k
    s = max(s, MIN_ZOOM)  # never closer than this: close-ups stay comfortable
    w, h = SW * s, SH * s
    x = min(max(cx * SW - w / 2, 0), SW - w)
    y = min(max(cy * SH - h / 2, 0), SH - h)
    return x, y, w, h


# ---------------------------------------------------------------- render


def render(enc, faces):
    bg = background()
    shadow, mask = window_layers()
    shadow_rgb = Image.new("RGB", (W, H), (60, 75, 120))
    stage = Image.composite(shadow_rgb, bg, shadow)
    for blk in BLOCKS:
        if blk["name"].startswith("FACE"):
            render_face(enc, blk, faces.get(blk["name"]), bg)
            continue
        url_bar = bar(blk["url"])
        total = sum(s[2] for s in blk["segments"])
        print(f"{blk['name']}: {total}s", flush=True)
        for i, frame in enumerate(retimed(blk)):
            t = i / FPS
            x, y, w, h = zoom_at(blk, t)
            screen = frame.resize((CW, CH), Image.BICUBIC, box=(x, y, x + w, y + h))  # sub-pixel: no stepping, no shake
            win = Image.new("RGB", (CW, BAR + CH))
            win.paste(url_bar, (0, 0)); win.paste(screen, (0, BAR))
            canvas = stage.copy()
            enter = ease(min(1, t / .45))  # window rises in at the start of each block
            canvas.paste(win, (WX, WY + int((1 - enter) * 40)), mask)
            # chapter chip
            ci, cm = chip(blk["chapter"], min(1, t / .3))
            canvas.paste(ci, (WX, 48), cm)
            # sped-up badge, only while this part is actually faster than real time
            sp = speed_at(blk, t)
            if sp >= 1.5:
                bi, bm = badge(f"sped up  ×{sp:.0f}")
                canvas.paste(bi, (WX + CW - bi.width - 18, WY + 7), bm)
            # callouts
            for a, b, text, *where in blk.get("callouts", []):
                if a <= t <= b:
                    fin, fout = min(1, (t - a) / .35), min(1, (b - t) / .3)
                    al = ease(min(fin, fout))
                    img, m, _ = callout(text, al, 0)
                    cx = (W - img.width) // 2
                    cy = (WY + BAR + 24 if where == ["top"] else WY + BAR + CH - 120) + int((1 - ease(fin)) * 24)
                    canvas.paste(img, (cx, cy), m)
            enc.stdin.write(canvas.tobytes())


def render_face(enc, blk, clip, bg):
    n = blk["seconds"] * FPS
    if clip:
        p = subprocess.Popen([FF, "-v", "error", "-i", str(clip), "-t", str(blk["seconds"]), "-vf",
                              f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        last = None
        for _ in range(n):
            buf = p.stdout.read(W * H * 3)
            if len(buf) == W * H * 3:
                last = buf
            enc.stdin.write(last or bg.tobytes())
        p.stdout.close(); p.wait()
        return
    slate = bg.copy()
    d = ImageDraw.Draw(slate)
    d.rounded_rectangle([WX, WY, WX + CW, WY + BAR + CH], 18, outline=NAVY, width=3)
    title = "YOUR FACE HERE  ·  " + ("0:00 to 0:12" if blk["name"] == "FACE_A" else "1:48 to 2:00")
    tw = d.textlength(title, font=F_SLATE_H)
    d.text(((W - tw) / 2, 380), title, font=F_SLATE_H, fill=GREEN)
    for k, line in enumerate(blk["lines"]):
        lw = d.textlength(line, font=F_SLATE)
        d.text(((W - lw) / 2, 470 + k * 64), line, font=F_SLATE, fill=TEXT)
    raw = slate.tobytes()
    for _ in range(n):
        enc.stdin.write(raw)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    faces = {"FACE_A": Path(sys.argv[1]) if len(sys.argv) > 1 else None, "FACE_B": Path(sys.argv[2]) if len(sys.argv) > 2 else None}
    voice = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    silent = OUT / "vouch-film-video.mp4"
    enc = subprocess.Popen([FF, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                            "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", str(silent)], stdin=subprocess.PIPE)
    render(enc, faces)
    enc.stdin.close(); enc.wait()
    final = OUT / "vouch-film.mp4"
    total = sum(b.get("seconds") or sum(s[2] for s in b["segments"]) for b in BLOCKS)
    inputs = ["-i", str(silent)]
    face_a = faces["FACE_A"]
    # audio: face clips keep their own sound; the voice-over runs under the screen part
    filters, mix = [], []
    if face_a:
        inputs += ["-i", str(face_a)]; filters.append(f"[1:a]atrim=0:12,apad[fa]"); mix.append("[fa]")
    if faces["FACE_B"]:
        idx = len(inputs) // 2
        inputs += ["-i", str(faces["FACE_B"])]; filters.append(f"[{idx}:a]atrim=0:12,adelay=108000|108000,apad[fb]"); mix.append("[fb]")
    if voice:
        idx = len(inputs) // 2
        inputs += ["-i", str(voice)]; filters.append(f"[{idx}:a]atrim=0:96,adelay=12000|12000,apad[vo]"); mix.append("[vo]")
    if mix:
        graph = ";".join(filters) + f";{''.join(mix)}amix=inputs={len(mix)}:duration=longest:normalize=0,atrim=0:{total}[a]"
        subprocess.run([FF, "-y", "-v", "error", *inputs, "-filter_complex", graph, "-map", "0:v", "-map", "[a]",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", str(total), str(final)], check=True)
    else:
        subprocess.run([FF, "-y", "-v", "error", "-i", str(silent), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                        "-c:v", "copy", "-c:a", "aac", "-shortest", str(final)], check=True)
    print(final)
