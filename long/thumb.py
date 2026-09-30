"""YouTube thumbnail 1280×720 in each channel's identity.

Sakina (Arabic):   deep green + gold + beige, text on the right, Arabic calligraphic title.
Serenity (English): the same palette, text on the left, serif title + the Arabic name as an accent.
Both: a frame of the video's own background, the channel's round logo, a content tag, the reciter,
the length, and a thin gold frame – readable even at phone size.
"""
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

import os
import random

from .common import CACHE, ROOT, download, http_get, run
from .render import EN_SANS, EN_SERIF, EN_SERIF_UP, UI_BOLD, UI_FONT, font

TW, TH = 1280, 720
GREEN = (18, 32, 25)
GOLD = (201, 164, 92, 255)
BEIGE = (243, 235, 221, 255)
INK = (46, 62, 44, 255)  # logo green, used on gold pills


def logo(channel, size):
    im = Image.open(ROOT / "brand" / f"logo-{channel}.jpg").convert("RGBA").resize((size, size), Image.LANCZOS)
    m = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(m).ellipse((6, 6, size * 4 - 6, size * 4 - 6), fill=255)
    im.putalpha(m.resize((size, size), Image.LANCZOS))
    return im


def _fit(path, text, max_w, start, rtl=False, weight=None, minimum=48):
    size = start
    while size > minimum:
        f = font(path, size, weight)
        if (f.getlength(text, direction="rtl") if rtl else f.getlength(text)) <= max_w:
            return f
        size -= 4
    return font(path, minimum, weight)


def _pill(d, xy, text, f, anchor_right, fill=GOLD, ink=INK, pad=(26, 12), rtl=False, spacing=0, outline=None):
    w = f.getlength(text, direction="rtl") if rtl else (f.getlength(text) + spacing * max(0, len(text) - 1))
    h = f.size + pad[1] * 2
    x1 = xy[0] if not anchor_right else xy[0] - w - pad[0] * 2
    box = (x1, xy[1], x1 + w + pad[0] * 2, xy[1] + h)
    d.rounded_rectangle(box, radius=h // 2, fill=fill, outline=outline, width=2 if outline else 0)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    if spacing:
        x = cx - w / 2
        for ch in text:
            d.text((x, cy), ch, font=f, fill=ink, anchor="lm")
            x += f.getlength(ch) + spacing
    else:
        d.text((cx, cy + (2 if rtl else 0)), text, font=f, fill=ink, anchor="mm", **({"direction": "rtl"} if rtl else {}))
    return box


# a nature photo that fits the content (Pexels – free to use)
PHOTO_QUERIES = {
    ("surah", "18"): ["mountain cave light", "cave sunlight"], ("surah", "67"): ["starry night sky", "milky way"],
    ("surah", "55"): ["flower garden", "green garden"], ("surah", "56"): ["desert night stars"],
    ("surah", "19"): ["palm trees sunset"], ("surah", "12"): ["desert sunset"], ("surah", "36"): ["sunrise mountains"],
    ("sleep", None): ["night sky stars", "moon night clouds"], ("duas", None): ["sun rays clouds", "sunrise sky"],
    ("juz", None): ["mountain lake", "ocean horizon", "misty mountains"],
    ("surah", None): ["waterfall forest", "misty mountains", "forest sunlight", "calm lake", "green valley"],
}


def _photo(kind, key):
    k = os.getenv("PEXELS_API_KEY")
    if not k:
        return None
    qs = PHOTO_QUERIES.get((kind, str(key))) or PHOTO_QUERIES.get((kind, None)) or PHOTO_QUERIES[("surah", None)]
    for q in random.sample(qs, len(qs)):
        try:
            r = http_get("https://api.pexels.com/v1/search", headers={"Authorization": k},
                         params={"query": q, "orientation": "landscape", "size": "large", "per_page": 30})
            ph = [p for p in r.json().get("photos", []) if p.get("width", 0) >= 1920]
            if ph:
                p = random.choice(ph[:15])
                return download(f"{p['src']['original']}?auto=compress&cs=tinysrgb&w=1920",
                                CACHE / "thumb" / f"pexels_{p['id']}.jpg")
        except Exception as e:  # noqa: BLE001
            print("  thumbnail photo failed:", e)
    return None


def reciter_photo(key):
    """brand/reciters/<key>.png (cut-out) or .jpg – only photos you have the right to use."""
    for ext in ("png", "jpg"):
        p = ROOT / "brand" / "reciters" / f"{key}.{ext}"
        if p.exists():
            return p
    return None


def make(background, dest, t, channel, kind=None, key=None, reciter=None):
    """t: {"title", "tag", "line", "minutes", + for English: "ar", "sub"}"""
    en = channel == "en"
    frame = dest.with_name("thumb_bg.jpg")
    photo = _photo(kind, key)
    src = ["-i", str(photo)] if photo else ["-ss", "6", "-i", str(background), "-frames:v", "1"]
    run(["ffmpeg", "-y", "-loglevel", "error", *src,
         "-vf", f"scale={TW}:{TH}:force_original_aspect_ratio=increase,crop={TW}:{TH}", str(frame)])
    bg = Image.open(frame).convert("RGB").filter(ImageFilter.GaussianBlur(0.8))
    img = ImageEnhance.Contrast(ImageEnhance.Brightness(bg).enhance(0.8)).enhance(1.1).convert("RGBA")

    # brand gradient on the text side
    grad = Image.new("L", (TW, 1))
    for x in range(TW):
        p = (x / TW) if not en else (1 - x / TW)  # 0 at the far side, 1 at the text side
        grad.putpixel((x, 0), int(245 * min(1.0, max(0.0, (p - 0.18) / 0.5)) ** 1.2))
    shade = Image.new("RGBA", (TW, TH), GREEN + (255,))
    shade.putalpha(grad.resize((TW, TH)))
    img = Image.alpha_composite(img, shade)
    vign = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    ImageDraw.Draw(vign).rectangle((0, TH - 170, TW, TH), fill=(0, 0, 0, 90))
    img = Image.alpha_composite(img, vign.filter(ImageFilter.GaussianBlur(60)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((16, 16, TW - 16, TH - 16), radius=26, outline=GOLD[:3] + (200,), width=3)

    # image side: the reciter's photo (if you added one) + the logo
    rp = reciter_photo(reciter) if reciter else None
    side_x = 60 if not en else TW - 60
    if rp:
        size = 380
        ph = Image.open(rp).convert("RGBA")
        s = max(size / ph.width, size / ph.height)
        ph = ph.resize((int(ph.width * s) + 1, int(ph.height * s) + 1), Image.LANCZOS)
        l, tp = (ph.width - size) // 2, 0
        ph = ph.crop((l, tp, l + size, tp + size))
        m = Image.new("L", (size, size), 0)
        ImageDraw.Draw(m).ellipse((0, 0, size, size), fill=255)
        ph.putalpha(m)
        px = side_x if not en else side_x - size
        py = (TH - size) // 2 + 20
        glow = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse((px - 14, py - 14, px + size + 14, py + size + 14), fill=(0, 0, 0, 170))
        img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(22)))
        img.alpha_composite(ph, (px, py))
        ImageDraw.Draw(img).ellipse((px - 5, py - 5, px + size + 5, py + size + 5), outline=GOLD, width=6)
        lg = logo(channel, 110)
        lx = px + size - 110 + 10 if not en else px - 10
        img.alpha_composite(lg, (lx, py + size - 110 + 10))
    else:
        lg = logo(channel, 168)
        lx = 58 if not en else TW - 58 - 168
        glow = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse((lx - 8, 44, lx + 176, 228), fill=(0, 0, 0, 140))
        img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(14)))
        img.alpha_composite(lg, (lx, 52))
    d = ImageDraw.Draw(img)
    tw = 640 if rp else 760

    if not en:
        right = TW - 70
        _pill(d, (right, 92), t["tag"], font(UI_BOLD, 40), anchor_right=True, rtl=True)
        f_t = _fit(UI_BOLD, t["title"], tw, 168, rtl=True, minimum=84)
        tl = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
        ImageDraw.Draw(tl).text((right + 4, 330), t["title"], font=f_t, fill=(0, 0, 0, 230), anchor="rm",
                                direction="rtl")
        img = Image.alpha_composite(img, tl.filter(ImageFilter.GaussianBlur(9)))
        d = ImageDraw.Draw(img)
        d.text((right, 322), t["title"], font=f_t, fill=BEIGE, anchor="rm", direction="rtl")
        d.line((right - 300, 446, right, 446), fill=GOLD, width=4)
        d.text((right, 500), t["line"], font=_fit(UI_BOLD, t["line"], tw, 50, rtl=True, minimum=34), fill=GOLD,
               anchor="rm", direction="rtl")
        _pill(d, (right, 574), t["minutes"], font(UI_BOLD, 34), anchor_right=True, fill=GREEN + (255,),
              ink=GOLD, rtl=True, outline=GOLD)
    else:
        left = 70
        f_tag = font(EN_SANS, 24, 600)
        _pill(d, (left, 86), t["tag"], f_tag, anchor_right=False, spacing=3)
        d.text((left, 190), t["ar"], font=font(UI_BOLD, 58), fill=GOLD, anchor="lm", direction="rtl")
        f_t = _fit(EN_SERIF_UP, t["title"], tw, 132, weight=600, minimum=70)
        tl = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
        ImageDraw.Draw(tl).text((left + 3, 318), t["title"], font=f_t, fill=(0, 0, 0, 230), anchor="lm")
        img = Image.alpha_composite(img, tl.filter(ImageFilter.GaussianBlur(9)))
        d = ImageDraw.Draw(img)
        d.text((left, 312), t["title"], font=f_t, fill=BEIGE, anchor="lm")
        if t.get("sub"):
            d.text((left, 412), t["sub"], font=_fit(EN_SERIF, t["sub"], tw, 54, weight=500, minimum=34),
                   fill=(255, 255, 255, 225), anchor="lm")
        d.line((left, 470, left + 280, 470), fill=GOLD, width=4)
        f_l = font(EN_SANS, 26, 500)
        x = left
        for ch in t["line"].upper():
            d.text((x, 518), ch, font=f_l, fill=(255, 255, 255, 215), anchor="lm")
            x += f_l.getlength(ch) + 2.5
        _pill(d, (left, 570), t["minutes"], font(EN_SANS, 26, 600), anchor_right=False,
              fill=GREEN + (255,), ink=GOLD, spacing=2, outline=GOLD)
    img.convert("RGB").save(dest, "JPEG", quality=92, optimize=True)
    return dest
