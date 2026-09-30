"""Make (and publish) one long video.

  python -m long.main --auto --publish                  # decides channel + slot from the UTC hour
  python -m long.main --channel ar --slot 1             # render only (out_long/)
  python -m long.main --channel en --kind juz --key 30 --reciter husary
  python -m long.main --channel ar --kind surah --key 67 --preview 60   # first ~60 s only, for checking
"""
import argparse
import datetime as dt
import random
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor

from . import backgrounds, content, meta, thumb
from .common import DATA, ROOT, ar_num, load_json, run, save_json
from .render import (FADE, Layout, Timeline, build_audio, compose, split_ayah, static_layer)
from .source import fetch_verse, prefetch_chapter

OUT = ROOT / "out_long"
HISTORY = ROOT / "long_history.json"
RECITERS = ["husary", "minshawi", "abdulbasit", "tablawi"]  # classic murattal recordings
BASMALA_EN = "In the name of Allah, the Beneficent, the Merciful."
BRAND = {"ar": "سَكينة يومية", "en": "Daily Serenity"}


class Ctx:
    def __init__(self, english):
        self.s = load_json(DATA / "surahs.json")
        self.en = load_json(DATA / "en" / "chapters.json") if english else {}
        self.pick = load_json(DATA / "en" / "pickthall.json")["verses"] if english else {}

    def ar_name(self, s):
        return self.s[s - 1]["name"]

    def en_name(self, s):
        return self.en[str(s)]["name"]

    def en_meaning(self, s):
        return self.en[str(s)]["meaning"]


def auto_slot(now):
    h = now.hour
    if 2 <= h <= 8:
        return "ar", 1
    if 9 <= h <= 13:
        return "en", 1
    if 14 <= h <= 19:
        return "ar", 2
    return "en", 2


def slot_key(channel, slot, now):
    return f"{channel}-{slot}-{(now - dt.timedelta(hours=4)).date()}"


def pick_reciter(history, channel, forced=None):
    rs = {r["key"]: r for r in load_json(DATA / "reciters.json")["reciters"]}
    if forced:
        return rs[forced]
    last = {}
    for i, v in enumerate(history["videos"]):
        if v["channel"] == channel:
            last[v["reciter"]] = i
    return rs[min(RECITERS, key=lambda k: (last.get(k, -1), random.random()))]


def collect(sections, reciter, preview=None):
    """→ list of segments {"surah","ayah"(None = basmala),"audio","words","timings","duration"}"""
    for sec in sections:
        prefetch_chapter(reciter, sec["surah"], sec["from"], sec["to"])
    jobs = []
    for sec in sections:
        if sec["basmala"]:
            jobs.append((sec["surah"], None))
        jobs += [(sec["surah"], a) for a in range(sec["from"], sec["to"] + 1)]

    def get(job):
        s, a = job
        v = fetch_verse(reciter, 1, 1) if a is None else fetch_verse(reciter, s, a)
        return {"surah": s, "ayah": a, **v}

    segs, total = [], 0.0
    with ThreadPoolExecutor(8) as ex:
        for seg in ex.map(get, jobs):
            segs.append(seg)
            total += seg["duration"]
            if preview and total > preview and any(x["ayah"] for x in segs):
                break
    est = sum(1 for s in segs if s["timing_source"] == "estimated")
    print(f"📥 {len(segs)} segments, {total / 60:.1f} min of recitation"
          + (f" ({est} with estimated word timing)" if est else ""))
    return segs


def make_cards(ctx, layout, segs, times, total, english):
    cards, marks = [], []
    for i, (seg, (t0, t1)) in enumerate(zip(segs, times)):
        s, a = seg["surah"], seg["ayah"]
        tokens = list(seg["words"])
        timings = [(t0 + ws, t0 + we) for ws, we in seg["timings"]]
        if a:
            tokens.append(f"۝{ar_num(a)}")
            last = timings[-1][1] if timings else t0
            timings.append((last - 0.05, last + 0.35))
            marks.append((t0, s, a))
        en = (ctx.pick.get(f"{s}:{a}") if a else BASMALA_EN) if english else None
        label = meta.card_label(ctx, s, a, english)
        chunks = split_ayah(layout, tokens)
        en_parts = [en] * len(chunks)
        if en and len(chunks) > 1:
            ew, n = en.split(), len(tokens)
            cut, pos = [], 0
            for c in chunks[:-1]:
                pos += len(c)
                cut.append(round(len(ew) * pos / n))
            bounds = [0] + cut + [len(ew)]
            en_parts = [" ".join(ew[bounds[k]:bounds[k + 1]]) for k in range(len(chunks))]
        if i + 1 < len(segs):
            nt = segs[i + 1]["timings"]
            next_first = times[i + 1][0] + (nt[0][0] if nt else 0.0)
        else:
            next_first = total
        k0 = 0
        for c, chunk in enumerate(chunks):
            w = timings[k0:k0 + len(chunk)]
            start = w[0][0] - 0.15 - (0.2 if not cards else 0)
            if c + 1 < len(chunks):
                end = timings[k0 + len(chunk)][0] - 0.15
            else:
                end = next_first - 0.15 if i + 1 < len(segs) else total - 0.3
            end = max(end, w[-1][1] + FADE)
            cards.append({"spec": {"tokens": chunk, "label": label, "en": en_parts[c]},
                          "window": (max(0.0, start), end), "words": w})
            k0 += len(chunk)
    # windows must not overlap
    for j in range(len(cards) - 1):
        a0, a1 = cards[j]["window"]
        b0 = cards[j + 1]["window"][0]
        if a1 > b0:
            cards[j]["window"] = (a0, b0)
    return cards, marks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--channel", choices=["ar", "en"])
    ap.add_argument("--slot", type=int, choices=[1, 2])
    ap.add_argument("--kind", choices=["surah", "juz", "duas", "sleep"])
    ap.add_argument("--key")
    ap.add_argument("--reciter")
    ap.add_argument("--preview", type=float, help="render only the first N seconds (no publishing)")
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    history = load_json(HISTORY) if HISTORY.exists() else {"videos": []}
    channel, slot = (auto_slot(now) if args.auto else (args.channel or "ar", args.slot or 1))
    key_slot = slot_key(channel, slot, now)
    if args.auto and args.publish and any(v.get("slot_key") == key_slot and v.get("video_id")
                                          for v in history["videos"]):
        print(f"✅ {key_slot} already published – nothing to do")
        return
    english = channel == "en"
    if english:
        from .en_data import ensure
        ensure()
    ctx = Ctx(english)
    kind, key = (args.kind, args.key or args.kind) if args.kind else content.plan(channel, slot, history)
    reciter = pick_reciter(history, channel, args.reciter)
    sections = content.sections_for(kind, key)
    print(f"🎬 {channel} slot {slot} | {kind} {key} | {reciter['key']} | {len(sections)} section(s)")

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    segs = collect(sections, reciter, args.preview)
    audio, times, total = build_audio([s["audio"] for s in segs], OUT / "audio.wav", OUT / "wav")
    print(f"🔊 audio {total / 60:.1f} min")

    layout = Layout(english)
    cards, marks = make_cards(ctx, layout, segs, times, total, english)
    r_line = (f"Recited by {meta.RECITERS_EN.get(reciter['key'], reciter['key'])}" if english
              else f"بصوت الشيخ {reciter['name']}")
    section = meta.section_title(ctx, kind, key, english)
    static = static_layer(brand=BRAND[channel], section=section, reciter_line=r_line, english=english,
                          logo=thumb.logo(channel, 72))
    used = {i for v in history["videos"][-30:] for i in v.get("backgrounds", [])}
    bg, bg_ids = backgrounds.build(OUT / "bg.mp4", used)
    print(f"🌄 background: {len(bg_ids)} clip(s)")

    video = compose(background=bg, timeline=Timeline(layout, static, cards, total), audio=audio, total=total,
                    dest=OUT / "video.mp4")
    print(f"✅ video {video.stat().st_size / 1e6:.0f} MB, {len(cards)} cards")

    n_ayat = sum(1 for s in segs if s["ayah"])
    chaps = meta.chapters(ctx, kind, sections, marks, english) if not args.preview else [(0, section)]
    m = meta.build(ctx, kind, key, reciter, total, chaps, english, n_ayat)
    th = thumb.make(bg, OUT / "thumbnail.jpg", m["thumb"], channel, kind=kind, key=key, reciter=reciter["key"])
    (OUT / "title.txt").write_text(m["title"], encoding="utf-8")
    (OUT / "description.txt").write_text(m["description"], encoding="utf-8")
    (OUT / "frames").mkdir()
    for k, t in enumerate([total * f for f in (0.05, 0.2, 0.45, 0.7, 0.9)]):
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
             "-q:v", "3", str(OUT / "frames" / f"frame_{k}.jpg")])
    print("\n" + m["title"] + "\n\n" + m["description"])

    if args.preview or not args.publish:
        return
    from .youtube import upload
    res = upload(video, m, thumbnail=th)
    print("📺", res)
    history["videos"].append({"date": now.isoformat(timespec="seconds"), "slot_key": key_slot, "channel": channel,
                              "slot": slot, "kind": kind, "key": str(key), "reciter": reciter["key"],
                              "minutes": round(total / 60, 1), "title": m["title"], "backgrounds": bg_ids, **res})
    save_json(HISTORY, history)


if __name__ == "__main__":
    sys.exit(main())
