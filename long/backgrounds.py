"""Landscape nature background for long videos: several free Pexels clips (license: free to use,
no attribution required), slowed down and joined with soft cross-fades into one calm ~5 minute loop.
No sound from the clips is ever used."""
import os
import random

from .common import CACHE, download, http_get, media_duration, run

QUERIES = ["waterfall", "mountain lake", "forest stream", "misty mountains", "ocean waves", "calm sea sunset",
           "clouds timelapse", "green valley", "river forest", "snow mountains", "rain forest", "desert dunes",
           "autumn forest", "flower field", "starry night sky", "sunrise mountains"]
W, H, FPS = 1920, 1080, 24


def _pexels(n, used):
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        return []
    out, qs = [], QUERIES[:]
    random.shuffle(qs)
    for q in qs:
        if len(out) >= n:
            break
        try:
            r = http_get("https://api.pexels.com/videos/search", headers={"Authorization": key},
                         params={"query": q, "orientation": "landscape", "size": "large", "per_page": 30})
        except Exception as e:  # noqa: BLE001
            print("  pexels failed:", e)
            continue
        vids = [v for v in r.json().get("videos", []) if f"pexels:{v['id']}" not in used and v.get("duration", 0) >= 10]
        random.shuffle(vids)
        for v in vids[:2]:
            files = [f for f in v.get("video_files", []) if f.get("width") and f.get("height")
                     and f["width"] > f["height"] and f["width"] >= 1920 and f.get("file_type") == "video/mp4"]
            if not files:
                continue
            f = min(files, key=lambda f: abs(f["width"] - 1920))
            try:
                path = download(f["link"], CACHE / "bg_long" / f"pexels_{v['id']}.mp4")
                out.append((path, f"pexels:{v['id']}"))
            except Exception as e:  # noqa: BLE001
                print("  clip download failed:", e)
            if len(out) >= n:
                break
    return out


def _generated(dest, seconds=120):
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         f"gradients=s={W}x{H}:c0=0x0e2a24:c1=0x2a4a3e:c2=0x113038:x0=0:y0=0:x1={W}:y1={H}:speed=0.004:d={seconds}",
         "-r", str(FPS), "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "20", str(dest)])
    return dest


def build(dest, used=(), n_clips=8, slow=1.6, xfade=2.0):
    """Returns (path, [ids])."""
    clips = _pexels(n_clips, set(used))
    if len(clips) < 2:
        print("  no Pexels clips – generated background")
        return _generated(dest), ["generated"]
    parts, durs = [], []
    for i, (p, _) in enumerate(clips):
        out = dest.parent / f"bgpart_{i}.mp4"
        d = min(media_duration(p), 30.0)
        run(["ffmpeg", "-y", "-loglevel", "error", "-t", f"{d:.2f}", "-i", str(p), "-an", "-vf",
             f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setpts={slow}*PTS,fps={FPS},"
             f"format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(out)])
        parts.append(out)
        durs.append(media_duration(out))
    inputs, chain, off, last = [], [], 0.0, "0:v"
    for p in parts:
        inputs += ["-i", str(p)]
    for i in range(1, len(parts)):
        off += durs[i - 1] - xfade
        chain.append(f"[{last}][{i}:v]xfade=transition=fade:duration={xfade}:offset={off:.2f}[x{i}]")
        last = f"x{i}"
    run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(chain), "-map", f"[{last}]",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(dest)])
    return dest, [c[1] for c in clips]
