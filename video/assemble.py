"""Cut the recorded blocks to their time budget and join them with the two face slots: one 2:00 video.

    python video/assemble.py                 -> video/out/vouch-demo.mp4 (silent, face slots as placeholders)
    python video/assemble.py faceA.mp4 faceB.mp4 -> same, with your clips in the slots (their audio kept)
    python video/assemble.py faceA.mp4 faceB.mp4 voice.m4a -> plus your voice-over under the screen part (0:12 to 1:48)

A block longer than its slot is sped up evenly, and says so on screen ("sped up x4"): nothing pretends to be faster than it is.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()  # a current ffmpeg; the system one is too old

HERE = Path(__file__).parent
RAW, OUT = HERE / "raw", HERE / "out"
FONT = "C\\:/Windows/Fonts/segoeui.ttf"
FONT_B = "C\\:/Windows/Fonts/segoeuib.ttf"

# (name, seconds, caption shown bottom-left). Order = the script in docs/VIDEO.md
TIMELINE = [
    ("FACE_A", 12, ""),
    ("hero", 8, "vouch-review-hazel.vercel.app", "head"),
    ("lanes", 18, "Lanes board: two Claude Code agents, same file, live"),
    ("run", 14, "Run Vouch: Aiven Kafka job, worker runs the tests"),
    ("github", 8, "GitHub: vouch/review blocks the pull request", "tail"),
    ("review", 24, "EasyReview: claims checked by code, mutation proof"),
    ("sign", 8, "Sign-off: the owner accepts the risk"),
    ("merged", 4, "Merged on GitHub, with the review record", "tail"),
    ("results", 12, "Measured on real changes", "tail"),
    ("FACE_B", 12, ""),
]
FACE_TEXT = {
    "FACE_A": ["YOUR FACE  ·  0:00 to 0:12",
               "AI agents now write thousands of lines a day. Nobody can review that.",
               "So teams either slow the AI down, or merge code no one has read.",
               "We built a third option."],
    "FACE_B": ["YOUR FACE  ·  1:48 to 2:00",
               "AI writes the code. Vouch makes sure a human can stand behind it.",
               "Built on Lanes, Claude and Aiven."],
}


def dur(p: Path) -> float:
    """Decode the whole file: browser recordings often carry no duration in their header."""
    err = subprocess.run([FF, "-i", str(p), "-f", "null", "-"], capture_output=True, text=True).stderr
    h, m, s = re.findall(r"time=(\d+):(\d+):([\d.]+)", err)[-1]
    return int(h) * 3600 + int(m) * 60 + float(s)


def esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace(",", "\\,")


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr[-1500:])


def slate(name: str, secs: int, out: Path) -> None:
    lines = FACE_TEXT[name]
    draws = [f"drawtext=fontfile='{FONT_B}':text='{esc(lines[0])}':fontcolor=0x86efac:fontsize=40:x=(w-text_w)/2:y=330"]
    for i, l in enumerate(lines[1:]):
        draws.append(f"drawtext=fontfile='{FONT}':text='{esc(l)}':fontcolor=white:fontsize=44:x=(w-text_w)/2:y={430 + i * 72}")
    run([FF, "-y", "-f", "lavfi", "-i", f"color=c=0x0f1f4d:s=1920x1080:r=30:d={secs}", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-vf", ",".join(draws), "-t", str(secs), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)])


def face(clip: Path, secs: int, out: Path) -> None:
    run([FF, "-y", "-i", str(clip), "-t", str(secs), "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", str(out)])


def block(name: str, secs: int, caption: str, out: Path, mode: str = "speed") -> None:
    """mode: speed (events over time, sped up and labelled), head / tail (a still page: keep the start / the end)."""
    src = RAW / f"{name}.webm"
    d = dur(src)
    speed = max(1.0, (d - 0.5) / secs) if mode == "speed" else 1.0
    start = max(0.0, d - secs - 0.3) if mode == "tail" else 0.0
    vf = [f"trim=start={start:.2f}", "setpts=PTS-STARTPTS", f"setpts=PTS/{speed:.4f}", "fps=30", "scale=1920:1080"]
    tag = caption + (f"   ·   sped up x{speed:.0f}" if speed >= 1.5 else "")
    vf.append(f"drawtext=fontfile='{FONT}':text='{esc(tag)}':fontcolor=white:fontsize=26:x=56:y=h-84"
              ":box=1:boxcolor=0x0f1f4d@0.85:boxborderw=16")  # the box fits the text
    run([FF, "-y", "-i", str(src), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-vf", ",".join(vf),
         "-t", str(secs), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)])
    print(f"{name}: {d:.1f}s recorded -> {secs}s {mode}{' (x%.1f)' % speed if speed > 1.01 else ''}")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    faces = {"FACE_A": Path(sys.argv[1]) if len(sys.argv) > 1 else None, "FACE_B": Path(sys.argv[2]) if len(sys.argv) > 2 else None}
    parts, t, marks = [], 0, []
    for name, secs, cap, *mode in TIMELINE:
        part = OUT / f"part-{len(parts):02d}-{name}.mp4"
        if name.startswith("FACE"):
            face(faces[name], secs, part) if faces[name] else slate(name, secs, part)
        else:
            block(name, secs, cap, part, *(mode or ["speed"]))
        parts.append(part)
        marks.append({"part": name, "start": t, "end": t + secs})
        t += secs
    (OUT / "list.txt").write_text("".join(f"file '{p.name}'\n" for p in parts))
    final = OUT / "vouch-demo.mp4"
    run([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(OUT / "list.txt"), "-c", "copy", str(final)])
    (OUT / "timeline.json").write_text(json.dumps(marks, indent=1))
    if len(sys.argv) > 3:  # voice-over for the screen part, starting where face A ends
        voice, start = Path(sys.argv[3]), marks[0]["end"]
        span = marks[-1]["start"] - start
        mixed = OUT / "vouch-demo-voice.mp4"
        run([FF, "-y", "-i", str(final), "-i", str(voice), "-filter_complex",
             f"[1:a]atrim=0:{span},adelay={start * 1000}|{start * 1000},apad[vo];[0:a][vo]amix=inputs=2:duration=first:normalize=0[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", str(mixed)])
        mixed.replace(final)
    print(f"\n{final}  {dur(final):.1f}s")
