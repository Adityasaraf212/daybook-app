# Mid-Brain Activity: promo reel

`midbrain-activity-reel.mp4`: 34 s, 1080x1920 (9:16), 30 fps, H.264 + AAC, about -14 LUFS.
`midbrain-activity-reel-share.mp4`: same cut, smaller file (about 17 MB) for WhatsApp / upload-limited channels.
`cover.png`: suggested cover / thumbnail (hook frame with the question on screen).

Re-cut from the already-edited 130 s clip (`VID-20261010-WA0023.mp4`). The old voiceover,
the "Welcome to my channel" / "Thanks for watching" cards and the burned-in yellow captions
are gone: the caption band is cropped off and everything on screen is new.

## Structure

| Time | What | Why |
|------|------|-----|
| 0.0-3.5 | **Hook**: three card-in-hand shots (pink, Doraemon, grapes), `BLINDFOLDED.` then `CAN THEY STILL TELL THE COLOR?` | Strongest visuals first, curiosity question, riser into the drop |
| 3.5-6.5 | Title: `MID-BRAIN ACTIVITY`, "Here's how it works" | Names the activity |
| 6.5-11.5 | Step 1: cotton pads, then the blindfold | Shows the eyes are fully covered |
| 11.5-23.0 | Rounds 1-4: colors, shapes, pictures, words + numbers (progress tracker at top) | Escalating difficulty keeps people watching; each round asks the viewer a question |
| 23.0-28.0 | `THE SMILES SAY IT ALL` | Emotional payoff |
| 28.0-34.0 | End card: `WANT YOUR CHILD TO TRY THIS?`, The Maple International School, Bhadra, `CONTACT NOW 8440076300` | School name, place and phone number are in the `COPY` dict (`cta_school`, `cta_place`, `cta_phone`) |

The bottom ~17% of the frame is a deliberate dark fade, which is where Instagram / Shorts overlay
their caption and buttons.

## Rebuild / edit

Needs `ffmpeg`, Python 3, `numpy`, `Pillow`, and the Inter Black + Noto Color Emoji fonts.

```bash
cd reels/midbrain-activity
python3 build_video.py SOURCE.mp4 silent.mp4      # ~4 min; edit COPY / SHOTS at the top first
python3 build_audio.py track.wav                  # original synthesized soundtrack, 3 s
ffmpeg -i silent.mp4 -i track.wav -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p \
       -c:a aac -b:a 192k -movflags +faststart -shortest reel.mp4
python3 build_video.py SOURCE.mp4 stills/ --preview 0.5 2.9 12.0   # quick still-frame check
```

* All on-screen copy lives in the `COPY` dict at the top of `build_video.py`.
* Shot choices / timings are in `SHOTS` (`name, out_start, out_end, src_start, speed, push, cx, cy`).
  `build_audio.py` imports the same timings, so music and sound effects stay in sync with the cuts.
* The soundtrack is generated from scratch (no samples or licensed music). If you'd rather use a
  trending sound, upload the video and pick one in Instagram: the on-screen text works muted.

## Known limits

* The source is only 478x850, so the footage is upscaled about 2.3x and looks soft at full-screen.
  Raw phone clips would be sharper.
* Some in-source cuts and the original transitions are glitchy, so those frames were avoided.
