"""Narration + soft music for the OATH explainer, mixed onto video/out/oath-demo.mp4.

    python video/audio.py voices            # list available voices
    python video/audio.py                   # narrate, make music, mix -> video/out/oath-demo-voiced.mp4

Needs ELEVENLABS_API_KEY in the environment or in ~/.oath/.env (never in the repo).
Each scene's line is generated separately (with the neighbouring lines as context so the read flows)
and placed at that scene's start, so the voice always matches what is on screen.
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
MODEL = "eleven_multilingual_v2"   # the most natural-sounding long-form model
VOICE = os.environ.get("OATH_VOICE_ID", "cjVigY5qzO86Huf0OWal")  # "Eric": smooth, trustworthy, conversational (alt: Brian nPczCjzI2devNBz1zQrb, George JBFqnCBsd6RMkjVDRZzb)
SETTINGS = {"stability": 0.5, "similarity_boost": 0.8, "style": 0.15, "use_speaker_boost": True, "speed": 1.0}

# (start s, end s, line) aligned with the scenes in video/src/anim.js
LINES = [
    (0.7, 5, "This is OATH. An AI trader that can't hide a call."),
    (5.5, 12, "Most trading bots can rewrite their story. Keep the wins... delete the losses."),
    (12.5, 20, "OATH reads the market first. Trend, momentum and risk all agree. Threshold met."),
    (20.5, 28, "Then it writes its plan. Entry, stop, take-profit, size, and a fifteen-minute horizon."),
    (28.5, 36, "Before any money moves, it seals the plan on Solana. A salted hash that can never change."),
    (36.4, 42, "Only then can it trade. The swap lands twenty slots after the commit."),
    (42.4, 50, "Code closes the trade, not the model. The plan is revealed, anyone can re-hash it... and it matches."),
    (50.4, 56, "Try to change a single number... and the hash breaks. Tampered."),
    (56.3, 60, "Every oath numbered. Every call verifiable."),
]

MUSIC_PROMPT = ("Soft, minimal ambient electronic underscore for a calm tech explainer. Warm analog synth pads, "
                "gentle slow pulse, subtle piano notes, hopeful and trustworthy mood, 80 BPM, no drums, no vocals, "
                "low dynamics so a voice-over sits clearly on top, smooth fade in and fade out.")


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


def tts(i: int, text: str, prev: str | None, nxt: str | None, speed: float) -> Path:
    out = AUD / f"line{i}.mp3"
    body = {"text": text, "model_id": MODEL, "voice_settings": {**SETTINGS, "speed": speed}}
    if prev:
        body["previous_text"] = prev
    if nxt:
        body["next_text"] = nxt
    r = httpx.post(f"{API}/text-to-speech/{VOICE}?output_format=mp3_44100_128", json=body,
                   headers={"xi-api-key": key()}, timeout=120)
    if r.status_code != 200:
        sys.exit(f"TTS failed for line {i}: HTTP {r.status_code} {r.text[:300]}")
    out.write_bytes(r.content)
    return out


def narrate() -> list[tuple[float, Path]]:
    placed = []
    for i, (start, end, text) in enumerate(LINES):
        prev = LINES[i - 1][2] if i else None
        nxt = LINES[i + 1][2] if i + 1 < len(LINES) else None
        window = end - start - 0.25
        speed = 1.0
        p = tts(i, text, prev, nxt, speed)
        d = dur(p)
        # too long for its scene? re-read a touch faster (ElevenLabs speed, natural up to ~1.15)
        while d > window and speed < 1.15:
            speed = round(min(1.15, speed * d / window + 0.02), 2)
            p = tts(i, text, prev, nxt, speed)
            d = dur(p)
        print(f"line {i}: {d:4.1f}s in a {window:4.1f}s window (speed {speed})" + ("  ** OVER **" if d > window else ""))
        placed.append((start, p))
    return placed


def music() -> Path:
    out = AUD / "music.mp3"
    r = httpx.post(f"{API}/music?output_format=mp3_44100_128", headers={"xi-api-key": key()},
                   json={"prompt": MUSIC_PROMPT, "music_length_ms": 61000, "model_id": "music_v1"}, timeout=300)
    if r.status_code == 200 and r.headers.get("content-type", "").startswith("audio"):
        out.write_bytes(r.content)
        print("music: ElevenLabs Music")
        return out
    print(f"music: ElevenLabs Music unavailable (HTTP {r.status_code}: {r.text[:160]}); synthesising an ambient pad")
    return pad()


def pad() -> Path:
    """Original ambient bed, synthesised here (no third-party audio). Warm detuned pads with a few
    harmonics over a slow Cmaj9 - Am9 - Fmaj7 - G6sus progression, sparse decaying piano-like notes,
    a soft multi-tap reverb, and gentle filtering so it stays under the voice."""
    out = AUD / "music.wav"
    bar = 3.8
    prog = [  # (root for the low pad, upper voicing)
        (65.41, (261.63, 329.63, 392.00, 493.88, 587.33)),   # Cmaj9
        (55.00, (220.00, 261.63, 329.63, 392.00, 493.88)),   # Am9
        (43.65, (220.00, 261.63, 349.23, 440.00, 523.25)),   # Fmaj7
        (49.00, (196.00, 293.66, 329.63, 392.00, 523.25)),   # G6sus
    ] * 4
    pluck_seq = [587.33, 523.25, 440.00, 392.00, 493.88, 440.00, 392.00, 329.63]
    ins, flt, n = [], [], 0

    def src(expr: str, dur: float, start: float, fade_in: float, fade_out: float, vol: float) -> None:
        nonlocal n
        ins.extend(["-f", "lavfi", "-t", f"{dur:.2f}", "-i", f"aevalsrc='{expr}':s=44100:c=stereo"])
        flt.append(f"[{n}]volume={vol},afade=t=in:d={fade_in},afade=t=out:st={dur - fade_out:.2f}:d={fade_out},"
                   f"adelay={int(start * 1000)}:all=1[s{n}]")
        n += 1

    warm = "0.55*sin(2*PI*{f}*t)+0.25*sin(2*PI*{f}*2*t)+0.08*sin(2*PI*{f}*3*t)"
    for ci, (root, chord) in enumerate(prog):
        t0 = ci * bar
        # low root pad, slightly longer so chords overlap smoothly
        src(warm.format(f=root) + f"|" + warm.format(f=root * 1.003), bar + 1.6, t0, 1.2, 1.8, 0.10)
        for f in chord:  # stereo-detuned upper pad (chorus-like shimmer)
            src(warm.format(f=f) + "|" + warm.format(f=f * 1.004), bar + 1.6, t0, 1.4, 1.8, 0.035)
        # two soft piano-like notes per chord, decaying naturally
        for k in range(2):
            f = pluck_seq[(ci * 2 + k) % len(pluck_seq)] * 2
            e = f"(sin(2*PI*{f}*t)+0.35*sin(2*PI*{f}*2*t)+0.1*sin(2*PI*{f}*3*t))*exp(-2.6*t)"
            src(e + "|" + e, 2.8, t0 + 0.6 + k * 1.9, 0.005, 0.6, 0.06)
    # Windows caps the command line, so render each chord to its own file, then layer the chord files.
    per_chord = 1 + 5 + 2
    chord_files = []
    for ci in range(len(prog)):
        a, b = ci * per_chord, (ci + 1) * per_chord
        ci_ins = ins[a * 6:b * 6]
        ci_flt = []
        for k in range(a, b):
            # re-index this chord's inputs from 0 and drop the absolute delay (applied when layering)
            f = flt[k].replace(f"[{k}]", f"[{k - a}]").replace(f"[s{k}]", f"[c{k - a}]")
            f = f.rsplit(",adelay=", 1)[0] + f",adelay={int((float(flt[k].split('adelay=')[1].split(':')[0]) / 1000 - ci * bar) * 1000)}:all=1[c{k - a}]"
            ci_flt.append(f)
        ci_flt.append("".join(f"[c{j}]" for j in range(per_chord)) + f"amix=inputs={per_chord}:normalize=0[o]")
        cf = AUD / f"chord{ci:02d}.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", *ci_ins, "-filter_complex", ";".join(ci_flt), "-map", "[o]", str(cf)],
                       check=True)
        chord_files.append(cf)
    lay_in, lay = [], []
    for ci, cf in enumerate(chord_files):
        lay_in += ["-i", str(cf)]
        lay.append(f"[{ci}]adelay={int(ci * bar * 1000)}:all=1[l{ci}]")
    lay.append("".join(f"[l{ci}]" for ci in range(len(chord_files))) + f"amix=inputs={len(chord_files)}:normalize=0,"
               "highpass=f=45,lowpass=f=3200,aecho=0.85:0.8:70|140|260|520:0.32|0.24|0.16|0.10,"
               "afade=t=in:d=3,afade=t=out:st=56.5:d=4.5,atrim=0:61,alimiter=limit=0.7[out]")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *lay_in, "-filter_complex", ";".join(lay), "-map", "[out]", str(out)],
                   check=True)
    return out


def mix(placed: list[tuple[float, Path]], bed: Path) -> None:
    ins, flt = ["-i", str(VIDEO)], []
    for k, (start, p) in enumerate(placed):
        ins += ["-i", str(p)]
        flt.append(f"[{k + 1}:a]aresample=44100,adelay={int(start * 1000)}:all=1[v{k}]")
    nv = len(placed)
    flt.append("".join(f"[v{k}]" for k in range(nv)) + f"amix=inputs={nv}:normalize=0,apad=whole_dur=60[voice]")
    ins += ["-i", str(bed)]
    b = nv + 1
    # music quietly under everything, ducked further while the narrator speaks
    flt.append("[voice]asplit=2[vmix][vkey]")
    flt.append(f"[{b}:a]aresample=44100,atrim=0:60,volume=0.30,afade=t=in:d=1.5,afade=t=out:st=57.5:d=2.5[bed]")
    flt.append("[bed][vkey]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=450[ducked]")
    flt.append("[vmix][ducked]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9,atrim=0:60[aout]")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", ";".join(flt),
                    "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
                    "-movflags", "+faststart", "-shortest", str(FINAL)], check=True)
    print(f"wrote {FINAL}: {FINAL.stat().st_size / 1e6:.2f} MB, {dur(FINAL):.2f}s")


def voices() -> None:
    r = httpx.get(f"{API}/voices", headers={"xi-api-key": key()}, timeout=60)
    r.raise_for_status()
    for v in r.json()["voices"]:
        lab = v.get("labels") or {}
        print(f"{v['voice_id']}  {v['name']:<22} {lab.get('gender', ''):<7} {lab.get('accent', ''):<12} {lab.get('age', ''):<12} {lab.get('description', '') or lab.get('descriptive', '')} {lab.get('use_case', '')}")


if __name__ == "__main__":
    AUD.mkdir(parents=True, exist_ok=True)
    if sys.argv[1:] == ["voices"]:
        voices()
        sys.exit()
    if sys.argv[1:] == ["music"]:
        print(music())
        sys.exit()
    placed = narrate()
    bed = music()
    mix(placed, bed)
    json.dump({"voice": VOICE, "model": MODEL, "lines": LINES}, open(AUD / "narration.json", "w"), indent=1)
