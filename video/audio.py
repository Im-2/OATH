"""Narration + soft music for the OATH explainer, mixed onto video/out/oath-demo.mp4.

    python video/audio.py            # narrate, make music (if missing), mix -> video/out/oath-demo-voiced.mp4
    python video/audio.py mix        # re-mix existing narration + music (no new TTS)
    python video/audio.py voices     # list voices

Rules this follows:
  * The narrator says EXACTLY the words shown on screen, starting at the moment they appear
    (times taken from video/src/anim.js), so voice and picture always match.
  * Each clip is trimmed of leading/trailing silence so the first word lands on its frame, and must
    finish before the next line starts (checked; the run fails loudly if a line does not fit).
  * The music plays continuously for the whole video; under the voice it dips only a few dB.

Needs ELEVENLABS_API_KEY in the environment or in ~/.oath/.env (never in the repo).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
AUD = OUT / "audio"
VIDEO = OUT / "oath-demo.mp4"
FINAL = OUT / "oath-demo-voiced.mp4"
API = "https://api.elevenlabs.io/v1"
# multilingual v2 reads the script word for word (v3 sounds lively but can improvise words)
MODEL = os.environ.get("OATH_TTS_MODEL", "eleven_multilingual_v2")
# "George": warm, captivating storyteller (alt: Brian nPczCjzI2devNBz1zQrb, Eric cjVigY5qzO86Huf0OWal)
VOICE = os.environ.get("OATH_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
SETTINGS = {"stability": 0.55, "similarity_boost": 0.8, "style": 0.1, "use_speaker_boost": True}

# (start s, must end by s, words): EXACTLY what is on screen, starting when it appears.
LINES = [
    (0.8, 5.1, "OATH. An AI trader that can't hide a call."),
    (5.2, 9.4, "Most trading bots can rewrite their story."),
    (9.5, 12.1, "Losing trades? Quietly deleted."),
    (12.2, 16.2, "OATH reads the market."),
    (16.3, 20.1, "Three agreeing. Zero against. Threshold met."),
    (20.2, 21.8, "It writes its plan."),
    (21.9, 28.1, "Entry. Stop. Take-profit. Size. Horizon."),
    (28.2, 31.8, "Then seals it on Solana."),
    (31.9, 36.1, "Sealed. Committed."),
    (36.2, 39.3, "Only then can it trade."),
    (39.4, 42.1, "Traded, after the commit."),
    (42.2, 44.8, "Code closes the trade, not the model."),
    (44.9, 47.8, "Horizon reached. Monitor exits."),
    (47.9, 50.2, "Match. Exactly what OATH committed."),
    (50.3, 53.4, "Try to cheat."),
    (53.5, 56.3, "Tampered."),
    (56.4, 59.8, "Every oath numbered. Every call verifiable."),
]


def key() -> str:
    k = os.environ.get("ELEVENLABS_API_KEY")
    if not k:
        env = Path.home() / ".oath" / ".env"
        for line in env.read_text(encoding="utf-8").splitlines() if env.exists() else []:
            if line.startswith("ELEVENLABS_API_KEY="):
                k = line.split("=", 1)[1].strip()
    if not k:
        sys.exit("ELEVENLABS_API_KEY not set (env or ~/.oath/.env)")
    return k


def dur(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def tts(i: int, text: str, prev: str | None, nxt: str | None, speed: float) -> Path:
    body = {"text": text, "model_id": MODEL, "voice_settings": {**SETTINGS, "speed": speed}}
    if prev:
        body["previous_text"] = prev
    if nxt:
        body["next_text"] = nxt
    r = httpx.post(f"{API}/text-to-speech/{VOICE}?output_format=mp3_44100_128", json=body,
                   headers={"xi-api-key": key()}, timeout=120)
    if r.status_code != 200:
        sys.exit(f"TTS failed for line {i}: HTTP {r.status_code} {r.text[:300]}")
    raw = AUD / f"line{i:02d}.raw.mp3"
    raw.write_bytes(r.content)
    out = AUD / f"line{i:02d}.wav"
    # trim silence at both ends so the first word lands on its frame. -42 dB keeps soft first consonants
    # ("th" in "Three"); a stricter -30 dB clipped them. Onsets measured in the mix land within 50 ms.
    ff("-i", str(raw), "-af",
       "silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.02,"
       "areverse,silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.08,areverse",
       "-ar", "44100", "-ac", "1", str(out))
    return out


def narrate() -> list[tuple[float, Path]]:
    placed = []
    for i, (start, end, text) in enumerate(LINES):
        prev = LINES[i - 1][2] if i else None
        nxt = LINES[i + 1][2] if i + 1 < len(LINES) else None
        window = end - start - 0.1
        speed = 1.0
        p = tts(i, text, prev, nxt, speed)
        d = dur(p)
        while d > window and speed < 1.12:  # only a touch faster, never rushed
            speed = round(min(1.12, speed * d / window + 0.01), 2)
            p = tts(i, text, prev, nxt, speed)
            d = dur(p)
        status = "OK" if d <= window else "TOO LONG"
        print(f"{status:8} {start:5.1f}s  {d:4.2f}s/{window:4.2f}s  speed {speed}  {text}")
        if d > window:
            sys.exit(f"line {i} does not fit its window; shorten it")
        placed.append((start, p))
    return placed


def pad() -> Path:
    """Original ambient bed, synthesised here (no third-party audio): warm detuned pads over a slow
    Cmaj9 - Am9 - Fmaj7 - G6sus progression, sparse decaying piano-like notes, soft reverb.
    Each chord is rendered to its own file (Windows caps command length), then the chords are
    chained with 1.6 s crossfades, so the bed is continuous for the whole minute."""
    out = AUD / "music.wav"
    bar, overlap = 3.8, 1.6
    prog = [
        (65.41, (261.63, 329.63, 392.00, 493.88, 587.33)),   # Cmaj9
        (55.00, (220.00, 261.63, 329.63, 392.00, 493.88)),   # Am9
        (43.65, (220.00, 261.63, 349.23, 440.00, 523.25)),   # Fmaj7
        (49.00, (196.00, 293.66, 329.63, 392.00, 523.25)),   # G6sus
    ] * 4
    pluck_seq = [587.33, 523.25, 440.00, 392.00, 493.88, 440.00, 392.00, 329.63]
    warm = "0.55*sin(2*PI*{f}*t)+0.25*sin(2*PI*{f}*2*t)+0.08*sin(2*PI*{f}*3*t)"
    chord_files = []
    for ci, (root, chord) in enumerate(prog):
        ins, flt = [], []

        def src(expr: str, length: float, at: float, fin: float, fout: float, vol: float) -> None:
            n = len(flt)
            ins.extend(["-f", "lavfi", "-t", f"{length:.2f}", "-i", f"aevalsrc='{expr}':s=44100:c=stereo"])
            flt.append(f"[{n}]volume={vol},afade=t=in:d={fin},afade=t=out:st={length - fout:.2f}:d={fout},"
                       f"adelay={int(at * 1000)}:all=1[c{n}]")

        src(warm.format(f=root) + "|" + warm.format(f=root * 1.003), bar + overlap, 0, 1.2, 1.8, 0.10)
        for f in chord:
            src(warm.format(f=f) + "|" + warm.format(f=f * 1.004), bar + overlap, 0, 1.4, 1.8, 0.035)
        for k in range(2):
            f = pluck_seq[(ci * 2 + k) % len(pluck_seq)] * 2
            e = f"(sin(2*PI*{f}*t)+0.35*sin(2*PI*{f}*2*t)+0.1*sin(2*PI*{f}*3*t))*exp(-2.6*t)"
            src(e + "|" + e, 2.8, 0.6 + k * 1.9, 0.005, 0.6, 0.06)
        n = len(flt)
        flt.append("".join(f"[c{j}]" for j in range(n)) + f"amix=inputs={n}:normalize=0:duration=longest,"
                   f"apad=whole_dur={bar + overlap},atrim=0:{bar + overlap}[o]")
        cf = AUD / f"chord{ci:02d}.wav"
        ff(*ins, "-filter_complex", ";".join(flt), "-map", "[o]", str(cf))
        chord_files.append(cf)
    lay_in, chain, prev = [], [], "[0]"
    for cf in chord_files:
        lay_in += ["-i", str(cf)]
    for ci in range(1, len(chord_files)):
        chain.append(f"{prev}[{ci}]acrossfade=d={overlap}:c1=tri:c2=tri[x{ci}]")
        prev = f"[x{ci}]"
    chain.append(f"{prev}highpass=f=45,lowpass=f=3200,aecho=0.85:0.8:70|140|260|520:0.32|0.24|0.16|0.10,"
                 "afade=t=in:d=2.5,atrim=0:60.5,afade=t=out:st=57:d=3.5,alimiter=limit=0.7[out]")
    ff(*lay_in, "-filter_complex", ";".join(chain), "-map", "[out]", str(out))
    return out


def mix(placed: list[tuple[float, Path]], bed: Path) -> None:
    ins, flt = ["-i", str(VIDEO)], []
    for k, (start, p) in enumerate(placed):
        ins += ["-i", str(p)]
        flt.append(f"[{k + 1}:a]aresample=44100,aformat=channel_layouts=stereo,adelay={int(round(start * 1000))}:all=1[v{k}]")
    nv = len(placed)
    flt.append("".join(f"[v{k}]" for k in range(nv)) + f"amix=inputs={nv}:normalize=0:duration=longest,"
               "apad=whole_dur=60,atrim=0:60[voice]")
    ins += ["-i", str(bed)]
    b = nv + 1
    flt.append("[voice]asplit=2[vmix][vkey]")
    # the music plays the whole time; under the voice it dips only a few dB (ratio 2), never disappears
    flt.append(f"[{b}:a]aresample=44100,aformat=channel_layouts=stereo,atrim=0:60,volume=0.55[bed]")
    flt.append("[bed][vkey]sidechaincompress=threshold=0.08:ratio=2:attack=40:release=600[ducked]")
    flt.append("[vmix][ducked]amix=inputs=2:normalize=0:duration=first,volume=1.5,alimiter=limit=0.89[aout]")
    ff(*ins, "-filter_complex", ";".join(flt), "-map", "0:v", "-map", "[aout]", "-c:v", "copy",
       "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", "-movflags", "+faststart", "-t", "60", str(FINAL))
    print(f"wrote {FINAL}: {FINAL.stat().st_size / 1e6:.2f} MB, {dur(FINAL):.2f}s")


def voices() -> None:
    r = httpx.get(f"{API}/voices", headers={"xi-api-key": key()}, timeout=60)
    r.raise_for_status()
    for v in r.json()["voices"]:
        lab = v.get("labels") or {}
        print(f"{v['voice_id']}  {v['name']:<40} {lab.get('accent', ''):<12} {lab.get('use_case', '')}")


if __name__ == "__main__":
    AUD.mkdir(parents=True, exist_ok=True)
    arg = sys.argv[1:]
    if arg == ["voices"]:
        voices()
        sys.exit()
    bed = AUD / "music.wav"
    if arg == ["music"] or not bed.exists():
        bed = pad()
        if arg == ["music"]:
            sys.exit()
    if arg == ["mix"]:
        placed = [(start, AUD / f"line{i:02d}.wav") for i, (start, _, _) in enumerate(LINES)]
    else:
        placed = narrate()
    mix(placed, bed)
    json.dump({"voice": VOICE, "model": MODEL, "lines": LINES}, open(AUD / "narration.json", "w"), indent=1)
