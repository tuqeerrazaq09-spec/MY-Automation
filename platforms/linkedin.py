"""LinkedIn posting via the Posts API.

Personal profile: needs the free "Share on LinkedIn" product (w_member_social).
Company page: needs LinkedIn's Community Management API approval (w_organization_social).
"""
from .common import Post, PostError, env, fetch_image, request

NAME = "linkedin"
API = "https://api.linkedin.com/rest"

# Characters that LinkedIn's "little text" format treats as markup and that truncate a post if unescaped.
_RESERVED = "\\|{}[]()<>*_~"


def _escape(text):
    return "".join("\\" + c if c in _RESERVED else c for c in text)


def _headers(extra=None):
    h = {
        "Authorization": "Bearer " + env("LINKEDIN_ACCESS_TOKEN"),
        "X-Restli-Protocol-Version": "2.0.0",
        "Linkedin-Version": env("LINKEDIN_API_VERSION") or "202510",
    }
    h.update(extra or {})
    return h


def configured():
    return bool(env("LINKEDIN_ACCESS_TOKEN") and env("LINKEDIN_AUTHOR_URN"))


def check():
    r = request("GET", "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": "Bearer " + env("LINKEDIN_ACCESS_TOKEN")})
    j = r.json()
    return f"Token valid for {j.get('name', 'member')} (posting as {env('LINKEDIN_AUTHOR_URN')})"


def _upload_image(url, author):
    data, ctype = fetch_image(url)
    r = request("POST", f"{API}/images?action=initializeUpload", headers=_headers({"Content-Type": "application/json"}),
                json={"initializeUploadRequest": {"owner": author}})
    val = r.json()["value"]
    request("PUT", val["uploadUrl"], headers={"Authorization": "Bearer " + env("LINKEDIN_ACCESS_TOKEN"),
                                              "Content-Type": ctype}, data=data)
    return val["image"]


def publish(post: Post):
    author = env("LINKEDIN_AUTHOR_URN")
    body = {
        "author": author,
        "commentary": _escape(post.caption),
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if post.image_url:
        body["content"] = {"media": {"id": _upload_image(post.image_url, author)}}
        if post.link:
            body["commentary"] += "\n\n" + _escape(post.link)
    elif post.link:
        body["content"] = {"article": {"source": post.link, "title": post.title or post.link}}
    r = request("POST", f"{API}/posts", headers=_headers({"Content-Type": "application/json"}), json=body)
    pid = r.headers.get("x-restli-id")
    if not pid:
        raise PostError("LinkedIn accepted the request but returned no post id")
    return pid
