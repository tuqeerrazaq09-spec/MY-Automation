#!/usr/bin/env python3
"""Reads content_calendar.csv and publishes every post that is due.

Modes:
  post      publish due posts and update the calendar (default)
  dry-run   show what would be published, change nothing
  check     verify that each platform's credentials work, post nothing
"""
import argparse
import csv
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from platforms import REGISTRY, Post, PostError, Skip

CALENDAR = os.environ.get("CALENDAR_FILE", "content_calendar.csv")
TZ = ZoneInfo(os.environ.get("TIMEZONE", "Asia/Karachi"))
MAX_LATE_HOURS = float(os.environ.get("MAX_LATE_HOURS", "24"))
MAX_POSTS_PER_RUN = int(os.environ.get("MAX_POSTS_PER_RUN", "5"))
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "3"))

FIELDS = ["id", "publish_at", "platforms", "caption", "link", "image", "x_text",
          "pinterest_title", "pinterest_board_id", "status", "done", "errors", "attempts", "posted_at"]
OPEN_STATUSES = ("", "pending", "partial")


def parse_time(value):
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


def resolve_image(value):
    """Full URLs are used as-is; a bare file name means images/<name> in this GitHub repo."""
    value = value.strip()
    if not value or value.startswith(("http://", "https://")):
        return value
    repo, branch = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_REF_NAME", "main")
    if not repo:
        return value
    return f"https://raw.githubusercontent.com/{repo}/{branch}/images/{value.lstrip('/')}"


def targets(row):
    raw = row["platforms"].strip().lower()
    if raw in ("", "all"):
        return list(REGISTRY)
    names = [n for n in re.split(r"[,;| ]+", raw) if n]
    unknown = [n for n in names if n not in REGISTRY]
    if unknown:
        raise ValueError(f"unknown platform(s): {', '.join(unknown)}")
    return names


def read_calendar():
    with open(CALENDAR, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in FIELDS:
            r.setdefault(k, "")
            r[k] = r[k] or ""
    return rows


def write_calendar(rows):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(CALENDAR)), suffix=".tmp")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, CALENDAR)


def parse_done(text):
    return dict(p.split("=", 1) for p in text.split(";") if "=" in p)


def check_mode():
    ok = True
    for name, mod in REGISTRY.items():
        if not mod.configured():
            print(f"[--] {name}: not configured (secrets missing), will be skipped")
            continue
        try:
            print(f"[OK] {name}: {mod.check()}")
        except Exception as e:  # noqa: BLE001 - report any failure per platform
            ok = False
            print(f"[!!] {name}: {e}")
    return 0 if ok else 1


def run(mode):
    dry = mode == "dry-run"
    now = datetime.now(timezone.utc)
    rows = read_calendar()
    posted_count, changed, had_error = 0, False, False

    for row in rows:
        if row["status"].strip().lower() not in OPEN_STATUSES:
            continue
        try:
            when = parse_time(row["publish_at"])
            plat = targets(row)
        except ValueError as e:
            if not dry:
                row["status"], row["errors"], changed = "failed", f"bad row: {e}", True
            print(f"row {row['id'] or '?'}: bad row ({e})")
            continue
        if when > now:
            continue
        if now - when > timedelta(hours=MAX_LATE_HOURS):
            print(f"row {row['id']}: more than {MAX_LATE_HOURS:g}h overdue, marking missed")
            if not dry:
                row["status"], changed = "missed", True
            continue
        if posted_count >= MAX_POSTS_PER_RUN:
            print("post limit for this run reached, remaining rows wait for the next run")
            break

        post = Post(caption=row["caption"].strip(), link=row["link"].strip(), image_url=resolve_image(row["image"]),
                    x_text=row["x_text"].strip(), title=row["pinterest_title"].strip(),
                    board_id=row["pinterest_board_id"].strip())
        done = parse_done(row["done"])
        errors = []
        print(f"row {row['id']}: publishing to {', '.join(plat)}")
        for name in plat:
            if name in done:
                continue
            mod = REGISTRY[name]
            if not mod.configured():
                done[name] = "skipped"
                print(f"  {name}: not configured, skipped")
                continue
            if dry:
                print(f"  {name}: DRY RUN, would post: {post.caption[:70]!r}")
                continue
            try:
                done[name] = "ok:" + str(mod.publish(post))
                print(f"  {name}: posted ({done[name][3:]})")
            except Skip as e:
                done[name] = "skipped"
                print(f"  {name}: skipped ({e})")
            except PostError as e:
                errors.append(f"{name}: {e}")
                print(f"  {name}: FAILED {e}")
            except Exception as e:  # noqa: BLE001 - one platform must not stop the others
                errors.append(f"{name}: {type(e).__name__}")
                print(f"  {name}: FAILED {type(e).__name__}")
        if dry:
            posted_count += 1
            continue

        had_error = had_error or bool(errors)
        row["done"] = ";".join(f"{k}={v}" for k, v in done.items())
        row["errors"] = " | ".join(errors)
        row["attempts"] = str(int(row["attempts"] or 0) + 1)
        if all(n in done for n in plat):
            row["status"], row["posted_at"] = "posted", now.astimezone(TZ).strftime("%Y-%m-%d %H:%M")
        else:
            row["status"] = "failed" if int(row["attempts"]) >= MAX_ATTEMPTS else "partial"
        posted_count += 1
        changed = True

    if changed and not dry:
        write_calendar(rows)
    print(f"done: {posted_count} row(s) processed")
    return 1 if had_error else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["post", "dry-run", "check"], default="post")
    args = ap.parse_args()
    return check_mode() if args.mode == "check" else run(args.mode)


if __name__ == "__main__":
    sys.exit(main())
