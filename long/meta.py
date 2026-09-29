"""Titles, descriptions (with chapters), tags and thumbnail text – Arabic (Daily Sakina) and English
(Daily Serenity). Everything is built from the actual content of the video, nothing is generic."""
from .common import ar_num

RECITERS_EN = {
    "husary": "Sheikh Mahmoud Khalil Al-Husary", "minshawi": "Sheikh Mohamed Siddiq Al-Minshawi",
    "abdulbasit": "Sheikh Abdul Basit Abdus Samad", "tablawi": "Sheikh Mohamed Al-Tablawi",
    "alafasy": "Sheikh Mishary Rashid Alafasy", "sudais": "Sheikh Abdul Rahman Al-Sudais",
    "shuraim": "Sheikh Saud Al-Shuraim", "maher": "Sheikh Maher Al-Muaiqly",
}
JUZ_AR = ["الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس", "السابع", "الثامن", "التاسع", "العاشر",
          "الحادي عشر", "الثاني عشر", "الثالث عشر", "الرابع عشر", "الخامس عشر", "السادس عشر", "السابع عشر",
          "الثامن عشر", "التاسع عشر", "العشرون", "الحادي والعشرون", "الثاني والعشرون", "الثالث والعشرون",
          "الرابع والعشرون", "الخامس والعشرون", "السادس والعشرون", "السابع والعشرون", "الثامن والعشرون",
          "التاسع والعشرون", "الثلاثون"]
JUZ_NICK_AR = {30: "جزء عمّ", 29: "جزء تبارك", 28: "جزء قد سمع"}
JUZ_NICK_EN = {30: "Juz 'Amma", 29: "Juz Tabarak", 28: "Juz Qad Sami'a", 1: "Alif Lam Mim"}


def ayat_ar(n):
    """Arabic counted noun: ٣ آيات، ١١ آية"""
    if n == 1:
        return "آية واحدة"
    if n == 2:
        return "آيتان"
    return f"{ar_num(n)} {'آيات' if 3 <= n <= 10 else 'آية'}"


def ts(sec):
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ------------------------------------------------------------------ names
def section_title(ctx, kind, key, en):
    if kind == "surah":
        return f"Surah {ctx.en_name(int(key))}" if en else f"سورة {ctx.ar_name(int(key))}"
    if kind == "juz":
        return f"Juz {key}" if en else f"الجزء {JUZ_AR[int(key) - 1]}"
    if kind == "duas":
        return "Duas from the Quran" if en else "أدعية من القرآن الكريم"
    return "Quran before sleep" if en else "قرآن قبل النوم"


def card_label(ctx, surah, ayah, en):
    if en:
        return f"Surah {ctx.en_name(surah)}  ·  {surah}:{ayah}" if ayah else f"Surah {ctx.en_name(surah)}"
    return f"سورة {ctx.ar_name(surah)}  •  الآية {ar_num(ayah)}" if ayah else f"سورة {ctx.ar_name(surah)}"


# ------------------------------------------------------------------ chapters
def chapters(ctx, kind, sections, marks, en):
    """marks: [(time, surah, ayah)] for every ayah in order (basmala excluded).
    YouTube needs: first at 0:00, at least 3, each ≥ 10 s apart."""
    out = []
    if kind in ("duas", "sleep"):
        for n, sec in enumerate(sections, 1):
            t = next(m[0] for m in marks if m[1] == sec["surah"] and m[2] == sec["from"])
            if en:
                if kind == "duas":
                    name = f"Dua {n} – Surah {ctx.en_name(sec['surah'])} {sec['surah']}:{sec['from']}" + \
                           (f"-{sec['to']}" if sec["to"] != sec["from"] else "")
                else:
                    name = _sleep_name(ctx, sec, en=True)
            else:
                if kind == "duas":
                    rng = ar_num(sec["from"]) + ("" if sec["to"] == sec["from"] else f"–{ar_num(sec['to'])}")
                    name = f"الدعاء {ar_num(n)}: سورة {ctx.ar_name(sec['surah'])} ({rng})"
                else:
                    name = _sleep_name(ctx, sec, en=False)
            out.append((t, name))
    else:
        for sec in sections:
            s, a, b = sec["surah"], sec["from"], sec["to"]
            n = b - a + 1
            whole = kind == "juz" and n <= 25
            step = n if whole else (max(5, -(-n // 12)) if kind == "surah" else 20)
            for start in range(a, b + 1, step):
                end = min(b, start + step - 1)
                t = next(m[0] for m in marks if m[1] == s and m[2] == start)
                if en:
                    rng = f"Ayat {start}–{end}" if start != end else f"Ayah {start}"
                    name = (f"Surah {ctx.en_name(s)}" if whole else
                            f"Surah {ctx.en_name(s)} – {rng}" if kind == "juz" else rng)
                else:
                    rng = f"الآيات {ar_num(start)}–{ar_num(end)}" if start != end else f"الآية {ar_num(start)}"
                    name = (f"سورة {ctx.ar_name(s)}" if whole else
                            f"سورة {ctx.ar_name(s)} – {rng}" if kind == "juz" else rng)
                out.append((t, name))
    out[0] = (0, out[0][1])
    clean = []
    for t, name in out:
        if clean and t - clean[-1][0] < 10:
            continue
        clean.append((t, name))
    return clean if len(clean) >= 3 else [(0, clean[0][1])]


def _sleep_name(ctx, sec, en):
    s, a, b = sec["surah"], sec["from"], sec["to"]
    if s == 2 and a == 255:
        return "Ayat al-Kursi (2:255)" if en else "آية الكرسي"
    if s == 2:
        return "Last two ayat of Al-Baqarah (2:285-286)" if en else "خواتيم سورة البقرة"
    return f"Surah {ctx.en_name(s)}" if en else f"سورة {ctx.ar_name(s)}"


# ------------------------------------------------------------------ title / description / tags
def build(ctx, kind, key, reciter, total, chaps, en, n_ayat):
    r_ar, r_en = reciter["name"], RECITERS_EN.get(reciter["key"], reciter["key"])
    minutes = max(1, round(total / 60))
    chap_txt = "\n".join(f"{ts(t)} {name}" for t, name in chaps) if len(chaps) >= 3 else ""
    if en:
        return _en(ctx, kind, key, r_en, minutes, chap_txt, n_ayat)
    return _ar(ctx, kind, key, r_ar, minutes, chap_txt, n_ayat)


def _ar(ctx, kind, key, r, minutes, chap_txt, n):
    if kind == "surah":
        name = ctx.ar_name(int(key))
        if int(key) == 18:
            title = f"سورة الكهف كاملة يوم الجمعة | الشيخ {r} | نور ما بين الجمعتين"
            intro = ("قال رسول الله ﷺ: «مَن قرأ سورة الكهف في يوم الجمعة أضاء له من النور ما بين الجمعتين» "
                     "(رواه الحاكم والبيهقي، وصححه الألباني).\n\nسورة الكهف كاملة بتلاوة مرتلة هادئة، "
                     "والآيات تظهر كلمة بكلمة مع صوت الشيخ.")
        else:
            title = f"سورة {name} كاملة | الشيخ {r} | تلاوة هادئة مع الآيات"
            intro = f"سورة {name} كاملة ({ayat_ar(n)}) بصوت الشيخ {r}، والآيات تظهر كلمة بكلمة مع التلاوة."
        thumb = (f"سورة {name}", "كاملة" if int(key) != 18 else "يوم الجمعة")
        tags = [f"سورة {name}", f"سورة {name} كاملة", f"سورة {name} {r}", r, "قرآن كريم", "تلاوة هادئة",
                "القرآن الكريم كامل", "تلاوة خاشعة", "سكينة يومية"]
    elif kind == "juz":
        j = int(key)
        nick = JUZ_NICK_AR.get(j)
        title = f"الجزء {JUZ_AR[j - 1]}" + (f" ({nick})" if nick else "") + f" كاملًا | الشيخ {r} | تلاوة مرتلة"
        intro = (f"الجزء {JUZ_AR[j - 1]} من القرآن الكريم كاملًا بصوت الشيخ {r}، مع ظهور الآيات كلمة بكلمة. "
                 "جزء جديد كل فترة حتى نختم القرآن معًا بإذن الله.")
        thumb = (f"الجزء {JUZ_AR[j - 1]}", nick or "كاملًا")
        tags = [f"الجزء {JUZ_AR[j - 1]}", f"الجزء {j}", nick or "جزء كامل", r, "قرآن كريم", "ختمة القرآن",
                "تلاوة مرتلة", "سكينة يومية"]
    elif kind == "duas":
        title = f"أدعية من القرآن الكريم | من دعاء الأنبياء والمؤمنين | الشيخ {r}"
        intro = ("أجمل الأدعية التي وردت في القرآن الكريم على لسان الأنبياء والمؤمنين: «ربنا آتنا في الدنيا حسنة»، "
                 "«ربنا لا تزغ قلوبنا»، «رب اشرح لي صدري»، «لا إله إلا أنت سبحانك»… مرتبة حسب ترتيب المصحف.")
        thumb = ("أدعية من القرآن", "ادعُ بها من قلبك")
        tags = ["أدعية من القرآن", "أدعية قرآنية", "ربنا آتنا في الدنيا حسنة", "دعاء", "أدعية الأنبياء", r,
                "قرآن كريم", "سكينة يومية"]
    else:
        title = f"قرآن قبل النوم | آية الكرسي وخواتيم البقرة والسجدة والملك والمعوذات | الشيخ {r}"
        intro = ("ما كان النبي ﷺ يقرؤه قبل النوم: آية الكرسي (البخاري)، وخواتيم سورة البقرة (البخاري ومسلم)، "
                 "وسورة السجدة وسورة الملك (الترمذي)، والإخلاص والمعوذتان (البخاري). نم على ذكر الله.")
        thumb = ("قرآن قبل النوم", "آية الكرسي • الملك • المعوذات")
        tags = ["قرآن قبل النوم", "سورة الملك", "آية الكرسي", "خواتيم البقرة", "رقية", "قرآن للنوم", r,
                "سكينة يومية"]
    desc = "\n\n".join(x for x in [
        intro,
        f"⏱️ المدة: {ar_num(minutes)} دقيقة تقريبًا",
        ("📑 الفصول:\n" + chap_txt) if chap_txt else "",
        "🤍 اشترك في «سكينة يومية» لتصلك تلاوة جديدة كل يوم، وفعّل الجرس 🔔\n"
        "شارك الفيديو، فالدال على الخير كفاعله.",
        "المصادر: نص المصحف والتلاوة وتوقيت الكلمات من Quran.com • الخلفيات من Pexels (مجانية الاستخدام).",
        "#قرآن_كريم #سكينة_يومية #تلاوة_هادئة",
    ] if x)
    return {"title": title[:100], "description": desc[:4900], "tags": tags, "thumb": thumb, "lang": "ar"}


def _en(ctx, kind, key, r, minutes, chap_txt, n):
    if kind == "surah":
        s = int(key)
        name, meaning = ctx.en_name(s), ctx.en_meaning(s)
        if s == 18:
            title = f"Surah Al-Kahf – Friday Recitation | Full with English Translation | {r.split()[-1]}"
            intro = ("The Prophet ﷺ said: \"Whoever recites Surah Al-Kahf on Friday, a light will shine for him "
                     "between the two Fridays.\" (Al-Hakim, Al-Bayhaqi – graded authentic by Al-Albani)\n\n"
                     "The full surah in a calm Arabic recitation, with every word appearing as it is recited "
                     "and the English meaning under each verse.")
        else:
            title = f"Surah {name} ({meaning}) Full | Calm Quran Recitation with English Translation"
            intro = (f"Surah {name} – \"{meaning}\" – complete ({n} verses), recited by {r}. Every Arabic word appears "
                     "as it is recited, with the English translation under each verse.")
        thumb = (f"Surah {name}", "Full · English Translation")
        tags = [f"Surah {name}", f"Surah {name} full", f"Surah {name} English translation", "Quran recitation",
                "Quran with English translation", r, "beautiful Quran", "calm Quran", "Daily Serenity"]
    elif kind == "juz":
        j = int(key)
        nick = JUZ_NICK_EN.get(j)
        title = f"Juz {j}" + (f" ({nick})" if nick else "") + " Full | Beautiful Quran Recitation with English Translation"
        intro = (f"Juz {j} of the Holy Quran, complete, recited by {r} – with the Arabic words appearing as they "
                 "are recited and the English translation under each verse. A new juz every few days until we "
                 "complete the whole Quran together.")
        thumb = (f"Juz {j}", nick or "Full · English Translation")
        tags = [f"Juz {j}", f"Juz {j} full", nick or "Quran juz", "Quran recitation", "Quran with English translation",
                r, "Quran khatm", "Daily Serenity"]
    elif kind == "duas":
        title = f"Duas from the Quran | {n} Verses – Rabbana Duas with English Translation"
        intro = ("The most beautiful supplications in the Quran – the duas of the Prophets and the believers: "
                 "\"Our Lord, give us good in this world\", \"Our Lord, let not our hearts deviate\", \"My Lord, "
                 "expand for me my breast\"… in the order of the mushaf, with the English meaning of each one.")
        thumb = ("Duas from the Quran", "Rabbana · English Translation")
        tags = ["duas from the Quran", "Rabbana duas", "Quranic duas", "dua with English translation",
                "powerful dua", "Quran recitation", r, "Daily Serenity"]
    else:
        title = "Quran Before Sleep | Ayat al-Kursi, Al-Baqarah Ending, As-Sajdah, Al-Mulk & the 3 Quls"
        intro = ("What the Prophet ﷺ recited before sleeping: Ayat al-Kursi (Bukhari), the last two verses of "
                 "Al-Baqarah (Bukhari & Muslim), Surah As-Sajdah and Surah Al-Mulk (Tirmidhi), and Al-Ikhlas, "
                 "Al-Falaq and An-Nas (Bukhari) – with the English meaning. Sleep in the remembrance of Allah.")
        thumb = ("Quran Before Sleep", "Ayat al-Kursi · Al-Mulk · 3 Quls")
        tags = ["Quran before sleep", "Quran for sleep", "Surah Al-Mulk", "Ayat al-Kursi", "last 3 surahs",
                "sleep Quran", "Quran with English translation", "Daily Serenity"]
    desc = "\n\n".join(x for x in [
        intro,
        f"⏱️ Length: {minutes} minutes",
        ("📑 Chapters:\n" + chap_txt) if chap_txt else "",
        "🤍 Subscribe to Daily Serenity for a calm Quran recitation every day, and turn on the bell 🔔\n"
        "Share it – whoever guides to good gets the same reward.",
        "Recitation: " + r + " · Translation: Marmaduke Pickthall (public domain) · Quran text, audio and word "
        "timings: Quran.com · Backgrounds: Pexels (free to use).",
        "#Quran #QuranRecitation #DailySerenity",
    ] if x)
    return {"title": title[:100], "description": desc[:4900], "tags": tags, "thumb": thumb, "lang": "en"}
