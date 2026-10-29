"""Shared helpers for all platform modules."""
import os
import time
from dataclasses import dataclass

import requests


class PostError(Exception):
    """A platform rejected the post or could not be reached."""


class Skip(Exception):
    """The post is not applicable to this platform (e.g. no image for Instagram)."""


@dataclass
class Post:
    caption: str
    link: str = ""
    image_url: str = ""
    x_text: str = ""
    title: str = ""
    board_id: str = ""


def env(name, default=""):
    return os.environ.get(name, default).strip()


def request(method, url, retries=None, **kw):
    """HTTP call with sane errors. Never echoes URLs with secrets or retries POSTs
    (a retried POST could publish the same post twice)."""
    method = method.upper()
    if retries is None:
        retries = 2 if method == "GET" else 0
    kw.setdefault("timeout", 60)
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.request(method, url, **kw)
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code >= 500 and attempt < retries:
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code >= 400:
            raise PostError(f"{method} {url.split('?')[0]} -> {r.status_code}: {r.text[:300]}")
        return r
    raise PostError(f"network error: {type(last).__name__}")


def fetch_image(url, max_bytes=8 * 1024 * 1024):
    r = request("GET", url)
    if len(r.content) > max_bytes:
        raise PostError("image is larger than 8 MB")
    return r.content, r.headers.get("Content-Type", "image/jpeg").split(";")[0]
