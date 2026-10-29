"""Facebook Page posting via the Graph API (free)."""
from .common import Post, env, request

NAME = "facebook"


def _graph():
    return "https://graph.facebook.com/" + (env("META_GRAPH_VERSION") or "v21.0")


def _headers():
    return {"Authorization": "Bearer " + env("FB_PAGE_ACCESS_TOKEN")}


def configured():
    return bool(env("FB_PAGE_ID") and env("FB_PAGE_ACCESS_TOKEN"))


def check():
    r = request("GET", f"{_graph()}/{env('FB_PAGE_ID')}", params={"fields": "name"}, headers=_headers())
    return f"Page: {r.json().get('name')}"


def publish(post: Post):
    page = env("FB_PAGE_ID")
    if post.image_url:
        text = post.caption + (f"\n\n{post.link}" if post.link else "")
        r = request("POST", f"{_graph()}/{page}/photos", headers=_headers(),
                    data={"url": post.image_url, "caption": text})
    else:
        data = {"message": post.caption}
        if post.link:
            data["link"] = post.link
        r = request("POST", f"{_graph()}/{page}/feed", headers=_headers(), data=data)
    j = r.json()
    return j.get("post_id") or j.get("id")
