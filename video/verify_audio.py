"""Check the voiced video with speech-to-text (local Whisper, nothing uploaded):
  1. every scripted line is spoken, word for word,
  2. each line starts within 0.3 s of the moment its text appears on screen,
  3. the music is audible the whole time (RMS of the mix never falls to silence).

    uv run --no-project --with faster-whisper python video/verify_audio.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from faster_whisper import WhisperModel

HERE = Path(__file__).resolve().parent
MP4 = HERE / "out" / "oath-demo-voiced.mp4"
LINES = json.loads((HERE / "out" / "audio" / "narration.json").read_text())["lines"]
norm = lambda s: re.sub(r"[^a-z0-9 ]", "", s.lower().replace("-", " ")).split()  # noqa: E731

model = WhisperModel("base.en", device="cpu", compute_type="int8")
segs, _ = model.transcribe(str(MP4), word_timestamps=True, vad_filter=False, beam_size=5,
                           initial_prompt="OATH. Solana. Take-profit. Tampered.")
words = [(w.start, w.end, norm(w.word)) for s in segs for w in s.words]
words = [(a, b, t[0]) for a, b, t in words if t]
print("transcript:", " ".join(w for _, _, w in words), "\n")

bad = 0
for start, end, text in LINES:
    want = norm(text)
    # words heard between this line's start and the next line's start
    heard = [w for a, b, w in words if start - 0.4 <= a < end]
    first = next((a for a, b, w in words if start - 0.4 <= a < end), None)
    # Whisper hears "OATH" as oath/oaf/both; accept close variants for the brand word only
    fix = lambda ws: ["oath" if w in ("oaf", "both", "oat", "ofe", "oaths") else w for w in ws]  # noqa: E731
    ok_words = fix(heard) == fix(want)
    ok_time = first is not None and abs(first - start) <= 0.3
    bad += not (ok_words and ok_time)
    print(f"{'OK ' if ok_words and ok_time else 'BAD'} {start:5.1f}s  starts {('%.2f' % first) if first is not None else '  -  '}s"
          f"  want: {' '.join(want)}\n{'':17}heard: {' '.join(heard)}")

# music present throughout: 1 s windows of the full mix never go silent
low = []
for t in range(0, 59):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", str(t), "-t", "1", "-i", str(MP4), "-af", "astats",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.findall(r"RMS level dB: (-?[\d.]+|-inf)", r)
    v = float(m[-1]) if m and m[-1] != "-inf" else -200.0
    if v < -45:
        low.append((t, v))
print("\nmusic/audio silent windows:", low or "none")
sys.exit(1 if bad or low else 0)
