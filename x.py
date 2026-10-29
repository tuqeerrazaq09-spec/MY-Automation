"""X (Twitter) posting via API v2 with OAuth 1.0a user keys.

The free tier allows a limited number of posts per month. Image upload on the
free tier depends on X's current rules, so if it is refused the post is sent
as text (with the link) instead of failing.
"""
import re

from requests_oauthlib import OAuth1

from .common import Post, PostError, env, fetch_image, request

NAME = "x"
URL_RE = re.compile(r"https?://\S+")
LIMIT = 280


def _auth():
    return OAuth1(env("X_API_KEY"), env("X_API_SECRET"), env("X_ACCESS_TOKEN"), env("X_ACCESS_TOKEN_SECRET"))


def configured():
    return all(env(k) for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"))


def check():
    r = request("GET", "https://api.x.com/2/users/me", auth=_auth())
    return f"Account: @{r.json()['data']['username']}"


def weighted_len(text):
    """X counts every URL as 23 characters."""
    return len(URL_RE.sub("x" * 23, text))


def build_text(post: Post):
    text = (post.x_text or post.caption).strip()
    link = post.link.strip()
    tail = f"\n{link}" if link and link not in text else ""
    room = LIMIT - weighted_len(tail)
    if weighted_len(text) > room:
        while text and weighted_len(text) > room - 1:
            text = text[:-1]
        text = text.rstrip() + "…"
    return text + tail


def _upload_image(url):
    data, ctype = fetch_image(url)
    for endpoint in ("https://api.x.com/2/media/upload", "https://upload.twitter.com/1.1/media/upload.json"):
        try:
            r = request("POST", endpoint, auth=_auth(),
                        files={"media": ("image", data, ctype)}, data={"media_category": "tweet_image"})
            j = r.json()
            mid = (j.get("data") or {}).get("id") or j.get("media_id_string")
            if mid:
                return str(mid)
        except PostError:
            continue
    return None


def publish(post: Post):
    payload = {"text": build_text(post)}
    if post.image_url:
        media_id = _upload_image(post.image_url)
        if media_id:
            payload["media"] = {"media_ids": [media_id]}
        else:
            print("    x: image upload refused, posting text only")
    r = request("POST", "https://api.x.com/2/tweets", auth=_auth(), json=payload)
    return r.json()["data"]["id"]
