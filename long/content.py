"""What each long video contains, and what goes out in each time slot.

Slot 1 (morning): a full surah from a curated rotation – Friday is always Surah Al-Kahf.
Slot 2 (evening): rotates  juz (series) → Quran before sleep → juz → duas from the Quran.
"""
import datetime as dt

from .common import DATA, http_get, load_json

# full surahs for the daily rotation (Al-Kahf is kept for Fridays)
SURAHS = [36, 67, 55, 56, 32, 19, 12, 48, 59, 50, 31, 20, 25, 17, 21, 14, 13, 57, 23, 24, 44, 49, 76, 73, 78,
          10, 11, 15, 16, 22, 26, 27, 28, 29, 30, 33, 34, 35, 37, 38, 39, 40, 41, 42, 43, 45, 46, 47, 51, 52,
          53, 54, 58, 61, 62, 64, 65, 66, 68, 69, 70, 71, 72, 74, 75]
JUZ_ORDER = [30, 29, 28, 27] + list(range(1, 27))
EVENING_CYCLE = ["juz", "sleep", "juz", "duas"]

# Quran before sleep – each item is from an authentic hadith about the night:
#   Ayat al-Kursi (Bukhari), last two ayat of Al-Baqarah (Bukhari & Muslim), As-Sajdah and Al-Mulk
#   (Tirmidhi: the Prophet ﷺ did not sleep until he recited them), Al-Ikhlas + Al-Falaq + An-Nas (Bukhari)
SLEEP = [(2, 255, 255), (2, 285, 286), (32, None, None), (67, None, None), (112, None, None),
         (113, None, None), (114, None, None)]

# duas from the Quran – the same verified list as the daily posts, in mushaf order
DUAS = [(2, 127, 127), (2, 128, 128), (2, 201, 201), (2, 250, 250), (2, 286, 286), (3, 8, 8), (3, 16, 16),
        (3, 38, 38), (3, 53, 53), (3, 147, 147), (3, 193, 193), (7, 23, 23), (7, 47, 47), (7, 151, 151),
        (10, 85, 85), (11, 47, 47), (14, 40, 40), (14, 41, 41), (17, 24, 24), (17, 80, 80), (18, 10, 10),
        (20, 25, 28), (20, 114, 114), (21, 83, 83), (21, 87, 87), (21, 89, 89), (23, 29, 29), (23, 97, 97),
        (23, 109, 109), (23, 118, 118), (25, 65, 65), (25, 74, 74), (26, 83, 83), (27, 19, 19), (28, 16, 16),
        (28, 21, 21), (28, 24, 24), (29, 30, 30), (44, 12, 12), (59, 10, 10), (71, 28, 28)]

JUZ_START = ["1:1", "2:142", "2:253", "3:93", "4:24", "4:148", "5:82", "6:111", "7:88", "8:41", "9:93", "11:6",
             "12:53", "15:1", "17:1", "18:75", "21:1", "23:1", "25:21", "27:56", "29:46", "33:31", "36:28",
             "39:32", "41:47", "46:1", "51:31", "58:1", "67:1", "78:1"]


def surahs():
    return load_json(DATA / "surahs.json")


def ayah_count(s):
    return surahs()[s - 1]["ayahs"]


def juz_ranges(j):
    """[(surah, from, to)] for juz j – from Quran.com, with a built-in table as fallback."""
    try:
        r = http_get(f"https://api.quran.com/api/v4/juzs/{j}").json()
        m = (r.get("juz") or {}).get("verse_mapping") or {}
        out = []
        for s, rng in m.items():
            a, b = (int(x) for x in rng.split("-"))
            out.append((int(s), a, b))
        if out:
            return sorted(out)
    except Exception as e:  # noqa: BLE001
        print("  juz api failed:", e)
    start = [tuple(int(x) for x in k.split(":")) for k in JUZ_START] + [(115, 1)]
    (s0, a0), (s1, a1) = start[j - 1], start[j]
    out = []
    for s in range(s0, min(s1, 114) + 1):
        a = a0 if s == s0 else 1
        b = ayah_count(s) if (s < s1) else a1 - 1
        if b >= a:
            out.append((s, a, b))
    return out


def sections_for(kind, key):
    """kind: surah / juz / duas / sleep → list of {"surah","from","to","basmala"}"""
    if kind == "surah":
        s = int(key)
        return [{"surah": s, "from": 1, "to": ayah_count(s), "basmala": s not in (1, 9)}]
    if kind == "juz":
        return [{"surah": s, "from": a, "to": b, "basmala": a == 1 and s not in (1, 9)} for s, a, b in juz_ranges(int(key))]
    items = DUAS if kind == "duas" else SLEEP
    out = []
    for s, a, b in items:
        full = a is None
        out.append({"surah": s, "from": a or 1, "to": b or ayah_count(s), "basmala": full and s not in (1, 9)})
    return out


def _last_used(history, channel, kind):
    out = {}
    for i, p in enumerate(history["videos"]):
        if p["channel"] == channel and p["kind"] == kind:
            out[str(p["key"])] = i
    return out


def plan(channel, slot, history, date=None):
    """→ (kind, key)"""
    date = date or dt.datetime.now(dt.timezone.utc).date()
    if slot == 1:
        if date.weekday() == 4:  # Friday
            return "surah", 18
        used = _last_used(history, channel, "surah")
        return "surah", min(SURAHS, key=lambda s: (used.get(str(s), -1), SURAHS.index(s)))
    kind = EVENING_CYCLE[date.toordinal() % len(EVENING_CYCLE)]
    if kind == "juz":
        done = [int(p["key"]) for p in history["videos"] if p["channel"] == channel and p["kind"] == "juz"]
        nxt = next((j for j in JUZ_ORDER if j not in done), None)
        if nxt is None:  # whole Quran done → start again in the same order
            last = done[-1]
            nxt = JUZ_ORDER[(JUZ_ORDER.index(last) + 1) % len(JUZ_ORDER)]
        return "juz", nxt
    return kind, kind
