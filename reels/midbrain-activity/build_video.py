#!/usr/bin/env python3
"""Mid-Brain activity promo reel: video builder.

Re-cuts the already-edited source clip into a 35 s, 1080x1920, 30 fps reel with a
hook, kinetic captions, round chips, a progress tracker and a CTA end card.
The source's burned-in caption band (bottom of frame) is cropped out.

    python3 build_video.py SOURCE.mp4 out_silent.mp4             # full render
    python3 build_video.py SOURCE.mp4 prev/ --preview 0.5 2.9    # still frames

Everything you may want to edit (copy, timings, shot choices) is in the CONFIG
block below.
"""
import argparse
import functools
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# --------------------------------------------------------------------------- #
# CONFIG
# --------------------------------------------------------------------------- #
W, H, FPS = 1080, 1920, 30
SRC_W, SRC_H = 478, 850
CROP_H = 730                   # keep source rows 0..729 (burned-in captions start ~y=740)
VID_H = 1649                   # 1080 * 730 / 478, rounded down so the crop box stays inside the source
SHIFT = 60                     # footage is nudged up this many px (top rows are under the app UI anyway)
VIS_H = VID_H - SHIFT          # visible footage height before the dark base
TOTAL = 34.0
T_REACT = 23.0                 # reaction block starts
T_CTA = 28.0                   # CTA end card starts

YELLOW = (255, 210, 31)
WHITE = (255, 255, 255)
INK = (14, 14, 18)
BLACK = (0, 0, 0)

FONT = "/usr/share/fonts/opentype/inter/Inter-Black.otf"
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

# Copy -- edit freely.
COPY = dict(
    hook_1="BLINDFOLDED.",
    hook_2=[["CAN", "THEY"], ["STILL", "TELL"], ["THE", "COLOR?"]],
    title_1="MID-BRAIN",
    title_2="ACTIVITY",
    title_sub="Here's how it works",
    step1=("STEP 1", "SEAL THE EYES", "\U0001F648"),
    step1_cap_a="Cotton pads over the eyes...",
    step1_cap_b="...then a blindfold on top.",
    rounds=[
        ("ROUND 1", "COLORS", "\U0001F3A8", "Which color is it?"),
        ("ROUND 2", "SHAPES", "✋", "Which shape is it?"),
        ("ROUND 3", "PICTURES", "\U0001F5BC", "What's the picture?"),
        ("ROUND 4", "WORDS + NUMBERS", "\U0001F522", "What's written on it?"),
    ],
    react=[["THE", "SMILES"], ["SAY", "IT", "ALL", ("emoji", "\U0001F604")]],
    cta_brand="MID-BRAIN ACTIVITY",
    cta_1=["WANT", "YOUR", "CHILD"],
    cta_2=["TO", "TRY", "THIS?"],
    cta_school=("THE MAPLE", "INTERNATIONAL SCHOOL"),
    cta_place="BHADRA",
    cta_contact="CONTACT NOW",
    cta_phone="8440076300",
)

# Shot list: name, out_start, out_end, src_start, speed, push (end zoom - 1), cx, cy[, base_zoom]
# cx/cy = crop-box centre in the 478x730 cropped source (cy is clamped so the box stays inside).
SHOTS = [
    # HOOK
    ("PINK",    0.0,  1.0, 70.60, 1.00, 0.10, 239, 365),
    ("DORA",    1.0,  2.0, 81.30, 1.00, 0.08, 239, 365),
    ("GRAPES",  2.0,  3.5, 55.80, 1.00, 0.10, 239, 365),
    # TITLE
    ("TITLE",   3.5,  6.5, 17.60, 1.00, 0.08, 239, 365),
    # STEP 1: seal the eyes
    ("PADS",    6.5,  9.0, 11.00, 1.00, 0.10, 239, 365),
    ("TIE",     9.0, 11.5, 24.40, 1.00, 0.10, 239, 365),
    # ROUND 1: colors
    ("PINK2",  11.5, 13.5, 70.60, 0.55, 0.06, 239, 365),
    # ROUND 2: shapes
    ("SHAPE1", 13.5, 15.5, 32.40, 1.00, 0.08, 239, 365),
    ("SHAPE2", 15.5, 17.0, 48.90, 1.00, 0.08, 239, 365),
    # ROUND 3: pictures
    ("GRAPES2", 17.0, 18.5, 54.40, 1.00, 0.08, 239, 365),
    ("DORA2",  18.5, 20.0, 81.70, 0.80, 0.06, 239, 365),
    # ROUND 4: words & numbers
    ("BOOK",   20.0, 23.0, 109.55, 0.62, 0.06, 239, 365),
    # REACTIONS
    ("LAUGH1", 23.0, 24.5, 105.50, 1.00, 0.08, 239, 365),
    ("HUG",    24.5, 26.5, 112.00, 0.80, 0.08, 239, 365),
    ("LAUGH2", 26.5, 28.0, 118.50, 1.00, 0.08, 239, 365),
    # CTA background (slow-mo, under a dark scrim)
    ("CTA",    28.0, 34.0, 119.90, 0.40, 0.06, 239, 365),
]

# beats used for white flashes (big transitions)
FLASHES = [3.5, 11.5, T_REACT, T_CTA]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out_cubic(u):
    return 1 - (1 - clamp(u)) ** 3


def ease_out_back(u):
    u = clamp(u)
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (u - 1) ** 3 + c1 * (u - 1) ** 2


@functools.lru_cache(maxsize=None)
def font(size):
    return ImageFont.truetype(FONT, int(size))


@functools.lru_cache(maxsize=None)
def emoji_font():
    return ImageFont.truetype(EMOJI_FONT, 109)


@functools.lru_cache(maxsize=None)
def text_rgba(text, size, fill=WHITE, stroke=0, stroke_fill=BLACK, shadow=True):
    """Anti-aliased text with optional stroke + soft shadow, as a straight-alpha RGBA."""
    f = font(size)
    pad = int(size * 0.35) + stroke
    l, t, r, b = f.getbbox(text, stroke_width=stroke)
    w, h = r - l + 2 * pad, b - t + 2 * pad
    ox, oy = pad - l, pad - t

    def mask(stroke_w):
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).text((ox, oy), text, font=f, fill=255, stroke_width=stroke_w)
        return m

    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if shadow:
        sm = mask(stroke).filter(ImageFilter.GaussianBlur(size * 0.045))
        sm = ImageChops.offset(sm, 0, int(size * 0.06))
        sm = sm.point(lambda v: int(v * 0.65))
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sh.putalpha(sm)
        out = Image.alpha_composite(out, sh)
    if stroke:
        st = Image.new("RGBA", (w, h), stroke_fill + (0,))
        st.putalpha(mask(stroke))
        out = Image.alpha_composite(out, st)
    fl = Image.new("RGBA", (w, h), fill + (0,))
    fl.putalpha(mask(0))
    res = Image.alpha_composite(out, fl)
    res.info["pad"] = pad
    return res


def ink_w(im):
    """Width of the visible glyphs (text_rgba images carry transparent padding)."""
    return im.width - 2 * im.info.get("pad", 0)


@functools.lru_cache(maxsize=None)
def emoji_rgba(ch, size):
    im = Image.new("RGBA", (136, 128), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((0, 0), ch, font=emoji_font(), embedded_color=True)
    bb = im.getbbox() or (0, 0, 136, 128)
    im = im.crop(bb)
    s = size / max(im.size)
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)


@functools.lru_cache(maxsize=None)
def pill_rgba(w, h, r, fill):
    s = 3
    im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w * s - 1, h * s - 1], r * s, fill=fill)
    return im.resize((w, h), Image.LANCZOS)


def blit(img, rgba, x, y, scale=1.0, alpha=1.0, anchor="c", rot=0.0):
    """Paste an RGBA at (x, y). anchor: c=centre, l=left-centre, t=top-centre."""
    if rot:
        rgba = rgba.rotate(rot, resample=Image.BICUBIC, expand=True)
    if abs(scale - 1.0) > 1e-3:
        rgba = rgba.resize((max(1, int(rgba.width * scale)), max(1, int(rgba.height * scale))), Image.BICUBIC)
    w, h = rgba.size
    if anchor == "c":
        x, y = x - w // 2, y - h // 2
    elif anchor == "l":
        y = y - h // 2
    elif anchor == "t":
        x = x - w // 2
    a = rgba.getchannel("A")
    if alpha < 0.999:
        a = a.point(lambda v: int(v * alpha))
    img.paste(rgba.convert("RGB"), (int(x), int(y)), a)


def pop(t_local, dur=0.24):
    """(scale, alpha) for a pop-in with overshoot."""
    u = t_local / dur
    if u <= 0:
        return 0.0, 0.0
    return 0.55 + 0.45 * ease_out_back(u), clamp(u * 3)


def fade_out(t_local, total, dur=0.14):
    return clamp((total - t_local) / dur)


# --------------------------------------------------------------------------- #
# overlay components (each returns a draw(img, t_local, total) function)
# --------------------------------------------------------------------------- #
def kinetic_lines(lines, size, y_center, start, interval, colors=None, line_gap=1.08,
                  max_w=940, stroke=None, line_delay=0.0, scale_by_line=None):
    """Words pop in one by one, lines centred. colors: {word: rgb}. scale_by_line: {line_idx: factor}."""
    colors = colors or {}
    scale_by_line = scale_by_line or {}
    stroke = stroke if stroke is not None else max(6, size // 11)
    layout = []  # (rgba, cx, cy, t_appear, scale)
    n_words = 0
    for li, words in enumerate(lines):
        sz = size * scale_by_line.get(li, 1.0)
        imgs = [emoji_rgba(w[1], int(sz * 0.95)) if isinstance(w, tuple) else
                text_rgba(w, int(sz), colors.get(w, WHITE), stroke) for w in words]
        gap = int(sz * 0.22)
        total_w = sum(ink_w(i) for i in imgs) + gap * (len(imgs) - 1)
        k = min(1.0, max_w / max(1, total_w))
        cy = y_center + (li - (len(lines) - 1) / 2) * size * line_gap
        x = W / 2 - total_w * k / 2
        for im in imgs:
            cx = x + ink_w(im) * k / 2
            layout.append((im, cx, cy, start + n_words * interval + li * line_delay, k))
            x += (ink_w(im) + gap) * k
            n_words += 1

    def draw(img, tl, total):
        fo = fade_out(tl, total)
        for im, cx, cy, ta, k in layout:
            s, a = pop(tl - ta)
            if a <= 0:
                continue
            blit(img, im, cx, cy, scale=s * k, alpha=a * fo)
    return draw


def underline_sweep(y, x0, x1, start, dur=0.28, height=16, color=YELLOW):
    def draw(img, tl, total):
        u = ease_out_cubic((tl - start) / dur)
        if u <= 0:
            return
        w = int((x1 - x0) * u)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([x0, y, x0 + w, y + height], height // 2, fill=color)
    return draw


def emoji_pop(ch, size, cx, cy, start, bob=0.0):
    im = emoji_rgba(ch, size)

    def draw(img, tl, total):
        s, a = pop(tl - start, 0.3)
        if a <= 0:
            return
        dy = math.sin((tl - start) * 7) * bob
        blit(img, im, cx, cy + dy, scale=s, alpha=a * fade_out(tl, total))
    return draw


def chip(label, name, emoji, x, y, start, max_text_w=620):
    """Left-anchored dark pill: small yellow label over big white name, emoji at right."""
    name_sz = 92
    while font(name_sz).getlength(name) > max_text_w and name_sz > 50:
        name_sz -= 4
    lab = text_rgba(label, 40, YELLOW, 0, BLACK, shadow=False)
    nm = text_rgba(name, name_sz, WHITE, 0, BLACK, shadow=False)
    em = emoji_rgba(emoji, 118)
    pad_x = 48
    h = 180
    w = pad_x * 2 + 22 + max(ink_w(lab), ink_w(nm)) + 30 + em.width
    card = pill_rgba(w, h, 44, (12, 12, 16, 214)).copy()
    card.alpha_composite(pill_rgba(14, h - 52, 7, YELLOW + (255,)), (20, 26))
    tx = pad_x + 22
    card.alpha_composite(lab, (tx - lab.info["pad"], 24 - lab.info["pad"]))
    card.alpha_composite(nm, (tx - nm.info["pad"], 80 - nm.info["pad"]))
    card.alpha_composite(em, (w - pad_x - em.width + 8, (h - em.height) // 2))

    def draw(img, tl, total):
        u = clamp((tl - start) / 0.42)
        if u <= 0:
            return
        off = (1 - ease_out_back(u)) * (w + 80)
        a = fade_out(tl, total, 0.12)
        blit(img, card, x - off, y, alpha=a, anchor="l")
    return draw


def caption(text, y, start, size=68, color=WHITE):
    im = text_rgba(text, size, color, 7)

    def draw(img, tl, total):
        s, a = pop(tl - start, 0.22)
        if a <= 0:
            return
        blit(img, im, 60 + ink_w(im) / 2, y, scale=s, alpha=a * fade_out(tl, total))
    return draw


def pips(active_idx_fn, y=262):
    """Four story-style progress pips; active_idx_fn(t_abs)->(index, t_since_round_start)."""
    pw, gap = 190, 20
    x0 = (W - (4 * pw + 3 * gap)) // 2
    base = pill_rgba(pw, 14, 7, (255, 255, 255, 100))

    def draw(img, tl, total, t_abs=0.0):
        idx, since = active_idx_fn(t_abs)
        d = ImageDraw.Draw(img)
        for i in range(4):
            x = x0 + i * (pw + gap)
            img.paste(base.convert("RGB"), (x, y), base.getchannel("A"))
            if i < idx:
                fill_w = pw
            elif i == idx:
                fill_w = int(pw * ease_out_cubic(since / 0.5))
            else:
                fill_w = 0
            if fill_w > 0:
                d.rounded_rectangle([x, y, x + fill_w, y + 14], 7, fill=YELLOW)
    draw.wants_abs = True
    return draw


# --------------------------------------------------------------------------- #
# scene timeline
# --------------------------------------------------------------------------- #
ROUND_STARTS = [11.5, 13.5, 17.0, 20.0]
ROUND_END = T_REACT


def round_idx(t):
    idx = max(i for i, s in enumerate(ROUND_STARTS) if t >= s)
    return idx, t - ROUND_STARTS[idx]


def build_overlays():
    ov = []  # (t0, t1, drawfn)
    C = COPY

    # -- HOOK ---------------------------------------------------------------
    ov.append((0.0, 1.5, kinetic_lines([[C["hook_1"]]], 138, 470, 0.04, 0.0, stroke=14, max_w=960)))
    ov.append((0.0, 1.5, underline_sweep(556, 70, 1010, 0.18, 0.3, 18)))
    hook2 = kinetic_lines(C["hook_2"], 124, 430, 1.55, 0.13, colors={"COLOR?": YELLOW},
                          line_gap=1.12, scale_by_line={2: 1.0})
    ov.append((1.5, 3.5, hook2))
    ov.append((1.5, 3.5, emoji_pop("\U0001F92F", 150, W // 2, 705, 2.55, bob=6)))

    # -- TITLE --------------------------------------------------------------
    ov.append((3.5, 6.5, emoji_pop("\U0001F9E0", 170, W // 2, 335, 3.52)))
    ov.append((3.5, 6.5, kinetic_lines([[C["title_1"]]], 168, 490, 3.62, 0.0, stroke=14, max_w=980)))

    plaque = Image.new("RGBA", (560, 150), (0, 0, 0, 0))
    plaque.alpha_composite(pill_rgba(560, 150, 30, YELLOW + (255,)))
    t2 = text_rgba(C["title_2"], 98, INK, 0, BLACK, shadow=False)
    plaque.alpha_composite(t2, ((560 - t2.width) // 2, (150 - t2.height) // 2))

    def title_plaque(img, tl, total):
        s, a = pop(tl - 3.8, 0.3)
        if a > 0:
            blit(img, plaque, W // 2, 640, scale=s, alpha=a * fade_out(tl, total), rot=-4)
    ov.append((3.5, 6.5, title_plaque))
    sub = text_rgba(C["title_sub"], 58, WHITE, 6)
    pointer = emoji_rgba("\U0001F447", 70)

    def title_sub(img, tl, total):
        s, a = pop(tl - 4.6, 0.25)
        if a <= 0:
            return
        gap = 14
        tw = ink_w(sub)
        total_w = tw + gap + pointer.width
        x0 = W / 2 - total_w / 2
        cy = 1290
        blit(img, sub, x0 + tw / 2, cy, scale=s, alpha=a * fade_out(tl, total))
        blit(img, pointer, x0 + tw + gap + pointer.width / 2, cy + 4 + math.sin((tl - 4.6) * 9) * 8,
             scale=s, alpha=a * fade_out(tl, total))
    ov.append((3.5, 6.5, title_sub))

    # -- STEP 1 -------------------------------------------------------------
    ov.append((6.5, 11.5, chip(*C["step1"], 60, 1150, 6.5)))
    ov.append((6.7, 9.0, caption(C["step1_cap_a"], 1335, 6.7)))
    ov.append((9.0, 11.5, caption(C["step1_cap_b"], 1335, 9.0)))

    # -- ROUNDS -------------------------------------------------------------
    ends = ROUND_STARTS[1:] + [ROUND_END]
    for (s, e), (lab, name, em, cap) in zip(zip(ROUND_STARTS, ends), C["rounds"]):
        ov.append((s, e, chip(lab, name, em, 60, 1150, s)))
        ov.append((s + 0.2, e, caption(cap, 1335, s + 0.2)))
    ov.append((ROUND_STARTS[0], ROUND_END, pips(round_idx)))

    # -- REACTION -----------------------------------------------------------
    ov.append((T_REACT, T_CTA, kinetic_lines(C["react"], 128, 440, T_REACT + 0.1, 0.16, colors={"SMILES": YELLOW, "ALL": YELLOW},
                                         line_gap=1.1, max_w=940)))

    # -- CTA / end card ----------------------------------------------------------
    brand = text_rgba(C["cta_brand"], 46, WHITE, 0, BLACK, shadow=False)
    brain = emoji_rgba("\U0001F9E0", 62)

    def cta_brand(img, tl, total):
        s, a = pop(tl - (T_CTA + 0.25), 0.3)
        if a <= 0:
            return
        tw = ink_w(brand)
        x0 = W / 2 - (brain.width + 16 + tw) / 2
        blit(img, brain, x0 + brain.width / 2, 430, scale=s, alpha=a)
        blit(img, brand, x0 + brain.width + 16 + tw / 2, 434, scale=s, alpha=a)
    ov.append((T_CTA, TOTAL, cta_brand))
    ov.append((T_CTA, TOTAL, kinetic_lines([C["cta_1"], C["cta_2"]], 118, 600, T_CTA + 0.55, 0.16,
                                          colors={"THIS?": YELLOW}, line_gap=1.1, max_w=940)))

    def divider(img, tl, total):
        u = ease_out_cubic((tl - (T_CTA + 1.35)) / 0.3)
        if u > 0:
            w = int(220 * u)
            ImageDraw.Draw(img).rounded_rectangle([W // 2 - w // 2, 756, W // 2 + w // 2, 764], 4, fill=YELLOW)
    ov.append((T_CTA, TOTAL, divider))

    sch1, sch2 = C["cta_school"]
    ov.append((T_CTA, TOTAL, kinetic_lines([sch1.split()], 94, 855, T_CTA + 1.5, 0.12, stroke=9, max_w=940)))
    ov.append((T_CTA, TOTAL, kinetic_lines([sch2.split()], 62, 955, T_CTA + 1.75, 0.12, stroke=7, max_w=940)))
    ov.append((T_CTA, TOTAL, kinetic_lines([[("emoji", "\U0001F4CD"), C["cta_place"]]], 58, 1038, T_CTA + 2.1, 0.12,
                                          colors={C["cta_place"]: YELLOW}, stroke=7, max_w=940)))
    ov.append((T_CTA, TOTAL, kinetic_lines([C["cta_contact"].split()], 46, 1140, T_CTA + 2.5, 0.1, stroke=6, max_w=940)))

    ph_txt = text_rgba(C["cta_phone"], 88, INK, 0, BLACK, shadow=False)
    ph_em = emoji_rgba("\U0001F4DE", 84)
    pw = ink_w(ph_txt) + 22 + ph_em.width + 100
    ph = 150
    phone = pill_rgba(pw, ph, 75, YELLOW + (255,)).copy()
    phone.alpha_composite(ph_em, (50, (ph - ph_em.height) // 2))
    phone.alpha_composite(ph_txt, (50 + ph_em.width + 22 - ph_txt.info["pad"], (ph - ph_txt.height) // 2 + 3))

    def cta_phone(img, tl, total):
        s, a = pop(tl - (T_CTA + 2.7), 0.34)
        if a <= 0:
            return
        pulse = 1.0 + 0.03 * math.sin((tl - T_CTA - 2.7) * 7.5) if tl > T_CTA + 3.1 else 1.0
        blit(img, phone, W // 2, 1262, scale=s * pulse, alpha=a)
    ov.append((T_CTA, TOTAL, cta_phone))
    return ov


# --------------------------------------------------------------------------- #
# footage
# --------------------------------------------------------------------------- #
def decode_shot(video, src_start, out_dur, speed):
    n = int(round(out_dur * FPS))
    vf = f"crop={SRC_W}:{CROP_H}:0:0"
    if speed < 0.999:
        vf += f",setpts=PTS/{speed},minterpolate=fps={FPS}:mi_mode=blend"
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{src_start:.3f}", "-t", f"{out_dur * speed + 0.25:.3f}",
           "-i", video, "-vf", vf, "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, stdout=subprocess.PIPE, check=True).stdout
    fsz = SRC_W * CROP_H * 3
    frames = np.frombuffer(raw, np.uint8)[: (len(raw) // fsz) * fsz].reshape(-1, CROP_H, SRC_W, 3)
    if len(frames) < n:  # pad with the last frame if the source ran out
        frames = np.concatenate([frames, np.repeat(frames[-1:], n - len(frames), 0)])
    return frames


def compose_footage(src, z, cx, cy, dx=0.0, dy=0.0):
    """Zoomed crop of the 478x730 source -> 1080x1920 canvas (footage fading into a dark ambient base)."""
    bw = SRC_W / z
    bh = bw * VID_H / W
    x0 = clamp(cx - bw / 2 + dx, 0, SRC_W - bw)
    y0 = clamp(cy - bh / 2 + dy, 0, CROP_H - bh)
    vid = Image.fromarray(src).resize((W, VID_H), Image.BICUBIC, box=(x0, y0, x0 + bw, y0 + bh))
    vid = vid.filter(ImageFilter.UnsharpMask(radius=2.0, percent=55, threshold=2))

    # Bottom: the footage fades into a dark ambient colour field derived from itself.
    vis = vid.crop((0, SHIFT, W, VID_H))
    low = vis.resize((9, 12), Image.BILINEAR).resize((W, VIS_H), Image.BICUBIC)
    low = ImageEnhance.Brightness(low).enhance(0.30)
    fade_from = VIS_H - 250
    canvas = Image.new("RGB", (W, H))
    canvas.paste(vis.crop((0, 0, W, fade_from)), (0, 0))
    u = np.linspace(0, 1, VIS_H - fade_from)
    fade_mask = Image.fromarray((u * u * (3 - 2 * u) * 255).astype(np.uint8)[:, None].repeat(W, 1))  # smoothstep: no visible seam
    canvas.paste(Image.composite(low.crop((0, fade_from, W, VIS_H)), vis.crop((0, fade_from, W, VIS_H)), fade_mask),
                 (0, fade_from))
    canvas.paste(low.crop((0, VIS_H - 1, W, VIS_H)).resize((W, H - VIS_H), Image.NEAREST), (0, VIS_H))
    return canvas


# --------------------------------------------------------------------------- #
# renderer
# --------------------------------------------------------------------------- #
class Renderer:
    def __init__(self, video):
        self.video = video
        self.overlays = build_overlays()
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H * 0.45) / (H * 0.6)) ** 2)
        self.vig = Image.fromarray((np.clip((r - 0.65) / 0.8, 0, 1) ** 1.6 * 120).astype(np.uint8))
        rng = np.random.default_rng(7)
        self.grain = [Image.fromarray(rng.integers(0, 9, (H, W), dtype=np.uint8)).convert("RGB") for _ in range(6)]
        # scrims: top (headline zone) and bottom (chip/caption zone), vertical alpha ramps
        self.scrim_top = np.clip(1 - np.arange(900) / 900.0, 0, 1) ** 1.4
        self.scrim_title = np.clip(1 - (np.arange(1000) - 420) / 600.0, 0, 1)
        self.scrim_bot = np.clip(np.arange(H - 1000) / 450.0, 0, 1) ** 1.2
        self._cache = {}

    def scrim_at(self, t):
        """(top, bottom, cta) scrim opacities."""
        if t < 3.5:
            top = 0.60
        elif t < 6.3:
            top = 0.85
        elif t < 6.5:
            top = 0.85 * (6.5 - t) / 0.2
        elif t < ROUND_STARTS[0]:
            top = 0.0
        elif t < ROUND_END:
            top = 0.38
        elif t < T_CTA:
            top = 0.58
        else:
            top = 0.0
        bot = 0.50 * clamp((t - 4.2) / 0.4) if 4.2 <= t < ROUND_END else 0.0
        cta = 0.70 * ease_out_cubic((t - T_CTA) / 0.4) if t >= T_CTA else 0.0
        return top, bot, cta

    def shot_frames(self, idx):
        if idx not in self._cache:
            self._cache.clear()
            name, t0, t1, src, spd, push, cx, cy, *_ = SHOTS[idx]
            self._cache[idx] = decode_shot(self.video, src, t1 - t0, spd)
        return self._cache[idx]

    def frame(self, t):
        idx = max(i for i, s in enumerate(SHOTS) if t >= s[1] - 1e-6)
        name, t0, t1, src, spd, push, cx, cy, *rest = SHOTS[idx]
        z0 = rest[0] if rest else 1.0
        tl = t - t0
        fi = min(int(round(tl * FPS)), int(round((t1 - t0) * FPS)) - 1)
        frames = self.shot_frames(idx)
        u = tl / (t1 - t0)
        z = z0 * (1 + push * u) * (1 + 0.10 * (1 - ease_out_cubic(tl / 0.30)))
        dx = dy = 0.0
        if t < 0.5:  # hook slam shake
            amp = 5.0 * math.exp(-9 * t)
            dx, dy = amp * math.sin(t * 95), amp * math.cos(t * 80)
        img = compose_footage(frames[fi], z, cx, cy, dx, dy)

        img = ImageEnhance.Contrast(img).enhance(1.05)
        img = ImageEnhance.Color(img).enhance(1.08)
        img.paste((0, 0, 0), (0, 0), self.vig)
        img = ImageChops.add(img, self.grain[int(t * FPS) % 6], 1.0, -4)

        top, bot, cta = self.scrim_at(t)
        if top > 0:
            curve = self.scrim_title if 3.5 <= t < 6.5 else self.scrim_top
            m = Image.fromarray((curve * top * 255).astype(np.uint8)[:, None].repeat(W, 1))
            img.paste((0, 0, 0), (0, 0), m)
        if bot > 0:
            m = Image.fromarray((self.scrim_bot * bot * 255).astype(np.uint8)[:, None].repeat(W, 1))
            img.paste((0, 0, 0), (0, 1000), m)
        if cta > 0:
            img.paste((0, 0, 0), (0, 0), Image.new("L", (W, H), int(cta * 255)))

        for t0_, t1_, fn in self.overlays:
            if t0_ <= t < t1_:
                # overlays get ABSOLUTE time and their absolute end time
                if getattr(fn, "wants_abs", False):
                    fn(img, t, t1_, t_abs=t)
                else:
                    fn(img, t, t1_)

        fl = 0.0
        for ft in FLASHES:
            if ft <= t < ft + 0.17:
                fl = max(fl, 0.55 * (1 - (t - ft) / 0.17))
        if fl > 0:
            img = Image.blend(img, Image.new("RGB", (W, H), WHITE), fl)
        return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("out")
    ap.add_argument("--preview", nargs="*", type=float, help="render only these timestamps to PNGs in OUT dir")
    a = ap.parse_args()
    r = Renderer(a.source)

    if a.preview:
        os.makedirs(a.out, exist_ok=True)
        for t in a.preview:
            r.frame(t).save(os.path.join(a.out, f"t{t:05.2f}.png"))
            print("wrote", t, flush=True)
        return

    n = int(round(TOTAL * FPS))
    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-vf", "scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p",
         "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high", "-level", "4.2",
         "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
         "-movflags", "+faststart", a.out],
        stdin=subprocess.PIPE)
    for i in range(n):
        enc.stdin.write(r.frame(i / FPS).tobytes())
        if i % 30 == 0:
            print(f"frame {i}/{n}", flush=True)
    enc.stdin.close()
    enc.wait()
    print("done", a.out)


if __name__ == "__main__":
    sys.exit(main())
