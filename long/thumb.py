"""YouTube thumbnail 1280×720: a frame of the video's own background + a big, readable title."""
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from .common import run
from .render import BEIGE, EN_SANS, EN_SERIF, GOLD, UI_BOLD, UI_FONT, font

TW, TH = 1280, 720


def _fit(path, text, max_w, start, rtl, weight=None):
    size = start
    while size > 40:
        f = font(path, size, weight)
        w = f.getlength(text, direction="rtl") if rtl else f.getlength(text)
        if w <= max_w:
            return f
        size -= 4
    return font(path, size, weight)


def make(background, dest, title, subtitle, reciter_line, brand, english):
    frame = dest.with_name("thumb_bg.jpg")
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "4", "-i", str(background), "-frames:v", "1",
         "-vf", f"scale={TW}:{TH}:force_original_aspect_ratio=increase,crop={TW}:{TH}", str(frame)])
    img = ImageEnhance.Brightness(Image.open(frame).convert("RGB")).enhance(0.55).convert("RGBA")
    shade = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    ImageDraw.Draw(shade).rounded_rectangle((70, 150, TW - 70, TH - 130), radius=40, fill=(8, 14, 12, 150))
    img = Image.alpha_composite(img, shade.filter(ImageFilter.GaussianBlur(18)))
    cx = TW // 2
    rtl = not english
    glow = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    if english:
        f_t = _fit(EN_SERIF, title, TW - 220, 132, False, 600)
        f_s, f_r, f_b = font(EN_SANS, 40, 500), font(EN_SANS, 32, 420), font(EN_SANS, 28, 500)
    else:
        f_t = _fit(UI_BOLD, title, TW - 220, 150, True)
        f_s, f_r, f_b = font(UI_BOLD, 56), font(UI_FONT, 40), font(UI_BOLD, 34)
    kw = {"direction": "rtl"} if rtl else {}
    ImageDraw.Draw(glow).text((cx, 300), title, font=f_t, fill=(0, 0, 0, 230), anchor="mm", **kw)
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(img)
    d.text((cx, 300), title, font=f_t, fill=BEIGE if english else (255, 255, 255, 255), anchor="mm", **kw)
    d.line((cx - 170, 395, cx + 170, 395), fill=GOLD, width=3)
    d.text((cx, 450), subtitle, font=f_s, fill=GOLD, anchor="mm", **kw)
    d.text((cx, 530), reciter_line, font=f_r, fill=(255, 255, 255, 230), anchor="mm", **kw)
    d.text((cx, TH - 70), brand, font=f_b, fill=(255, 255, 255, 200), anchor="mm", **kw)
    img.convert("RGB").save(dest, "JPEG", quality=90, optimize=True)
    return dest
