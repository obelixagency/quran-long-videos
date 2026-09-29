"""Upload a long video to YouTube (Data API v3, resumable upload in 64 MB chunks) + custom thumbnail.

Env: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN, YT_CHANNEL_ID (the upload is refused if the token
belongs to another channel). Custom thumbnails need a phone-verified channel; if YouTube refuses it,
the video itself is still published.
"""
import os
import time
from pathlib import Path

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
CHUNK = 64 * 1024 * 1024


def _token():
    r = requests.post(TOKEN_URL, timeout=60, data={
        "client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"})
    j = r.json()
    if "access_token" not in j:
        raise RuntimeError(f"YouTube token refresh failed: {j.get('error')} {j.get('error_description', '')}")
    return j["access_token"]


def channel(h):
    r = requests.get(f"{API}/channels", params={"part": "id,snippet", "mine": "true"}, headers=h, timeout=60)
    items = r.json().get("items", [])
    if not items:
        raise RuntimeError(f"No YouTube channel for this token: {r.status_code}")
    ch = items[0]
    wanted = os.getenv("YT_CHANNEL_ID")
    if wanted and ch["id"] != wanted:
        raise RuntimeError(f"Token belongs to channel {ch['snippet']['title']}, not the expected one")
    return ch


def upload(video, meta, thumbnail=None, privacy="public", category="22"):
    h = {"Authorization": f"Bearer {_token()}"}
    ch = channel(h)
    size = Path(video).stat().st_size
    body = {"snippet": {"title": meta["title"], "description": meta["description"], "tags": meta["tags"][:20],
                        "categoryId": category, "defaultLanguage": meta["lang"], "defaultAudioLanguage": "ar"},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False, "embeddable": True}}
    init = requests.post(UPLOAD, params={"uploadType": "resumable", "part": "snippet,status"}, json=body, timeout=60,
                         headers={**h, "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)})
    if init.status_code >= 400 or "Location" not in init.headers:
        raise RuntimeError(f"YouTube upload init failed {init.status_code}: {init.text[:400]}")
    url, pos, vid = init.headers["Location"], 0, None
    with open(video, "rb") as f:
        while pos < size:
            f.seek(pos)
            chunk = f.read(CHUNK)
            end = pos + len(chunk) - 1
            for attempt in range(6):
                try:
                    r = requests.put(url, data=chunk, timeout=600, headers={
                        **h, "Content-Length": str(len(chunk)), "Content-Range": f"bytes {pos}-{end}/{size}"})
                    break
                except requests.RequestException as e:
                    print(f"  upload chunk retry {attempt + 1}: {e}")
                    time.sleep(10 * (attempt + 1))
            else:
                raise RuntimeError("YouTube upload failed after retries")
            if r.status_code in (200, 201):
                vid = r.json()
                pos = size
            elif r.status_code == 308:
                rng = r.headers.get("Range")
                pos = int(rng.split("-")[1]) + 1 if rng else 0
                print(f"   uploaded {pos / size:.0%}", flush=True)
            else:
                raise RuntimeError(f"YouTube upload failed {r.status_code}: {r.text[:400]}")
    thumb = None
    if thumbnail and Path(thumbnail).exists():
        with open(thumbnail, "rb") as img:
            t = requests.post("https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
                              params={"videoId": vid["id"]}, data=img, timeout=120,
                              headers={**h, "Content-Type": "image/jpeg"})
        thumb = "ok" if t.status_code < 300 else f"skipped ({t.status_code}) – verify the channel by phone"
    return {"video_id": vid["id"], "url": f"https://youtu.be/{vid['id']}", "thumbnail": thumb,
            "privacy": vid.get("status", {}).get("privacyStatus"), "channel": ch["snippet"]["title"]}
