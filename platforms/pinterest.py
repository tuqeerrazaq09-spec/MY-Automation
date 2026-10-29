"""Pinterest pin creation via API v5.

A pin needs an image and a board. Trial API access only works against
Pinterest's sandbox; set PINTEREST_API_BASE=https://api-sandbox.pinterest.com
to test with it. Posting publicly needs Standard access (approved by Pinterest).
"""
import base64

from .common import Post, Skip, env, request

NAME = "pinterest"
_cache = {}


def _base():
    return env("PINTEREST_API_BASE") or "https://api.pinterest.com"


def configured():
    has_token = env("PINTEREST_ACCESS_TOKEN") or (
        env("PINTEREST_REFRESH_TOKEN") and env("PINTEREST_APP_ID") and env("PINTEREST_APP_SECRET"))
    return bool(has_token)


def _token():
    """Prefer refreshing with a long-lived refresh token; fall back to a static access token."""
    if "t" in _cache:
        return _cache["t"]
    if env("PINTEREST_REFRESH_TOKEN") and env("PINTEREST_APP_ID") and env("PINTEREST_APP_SECRET"):
        basic = base64.b64encode(f"{env('PINTEREST_APP_ID')}:{env('PINTEREST_APP_SECRET')}".encode()).decode()
        r = request("POST", f"{_base()}/v5/oauth/token", headers={"Authorization": "Basic " + basic},
                    data={"grant_type": "refresh_token", "refresh_token": env("PINTEREST_REFRESH_TOKEN")})
        _cache["t"] = r.json()["access_token"]
    else:
        _cache["t"] = env("PINTEREST_ACCESS_TOKEN")
    return _cache["t"]


def _headers():
    return {"Authorization": "Bearer " + _token()}


def check():
    r = request("GET", f"{_base()}/v5/user_account", headers=_headers())
    boards = request("GET", f"{_base()}/v5/boards", headers=_headers(), params={"page_size": 25}).json().get("items", [])
    names = ", ".join(f"{b['name']} ({b['id']})" for b in boards[:5]) or "no boards found"
    return f"Account: {r.json().get('username')}; boards: {names}"


def publish(post: Post):
    if not post.image_url:
        raise Skip("Pinterest needs an image")
    board = post.board_id or env("PINTEREST_BOARD_ID")
    if not board:
        raise Skip("no Pinterest board id (set PINTEREST_BOARD_ID or the pinterest_board_id column)")
    first_line = post.caption.strip().splitlines()[0] if post.caption.strip() else "Pin"
    body = {
        "board_id": board,
        "title": (post.title or first_line)[:100],
        "description": post.caption[:800],
        "media_source": {"source_type": "image_url", "url": post.image_url},
    }
    if post.link:
        body["link"] = post.link
    r = request("POST", f"{_base()}/v5/pins", headers=_headers(), json=body)
    return r.json().get("id")
