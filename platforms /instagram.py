"""Instagram Business/Creator posting via the Graph API (free).

Instagram requires an image. Links in captions are not clickable, so the link
column is ignored here (use "link in bio").
"""
import time

from .common import Post, PostError, Skip, env, request

NAME = "instagram"


def _graph():
    return "https://graph.facebook.com/" + (env("META_GRAPH_VERSION") or "v21.0")


def _token():
    return env("IG_ACCESS_TOKEN") or env("FB_PAGE_ACCESS_TOKEN")


def _headers():
    return {"Authorization": "Bearer " + _token()}


def configured():
    return bool(env("IG_USER_ID") and _token())


def check():
    r = request("GET", f"{_graph()}/{env('IG_USER_ID')}", params={"fields": "username"}, headers=_headers())
    return f"Account: @{r.json().get('username')}"


def publish(post: Post):
    if not post.image_url:
        raise Skip("Instagram needs an image")
    ig = env("IG_USER_ID")
    r = request("POST", f"{_graph()}/{ig}/media", headers=_headers(),
                data={"image_url": post.image_url, "caption": post.caption})
    creation_id = r.json()["id"]
    for _ in range(15):  # wait up to ~30s for Instagram to process the image
        s = request("GET", f"{_graph()}/{creation_id}", params={"fields": "status_code"}, headers=_headers())
        code = s.json().get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise PostError(f"Instagram media processing failed: {code}")
        time.sleep(2)
    p = request("POST", f"{_graph()}/{ig}/media_publish", headers=_headers(), data={"creation_id": creation_id})
    return p.json().get("id")
