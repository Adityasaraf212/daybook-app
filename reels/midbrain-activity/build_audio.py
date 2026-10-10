#!/usr/bin/env python3
"""Mid-Brain activity promo reel: original soundtrack (no samples, no licensed music).

Synthesises a 120 BPM A-minor track + sound design, locked to the cut times in
build_video.py (it imports SHOTS / ROUND_STARTS / T_REACT / T_CTA / TOTAL).

    python3 build_audio.py out.wav

Structure
    0.0 - 3.5   hook: boom, sub pulse, tick per word, riser into the drop
    3.5 - 23.0  groove (kick/clap/hat/bass/arp/pad), ding + whoosh on every round
    23.0 - 28.0 "smiles" section: brighter major chords, bells, softer drums
    28.0 - 33.0 CTA: groove returns, button chime, final stab
"""
import sys
import wave

import numpy as np

from build_video import ROUND_STARTS, SHOTS, T_CTA, T_REACT, TOTAL

SR = 44100
N = int(TOTAL * SR)
BEAT = 0.5
T_DROP = 3.5
rng = np.random.default_rng(11)


# --------------------------------------------------------------------------- #
# DSP helpers
# --------------------------------------------------------------------------- #
def tt(d):
    return np.arange(int(d * SR)) / SR


def midi(f_a4, semis):
    return f_a4 * 2 ** (semis / 12)


def band(x, lo=None, hi=None, w=0.25):
    """FFT band-pass with soft edges (octave-wide smoothing)."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR) + 1e-9
    m = np.ones_like(f)
    if lo:
        m *= 1 / (1 + np.exp(-(np.log2(f / lo)) / w * 4))
    if hi:
        m *= 1 / (1 + np.exp((np.log2(f / hi)) / w * 4))
    return np.fft.irfft(X * m, len(x))


def fftconv(x, h):
    n = len(x) + len(h) - 1
    size = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(h, size), size)[:n]


def kick(vel=1.0):
    t = tt(0.5)
    f = 46 + 110 * np.exp(-t / 0.032)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t / 0.17)
    click = rng.standard_normal(len(t)) * np.exp(-t / 0.003) * 0.25
    return np.tanh(1.15 * (body + click * 0.6)) * vel


def clap(vel=1.0):
    t = tt(0.4)
    n = band(rng.standard_normal(len(t)), 900, 6500)
    env = np.zeros(len(t))
    for off in (0.0, 0.011, 0.023):
        k = int(off * SR)
        env[k:] += np.exp(-(t[: len(t) - k]) / 0.012) * 0.7
    env += np.exp(-t / 0.09) * 0.55
    return n / (np.abs(n).max() + 1e-9) * env * vel


def hat(open_=False, vel=1.0):
    t = tt(0.25 if open_ else 0.09)
    n = band(rng.standard_normal(len(t)), 7000, None)
    return n / (np.abs(n).max() + 1e-9) * np.exp(-t / (0.09 if open_ else 0.022)) * vel


def bass_note(f, d, vel=1.0):
    t = tt(d + 0.08)
    sub = np.sin(2 * np.pi * f * t)
    saw = sum(np.sin(2 * np.pi * f * k * t) / k for k in range(1, 9)) * 0.45
    env = np.minimum(1, t / 0.006) * np.exp(-t / 0.28) * np.clip((d + 0.08 - t) / 0.06, 0, 1)
    return np.tanh(1.05 * (sub + saw) * env) * vel


def pluck(f, d=0.3, vel=1.0):
    t = tt(d)
    out = np.zeros(len(t))
    for k in range(1, 11):
        out += np.sin(2 * np.pi * f * k * t) / k * np.exp(-t * (4 + k * 2.2))
    return out * np.minimum(1, t / 0.003) * vel


def bell(f, vel=1.0, d=1.4):
    t = tt(d)
    out = np.zeros(len(t))
    for r, a, tau in ((1, 1.0, 0.9), (2.76, 0.5, 0.5), (5.4, 0.25, 0.3), (8.93, 0.12, 0.15)):
        out += a * np.sin(2 * np.pi * f * r * t) * np.exp(-t / tau)
    return out * np.minimum(1, t / 0.002) * vel * 0.6


def pad(freqs, d=2.0, vel=1.0):
    t = tt(d)
    out = np.zeros(len(t))
    for f in freqs:
        for det in (-0.006, 0.006):
            ff = f * (1 + det)
            out += sum(np.sin(2 * np.pi * ff * k * t) / k ** 1.4 for k in range(1, 7))
    env = np.minimum(1, t / 0.45) * np.clip((d - t) / 0.5, 0, 1)
    return out * env * vel / (len(freqs) * 1.6)


def whoosh(d=0.45, f0=250, f1=5200, up=True, vel=1.0):
    n = int(d * SR)
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    blk, hop = 1024, 512
    win = np.hanning(blk)
    f = np.fft.rfftfreq(blk, 1 / SR)
    for i in range(0, n - blk, hop):
        u = i / n
        fc = f0 * (f1 / f0) ** (u if up else 1 - u)
        m = np.exp(-0.5 * (np.log2((f + 1) / fc) / 0.75) ** 2)
        out[i:i + blk] += np.fft.irfft(np.fft.rfft(noise[i:i + blk] * win) * m, blk)
    env = np.sin(np.pi * np.linspace(0, 1, n)) ** 1.6
    return out / (np.abs(out).max() + 1e-9) * env * vel


def riser(d=2.0, vel=1.0):
    n = int(d * SR)
    t = np.arange(n) / SR
    w = whoosh(d, 300, 9000, True, 1.0)
    u = t / d
    chirp = np.sin(2 * np.pi * np.cumsum(180 * (10 ** (u * 1.1))) / SR) * 0.25
    env = u ** 2.2
    return (w * 1.0 + chirp) * np.maximum(env, 0.02) * vel


def impact(vel=1.0):
    t = tt(1.6)
    f = 34 + 90 * np.exp(-t / 0.09)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.55)
    burst = band(rng.standard_normal(len(t)), 80, 2500) * np.exp(-t / 0.12) * 0.5
    crash = band(rng.standard_normal(len(t)), 3500, None) * np.exp(-t / 0.55) * 0.22
    return np.tanh(1.4 * (boom + burst) + crash) * vel


def pop_sfx(freq=900, vel=1.0):
    t = tt(0.12)
    f = freq * (1 + 0.5 * np.exp(-t / 0.018))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.035)
    click = rng.standard_normal(len(t)) * np.exp(-t / 0.002) * 0.15
    return (s + click) * vel


def make_ir(d=1.7):
    n = int(d * SR)
    t = np.arange(n) / SR
    ir = np.zeros((2, n))
    for c in range(2):
        x = rng.standard_normal(n) * np.exp(-t / 0.40)
        x = band(x, 180, 6500)
        x[: int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))
        ir[c] = x / np.abs(x).max()
    return ir


# --------------------------------------------------------------------------- #
# mixer
# --------------------------------------------------------------------------- #
class Mix:
    def __init__(self):
        self.drums = np.zeros((2, N))
        self.music = np.zeros((2, N))
        self.fx = np.zeros((2, N))
        self.send = np.zeros((2, N))
        self.kicks = []

    def put(self, bus, sig, t, gain=1.0, pan=0.0, send=0.0, fade_at=None):
        i = int(round(t * SR))
        if i >= N:
            return
        sig = np.asarray(sig, dtype=np.float64)
        if fade_at is not None:  # hard section end: short fade so nothing clicks
            k = int((fade_at - t) * SR)
            if k <= 0:
                return
            sig = sig[:k].copy()
            m = min(len(sig), int(0.03 * SR))
            sig[-m:] *= np.linspace(1, 0, m)
        n = min(len(sig), N - i)
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        bus[0, i:i + n] += sig[:n] * gain * l
        bus[1, i:i + n] += sig[:n] * gain * r
        if send:
            self.send[0, i:i + n] += sig[:n] * gain * l * send
            self.send[1, i:i + n] += sig[:n] * gain * r * send

    def kick_at(self, t, vel=1.0):
        self.put(self.drums, kick(), t, 0.95 * vel)
        self.kicks.append(t)

    def duck_env(self, depth=0.5):
        env = np.ones(N)
        t = tt(0.45)
        shape = 1 - depth * np.exp(-t / 0.11)
        for k in self.kicks:
            i = int(k * SR)
            if i >= N:
                continue
            n = min(len(shape), N - i)
            env[i:i + n] = np.minimum(env[i:i + n], shape[:n])
        return env


# --------------------------------------------------------------------------- #
# composition
# --------------------------------------------------------------------------- #
A4 = 440.0
# chords as semitone offsets from A4 (octave 4/5 voicing for arp/pad) + bass root (octave 2)
CH = {
    "Am": dict(tones=[0, 3, 7, 12], bass=-24),
    "F": dict(tones=[-4, 0, 3, 8], bass=-28),
    "C": dict(tones=[3, 7, 10, 15], bass=-21),
    "G": dict(tones=[-2, 2, 5, 10], bass=-26),
}
# note: tones are semitones relative to A4; e.g. Am = A4 C5 E5 A5, F = F4 A4 C5 F5
ARP = [0, 1, 2, 1, 0, 1, 2, 3]


def groove_section(m, start, end, prog, intensity=1.0, soft=False):
    k = 0
    t = start
    while t < end - 1e-6:
        bar = int((t - start) / 2.0)
        if abs((t - start) % 2.0) < 1e-6:
            chord = CH[prog[bar % len(prog)]]
            bt = t
            # pad
            freqs = [midi(A4, s) for s in chord["tones"][:3]]
            m.put(m.music, pad(freqs, 2.0), bt, (0.30 if soft else 0.17) * intensity, 0.0, send=0.25, fade_at=end)
            # bass (not in soft section)
            if not soft:
                for off, d in ((0.0, 0.40), (0.75, 0.20), (1.0, 0.40), (1.5, 0.35)):
                    m.put(m.music, bass_note(midi(A4, chord["bass"]), d), bt + off, 0.62 * intensity, fade_at=end)
            # arp (8ths)
            for i in range(8):
                idx = ARP[i]
                semis = chord["tones"][idx % 4] + (12 if soft else 0)
                f = midi(A4, semis)
                pan = -0.35 if i % 2 == 0 else 0.35
                if soft:
                    m.put(m.music, bell(f), bt + i * 0.25, 0.22 * intensity, pan, send=0.35, fade_at=end)
                else:
                    m.put(m.music, pluck(f), bt + i * 0.25, 0.24 * intensity, pan, send=0.28, fade_at=end)
        # drums on the beat grid
        beat_in_bar = int(round(((t - start) % 2.0) / BEAT))
        if soft:
            if beat_in_bar in (0, 2):
                m.kick_at(t, 0.6)
            m.put(m.drums, hat(vel=0.5), t + 0.25, 0.05, 0.3)
        else:
            m.kick_at(t, intensity)
            if beat_in_bar in (1, 3):
                m.put(m.drums, clap(), t, 0.30 * intensity, 0.0, send=0.10, fade_at=end)
            m.put(m.drums, hat(vel=0.55), t, 0.06, -0.25, fade_at=end)
            m.put(m.drums, hat(open_=(beat_in_bar == 3)), t + 0.25, 0.08, 0.25, fade_at=end)
            m.put(m.drums, hat(vel=0.4), t + 0.125, 0.025, -0.1, fade_at=end)
            m.put(m.drums, hat(vel=0.4), t + 0.375, 0.025, 0.1, fade_at=end)
        t += BEAT
        k += 1


def build():
    m = Mix()

    # ---- HOOK (0 - 3.5) ---------------------------------------------------
    m.put(m.fx, impact(), 0.0, 0.95, send=0.2)
    m.kicks.append(0.0)
    t = tt(3.5)
    drone = np.sin(2 * np.pi * 55 * t) * np.minimum(1, t / 0.3) * 0.5 + np.sin(2 * np.pi * 110 * t) * 0.12
    m.put(m.music, drone, 0.0, 0.5)
    for i in range(2, 7):  # 8th-note sub pulses
        m.put(m.music, bass_note(55.0, 0.2), i * 0.5, 0.55)
        m.kicks.append(i * 0.5)
    m.put(m.fx, whoosh(0.35, 400, 4500, True), 0.75, 0.30, -0.3)   # into cut at 1.0
    for wt, hz in zip((1.55, 1.68, 1.81, 1.94, 2.07, 2.20), (700, 760, 820, 880, 940, 1100)):
        m.put(m.fx, pop_sfx(hz), wt, 0.32, 0.0)
    m.put(m.fx, pop_sfx(1500, 1.0), 2.55, 0.35)
    m.put(m.fx, riser(1.95), 1.5, 0.55, send=0.15)
    m.put(m.drums, clap(), 1.5, 0.25, send=0.12)
    for i in range(24):  # accelerating ticks under the riser
        tk = 2.0 + 1.45 * (i / 24) ** 0.8
        m.put(m.drums, hat(vel=0.7), tk, 0.06 + 0.08 * i / 24, 0.2)

    # ---- DROP / MAIN GROOVE (3.5 - 23.0) ---------------------------------------
    m.put(m.fx, impact(), T_DROP, 1.0, send=0.25)
    groove_section(m, T_DROP, T_REACT, ["Am", "F", "C", "G"], 1.0)
    for wt, hz in ((T_DROP + 0.12, 600), (T_DROP + 0.30, 800), (T_DROP + 1.10, 1000)):
        m.put(m.fx, pop_sfx(hz), wt, 0.30)

    # ---- STEP 1 + ROUNDS: chip hits (ding ascending) --------------------------------
    m.put(m.fx, pop_sfx(520), 6.5, 0.35)
    m.put(m.fx, bell(midi(A4, 3)), 6.5, 0.30, 0.0, send=0.35)
    for n_i, rs in enumerate(ROUND_STARTS):
        semis = (3, 7, 10, 15)[n_i]
        m.put(m.fx, bell(midi(A4, semis)), rs, 0.42, 0.0, send=0.4)
        m.put(m.fx, pop_sfx(700 + 90 * n_i), rs + 0.2, 0.28)
        m.put(m.fx, whoosh(0.5, 300, 5200, True), rs - 0.35, 0.30)
        # snare-roll lead-in (16ths) before each round
        for i in range(4):
            m.put(m.drums, clap(), rs - 0.25 + i * 0.0625, 0.10 + 0.04 * i, 0.0)
    # pips fill tick
    # ---- generic whoosh on every other cut ------------------------------------
    cuts = [s[1] for s in SHOTS[1:]]
    special = {T_DROP, T_REACT, T_CTA} | set(ROUND_STARTS)
    for ct in cuts:
        if ct in special:
            continue
        m.put(m.fx, whoosh(0.35, 500, 6000, ct % 1.0 == 0), ct - 0.2, 0.22, -0.2 if ct % 1.0 else 0.2)
    # caption pops for title block
    m.put(m.fx, pop_sfx(450), 3.62, 0.5)
    m.put(m.fx, pop_sfx(620), 3.80, 0.4)
    m.put(m.fx, pop_sfx(900), 4.60, 0.3)

    # ---- REACTION (23.0 - 28.0): brighter major progression, bells, soft drums ---
    m.put(m.fx, riser(0.9), T_REACT - 0.9, 0.45, send=0.2)
    m.put(m.fx, impact(), T_REACT, 0.85, send=0.3)
    groove_section(m, T_REACT, T_CTA, ["C", "G", "Am", "F"], 1.0, soft=True)
    for i, wt in enumerate([T_REACT + 0.1 + 0.16 * j for j in range(6)]):
        m.put(m.fx, pop_sfx(760 + 70 * i), wt, 0.26)
    m.put(m.fx, bell(midi(A4, 19)), T_REACT + 0.94, 0.30, 0.0, send=0.5)

    # ---- CTA (28.0 - 33.0) -----------------------------------------------------------
    m.put(m.fx, riser(0.9), T_CTA - 0.9, 0.5, send=0.2)
    m.put(m.fx, impact(), T_CTA, 1.0, send=0.3)
    groove_section(m, T_CTA, T_CTA + 4.0, ["Am", "F"], 0.95)
    m.put(m.fx, pop_sfx(520), T_CTA + 0.25, 0.3)
    for i in range(6):
        m.put(m.fx, pop_sfx(700 + 60 * i), T_CTA + 0.55 + 0.16 * i, 0.26)
    # button + footer
    m.put(m.fx, pop_sfx(1000), T_CTA + 1.7, 0.4)
    m.put(m.fx, bell(midi(A4, 15)), T_CTA + 1.7, 0.42, 0.0, send=0.45)
    m.put(m.fx, bell(midi(A4, 22)), T_CTA + 1.8, 0.32, 0.2, send=0.45)
    m.put(m.fx, pop_sfx(800), T_CTA + 2.2, 0.25)
    # final stab + ring-out
    ft = T_CTA + 4.0
    m.put(m.fx, impact(), ft, 0.8, send=0.35)
    m.put(m.music, pad([midi(A4, s) for s in (0, 3, 7)], 1.0), ft, 0.45, send=0.4)
    m.put(m.music, bass_note(midi(A4, -24), 0.9), ft, 0.7)
    m.put(m.fx, bell(midi(A4, 12)), ft, 0.40, -0.2, send=0.5)
    m.put(m.fx, bell(midi(A4, 19)), ft + 0.08, 0.30, 0.2, send=0.5)
    m.kicks.append(ft)

    # ---- bus processing -----------------------------------------------------------
    m.music *= m.duck_env(0.55)
    # tiny pre-drop gap for impact
    gap = np.ones(N)
    g0, g1 = int((T_DROP - 0.09) * SR), int(T_DROP * SR)
    gap[g0:g1] = np.linspace(1, 0.05, g1 - g0)
    for b in (m.music, m.drums):
        b *= gap
    ir = make_ir()
    wet = np.stack([fftconv(m.send[c], ir[c])[:N] for c in range(2)])
    mix = m.drums + m.music + m.fx + wet * 0.45
    mix *= 10 ** (-19 / 20) / np.sqrt((mix ** 2).mean())      # RMS ~ -19 dBFS before loudnorm
    mix = 0.8 * np.tanh(mix / 0.8)                              # gentle soft limiter
    fade = np.ones(N)
    k = int(0.45 * SR)
    fade[-k:] = np.linspace(1, 0, k) ** 1.5
    fade[: int(0.004 * SR)] = np.linspace(0, 1, int(0.004 * SR))
    mix *= fade
    return mix


def write_wav(path, x):
    pcm = (np.clip(x.T, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    write_wav(sys.argv[1], build())
    print("wrote", sys.argv[1])
