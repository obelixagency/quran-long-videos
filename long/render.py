"""Long-form 16:9 video (1920×1080): calm nature background, a fixed soft panel, and the Quran text
written word by word in sync with the reciter (Quran.com word timings) – optionally with the English
translation (Pickthall) under it.

Built for 20–60 minute videos:
  * cards are built lazily and dropped when done (memory stays small)
  * the panel, brand and reciter line are one static layer; only the text changes
  * fully written words are cached, so each frame only draws the word being written
"""
import bisect
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .common import ROOT, ar_num, download, media_duration, run

W, H, FPS = 1920, 1080, 24
FONTS = ROOT / "assets" / "fonts"
QURAN_FONT = FONTS / "AmiriQuran-Regular.ttf"
UI_FONT = FONTS / "Amiri-Regular.ttf"
UI_BOLD = FONTS / "Amiri-Bold.ttf"
EN_SERIF = FONTS / "en" / "CormorantGaramond-Italic.ttf"
EN_SANS = FONTS / "en" / "Jost.ttf"
FONT_URLS = {
    QURAN_FONT: "https://github.com/google/fonts/raw/main/ofl/amiriquran/AmiriQuran-Regular.ttf",
    UI_FONT: "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf",
    UI_BOLD: "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Bold.ttf",
    EN_SERIF: "https://github.com/google/fonts/raw/main/ofl/cormorantgaramond/CormorantGaramond-Italic%5Bwght%5D.ttf",
    EN_SANS: "https://github.com/google/fonts/raw/main/ofl/jost/Jost%5Bwght%5D.ttf",
}
GOLD = (236, 214, 160, 255)
WHITE = (255, 255, 255, 255)
BEIGE = (243, 235, 221, 255)
LEAD, GAP, TAIL = 1.2, 0.6, 2.5
FADE = 0.35
PANEL = (110, 150, W - 110, 880)  # the fixed panel behind the text


def font(path, size, weight=None):
    if not path.exists():
        download(FONT_URLS[path], path)
    layout = ImageFont.Layout.RAQM if path.parent == FONTS else ImageFont.Layout.BASIC
    f = ImageFont.truetype(str(path), size, layout_engine=layout)
    if weight:
        try:
            f.set_variation_by_axes([weight])
        except Exception:  # noqa: BLE001 – static font
            pass
    return f


# ============================================================== layout helpers
def _wrap_rtl(tokens, f, max_w):
    lines, cur = [], []
    for tok in tokens:
        if cur and f.getlength(" ".join(cur + [tok]), direction="rtl") > max_w:
            lines.append(cur)
            cur = [tok]
        else:
            cur.append(tok)
    return lines + ([cur] if cur else [])


def _wrap_ltr(words, f, max_w):
    lines, cur = [], []
    for w in words:
        if cur and f.getlength(" ".join(cur + [w])) > max_w:
            lines.append(cur)
            cur = [w]
        else:
            cur.append(w)
    return [" ".join(l) for l in lines + ([cur] if cur else [])]


class Layout:
    def __init__(self, english):
        self.english = english
        self.max_w = PANEL[2] - PANEL[0] - 170
        # Arabic area (height) and the smallest Quran font we accept before splitting an ayah into parts
        self.ar_h = 330 if english else 520
        self.ar_min = 54 if english else 66
        self.ar_start = 92 if english else 112

    def fit_ar(self, tokens, allow_small=False):
        size = self.ar_start
        while True:
            f = font(QURAN_FONT, size)
            lines = _wrap_rtl(tokens, f, self.max_w)
            lh = int(size * 1.8)
            if len(lines) * lh <= self.ar_h:
                return f, lines, lh
            if size <= (40 if allow_small else self.ar_min):
                return (f, lines, lh) if allow_small else None
            size -= 2

    def fit_en(self, text):
        size = 44
        while True:
            f = font(EN_SERIF, size, 500)
            lines = _wrap_ltr(text.split(), f, self.max_w + 40)
            lh = int(size * 1.28)
            if len(lines) * lh <= 250 or size <= 26:
                return f, lines, lh
            size -= 2


def split_ayah(layout, tokens):
    """Returns a list of token chunks, each of which fits the panel at a readable size."""
    if layout.fit_ar(tokens):
        return [tokens]
    for k in range(2, 12):
        per = -(-len(tokens) // k)
        chunks = [tokens[i:i + per] for i in range(0, len(tokens), per)]
        if all(layout.fit_ar(c) for c in chunks):
            return chunks
    per = -(-len(tokens) // 12)
    return [tokens[i:i + per] for i in range(0, len(tokens), per)]


# ============================================================== layers
def static_layer(*, brand, section, reciter_line, english):
    """Panel + brand (top left) + section title (top right) + reciter line (bottom). Drawn once."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle(PANEL, radius=56, fill=(10, 16, 14, 150))
    img = img.filter(ImageFilter.GaussianBlur(22))
    d = ImageDraw.Draw(img)
    if english:
        f_b, f_s, f_r = font(EN_SANS, 30, 500), font(EN_SANS, 30, 450), font(EN_SANS, 32, 420)
        _spaced(d, (PANEL[0] + 40, 92), brand.upper(), f_b, (255, 255, 255, 190), 9, anchor="l")
        _spaced(d, (PANEL[2] - 40, 92), section.upper(), f_s, GOLD, 6, anchor="r")
        d.text((W // 2, 955), reciter_line, font=f_r, fill=(255, 255, 255, 215), anchor="mm")
    else:
        f_b, f_s, f_r = font(UI_BOLD, 40), font(UI_BOLD, 40), font(UI_FONT, 40)
        d.text((PANEL[2] - 30, 92), brand, font=f_b, fill=(255, 255, 255, 200), anchor="rm", direction="rtl")
        d.text((PANEL[0] + 30, 92), section, font=f_s, fill=GOLD, anchor="lm", direction="rtl")
        d.text((W // 2, 955), reciter_line, font=f_r, fill=(255, 255, 255, 215), anchor="mm", direction="rtl")
    return img


def _spaced(d, xy, text, f, fill, spacing, anchor="m"):
    widths = [f.getlength(ch) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x = {"l": xy[0], "r": xy[0] - total}.get(anchor, xy[0] - total / 2)
    for ch, w in zip(text, widths):
        d.text((x, xy[1]), ch, font=f, fill=fill, anchor="lm")
        x += w + spacing


def _line_layer(text, f, cx, cy, color):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((cx + 3, cy + 4), text, font=f, fill=(0, 0, 0, 190), anchor="mm", direction="rtl")
    layer = layer.filter(ImageFilter.GaussianBlur(5))
    ImageDraw.Draw(layer).text((cx, cy), text, font=f, fill=color, anchor="mm", direction="rtl")
    return layer


def build_card(layout, spec):
    """spec: {"tokens", "label", "en"} → {"base": RGBA, "words": [(sprite, x, y)]}"""
    fit = layout.fit_ar(spec["tokens"]) or layout.fit_ar(spec["tokens"], allow_small=True)
    f, lines, lh = fit
    ar_h = len(lines) * lh
    en = spec.get("en")
    en_fit = layout.fit_en(en) if en else None
    en_h = (len(en_fit[1]) * en_fit[2] + 50) if en_fit else 0
    label_h = 64
    block = ar_h + en_h + label_h
    mid = (PANEL[1] + 890) // 2 + 10
    top = mid - block // 2
    cx = W // 2

    base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    y = top + ar_h
    if en_fit:
        fe, elines, elh = en_fit
        y += 22
        d.line((cx - 120, y, cx + 120, y), fill=GOLD[:3] + (150,), width=2)
        y += 26
        for ln in elines:
            d.text((cx + 2, y + elh // 2 + 2), ln, font=fe, fill=(0, 0, 0, 150), anchor="mm")
            d.text((cx, y + elh // 2), ln, font=fe, fill=BEIGE, anchor="mm")
            y += elh
    y += 18
    if layout.english:
        d.text((cx, y + 22), spec["label"], font=font(EN_SANS, 30, 450), fill=GOLD, anchor="mm")
    else:
        d.text((cx, y + 24), spec["label"], font=font(UI_BOLD, 38), fill=GOLD, anchor="mm", direction="rtl")

    words = []
    space = f.getlength(" ")
    for li, toks in enumerate(lines):
        cy = top + li * lh + lh // 2
        text = " ".join(toks)
        lw = f.getlength(text, direction="rtl")
        widths = [f.getlength(t, direction="rtl") for t in toks]
        k = lw / (sum(widths) + space * (len(toks) - 1))
        right = cx + lw / 2
        layer = _line_layer(text, f, cx, cy, WHITE)
        y0, y1 = int(cy - lh * 0.62), int(cy + lh * 0.62)
        cum = 0.0
        for j, w in enumerate(widths):
            r = right - cum * k + (space * k / 2 if j else 30)
            left = right - (cum + w) * k - (space * k / 2 if j < len(toks) - 1 else 30)
            box = (max(0, int(left)), max(0, y0), min(W, int(r + 1)), min(H, y1))
            words.append((layer.crop(box), box[0], box[1]))
            cum += w + space
    return {"base": base, "words": words}


# ============================================================== timeline
def _alpha(img, mult):
    arr = np.array(img)
    a = arr[..., 3].astype(np.float32)
    a *= mult if np.isscalar(mult) else mult[None, :]
    arr[..., 3] = np.clip(a, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def _wipe(width, p, soft=28.0):
    x = np.arange(width, dtype=np.float32)
    return np.clip((x - width * (1.0 - p) + soft) / soft, 0.0, 1.0)


class Timeline:
    """cards: [{"spec": {...}, "window": (t0, t1), "words": [(ws, we)] absolute}] sorted by time."""

    def __init__(self, layout, static, cards, total):
        self.layout, self.static, self.cards, self.total = layout, static, cards, total
        self.starts = [c["window"][0] for c in cards]
        self.built = {}
        self.settled = {}  # ci -> (n, canvas with static + base + first n words)

    def _card(self, ci):
        if ci not in self.built:
            for old in [k for k in self.built if k < ci - 1]:
                self.built.pop(old, None)
                self.settled.pop(old, None)
            self.built[ci] = build_card(self.layout, self.cards[ci]["spec"])
        return self.built[ci]

    def state(self, t):
        i = bisect.bisect_right(self.starts, t) - 1
        for ci in (i, i - 1):
            if 0 <= ci < len(self.cards):
                t0, t1 = self.cards[ci]["window"]
                if t0 <= t <= t1:
                    ca = round(min(1.0, (t - t0) / FADE, (t1 - t) / FADE), 2)
                    n, prog = 0, []
                    for k, (ws, we) in enumerate(self.cards[ci]["words"]):
                        dur = min(1.4, max(0.22, we - ws))
                        p = round(min(1.0, (t - ws + 0.06) / dur), 2)
                        if p >= 1 and not prog:
                            n = k + 1
                        elif p > 0:
                            prog.append((k, p))
                    return (ci, ca, n, tuple(prog))
        return None

    def _settled(self, ci, n):
        card = self._card(ci)
        have = self.settled.get(ci)
        if have and have[0] <= n:
            k, canvas = have
        else:
            k, canvas = 0, Image.alpha_composite(self.static, card["base"])
        for j in range(k, n):
            sp, x, y = card["words"][j]
            canvas.alpha_composite(sp, dest=(x, y))
        self.settled[ci] = (n, canvas)
        return canvas

    def render(self, st):
        if st is None:
            return self.static
        ci, ca, n, prog = st
        card = self._card(ci)
        if ca >= 1:
            frame = self._settled(ci, n).copy()
            for k, p in prog:
                sp, x, y = card["words"][k]
                frame.alpha_composite(_alpha(sp, _wipe(sp.width, p)), dest=(x, y))
            return frame
        layer = card["base"].copy()
        for j in range(n):
            sp, x, y = card["words"][j]
            layer.alpha_composite(sp, dest=(x, y))
        for k, p in prog:
            sp, x, y = card["words"][k]
            layer.alpha_composite(_alpha(sp, _wipe(sp.width, p)), dest=(x, y))
        return Image.alpha_composite(self.static, _alpha(layer, ca))


# ============================================================== audio
def build_audio(paths, dest, workdir):
    """Concatenate ayah mp3s with gaps → one normalised wav. Timing is taken from the decoded wavs,
    so there is no drift even over hundreds of ayat. Returns (dest, [(start, end)], total)."""
    workdir.mkdir(parents=True, exist_ok=True)

    def conv(i):
        out = workdir / f"seg_{i:04d}.wav"
        pad = GAP if i < len(paths) - 1 else TAIL
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(paths[i]), "-af",
             f"aresample=44100,aformat=sample_fmts=s16:channel_layouts=stereo,apad=pad_dur={pad}",
             "-ac", "2", "-ar", "44100", str(out)])
        return out

    with ThreadPoolExecutor(8) as ex:
        wavs = list(ex.map(conv, range(len(paths))))
    durs = [media_duration(p) for p in paths]
    lens = [(w.stat().st_size - 44) / (44100 * 4) for w in wavs]  # exact decoded length incl. pad
    lst = workdir / "list.txt"
    lst.write_text("".join(f"file '{w.resolve()}'\n" for w in wavs))
    total = LEAD + sum(lens)
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-af",
         f"adelay={int(LEAD * 1000)}:all=1,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100,"
         f"afade=t=in:d=0.6,afade=t=out:st={total - 1.8:.2f}:d=1.8,atrim=0:{total:.3f}",
         "-ac", "2", str(dest)])
    times, t = [], LEAD
    for d, ln in zip(durs, lens):
        times.append((t, t + min(d, ln)))
        t += ln
    return dest, times, total


# ============================================================== compose
def compose(*, background, timeline, audio, total, dest, darken=0.35):
    n = int(round(total * FPS))
    fc = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,"
          f"eq=saturation=1.06,drawbox=x=0:y=0:w=iw:h=ih:color=black@{darken}:t=fill,vignette=PI/5[bg];"
          f"[1:v]format=rgba[ov];[bg][ov]overlay=0:0:format=auto:shortest=1,"
          f"fade=t=in:st=0:d=1.2,fade=t=out:st={total - 1.8:.2f}:d=1.8,format=yuv420p[v]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", str(background),
           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "pipe:0",
           "-i", str(audio), "-filter_complex", fc, "-map", "[v]", "-map", "2:a", "-t", f"{total:.3f}",
           "-r", str(FPS), "-c:v", "libx264", "-preset", "faster", "-crf", "20", "-maxrate", "8M",
           "-bufsize", "16M", "-g", str(FPS * 2), "-profile:v", "high", "-c:a", "aac", "-b:a", "192k",
           "-ar", "44100", "-movflags", "+faststart", str(dest)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    last, buf = object(), None
    try:
        for i in range(n):
            st = timeline.state(i / FPS)
            if st != last:
                buf, last = timeline.render(st).tobytes(), st
            proc.stdin.write(buf)
            if i and i % (FPS * 300) == 0:
                print(f"   … {i / FPS / 60:.0f} / {total / 60:.0f} min", flush=True)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode(errors="ignore")
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed:\n{err[-3000:]}")
    return Path(dest)
