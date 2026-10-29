"""Offline tests: no network, every HTTP call is mocked.  Run: python -m unittest discover -s tests"""
import os, sys, tempfile, unittest, csv
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import poster
from platforms import facebook, instagram, linkedin, pinterest, x
from platforms.common import Post, PostError


class Resp:
    def __init__(self, j=None, headers=None, content=b"img"):
        self._j, self.headers, self.content = j or {}, headers or {}, content
    def json(self): return self._j


ENV = dict(FB_PAGE_ID="1", FB_PAGE_ACCESS_TOKEN="t", IG_USER_ID="2", LINKEDIN_ACCESS_TOKEN="l",
           LINKEDIN_AUTHOR_URN="urn:li:person:abc", X_API_KEY="a", X_API_SECRET="b", X_ACCESS_TOKEN="c",
           X_ACCESS_TOKEN_SECRET="d", PINTEREST_ACCESS_TOKEN="p", PINTEREST_BOARD_ID="9")


def hours_ago(h):
    return (datetime.now(timezone.utc) - timedelta(hours=h)).astimezone(poster.TZ).strftime("%Y-%m-%d %H:%M")


class PlatformTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, ENV); p.start(); self.addCleanup(p.stop)

    def test_facebook_photo_and_text(self):
        with mock.patch.object(facebook, "request", return_value=Resp({"post_id": "1_2"})) as r:
            self.assertEqual(facebook.publish(Post("hi", "http://l", "http://i.jpg")), "1_2")
            self.assertTrue(r.call_args[0][1].endswith("/1/photos"))
            facebook.publish(Post("hi"))
            self.assertTrue(r.call_args[0][1].endswith("/1/feed"))

    def test_instagram_two_step(self):
        seq = [Resp({"id": "c1"}), Resp({"status_code": "FINISHED"}), Resp({"id": "m1"})]
        with mock.patch.object(instagram, "request", side_effect=seq):
            self.assertEqual(instagram.publish(Post("hi", image_url="http://i.jpg")), "m1")
        with self.assertRaises(Exception):
            instagram.publish(Post("no image"))

    def test_linkedin_escapes_and_returns_id(self):
        with mock.patch.object(linkedin, "request", return_value=Resp(headers={"x-restli-id": "urn:li:share:1"})) as r:
            linkedin.publish(Post("Save (20%) now_ #tag"))
            body = r.call_args.kwargs["json"]
            self.assertIn("\\(20%\\)", body["commentary"])
            self.assertIn("#tag", body["commentary"])

    def test_x_truncates_to_280_with_link(self):
        t = x.build_text(Post("word " * 100, link="https://example.com/very/long/path"))
        self.assertLessEqual(x.weighted_len(t), 280)
        self.assertTrue(t.endswith("https://example.com/very/long/path"))

    def test_x_falls_back_to_text_when_media_refused(self):
        calls = []
        def fake(method, url, **kw):
            calls.append(url)
            if "media" in url: raise PostError("403")
            return Resp({"data": {"id": "77"}})
        with mock.patch.object(x, "request", side_effect=fake), mock.patch.object(x, "fetch_image", return_value=(b"i", "image/jpeg")):
            self.assertEqual(x.publish(Post("hi", image_url="http://i.jpg")), "77")

    def test_pinterest_body(self):
        with mock.patch.object(pinterest, "request", return_value=Resp({"id": "pin1"})) as r:
            self.assertEqual(pinterest.publish(Post("Title line\nmore", "http://l", "http://i.jpg")), "pin1")
            b = r.call_args.kwargs["json"]
            self.assertEqual((b["board_id"], b["title"]), ("9", "Title line"))


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cal = os.path.join(self.dir, "cal.csv")
        p = mock.patch.dict(os.environ, ENV); p.start(); self.addCleanup(p.stop)
        mock.patch.object(poster, "CALENDAR", self.cal).start(); self.addCleanup(mock.patch.stopall)

    def write(self, rows):
        with open(self.cal, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=poster.FIELDS); w.writeheader()
            for r in rows: w.writerow({k: r.get(k, "") for k in poster.FIELDS})

    def read(self):
        with open(self.cal) as f:
            return list(csv.DictReader(f))

    def patch_all(self, fail=()):
        self.mocks = {}
        for name, mod in poster.REGISTRY.items():
            def pub(post, name=name):
                if name in fail: raise PostError("boom")
                return f"{name}-id"
            self.mocks[name] = mock.patch.object(mod, "publish", side_effect=pub).start()

    def test_due_future_and_overdue(self):
        self.write([
            dict(id="1", publish_at=hours_ago(1), platforms="facebook,x", caption="a", status="pending"),
            dict(id="2", publish_at=hours_ago(-5), platforms="all", caption="future", status="pending"),
            dict(id="3", publish_at=hours_ago(48), platforms="all", caption="old", status="pending"),
        ])
        self.patch_all()
        self.assertEqual(poster.run("post"), 0)
        rows = {r["id"]: r for r in self.read()}
        self.assertEqual(rows["1"]["status"], "posted")
        self.assertIn("facebook=ok:facebook-id", rows["1"]["done"])
        self.assertEqual(rows["2"]["status"], "pending")
        self.assertEqual(rows["3"]["status"], "missed")

    def test_partial_failure_retries_only_failed_platform(self):
        self.write([dict(id="1", publish_at=hours_ago(1), platforms="facebook,x", caption="a", status="pending")])
        self.patch_all(fail=("x",))
        self.assertEqual(poster.run("post"), 1)
        row = self.read()[0]
        self.assertEqual(row["status"], "partial")
        self.assertIn("facebook=ok", row["done"]); self.assertIn("boom", row["errors"])
        self.mocks["x"].side_effect = lambda post: "x-id"
        poster.run("post")
        row = self.read()[0]
        self.assertEqual(row["status"], "posted")
        self.assertEqual(self.mocks["facebook"].call_count, 1)  # not posted twice

    def test_dry_run_changes_nothing(self):
        self.write([dict(id="1", publish_at=hours_ago(1), platforms="all", caption="a", status="pending")])
        self.patch_all()
        poster.run("dry-run")
        self.assertEqual(self.read()[0]["status"], "pending")
        self.mocks["facebook"].assert_not_called()

    def test_unconfigured_platform_skipped_and_bad_row(self):
        with mock.patch.dict(os.environ, {"PINTEREST_ACCESS_TOKEN": ""}):
            self.write([dict(id="1", publish_at=hours_ago(1), platforms="pinterest", caption="a", status="pending"),
                        dict(id="2", publish_at=hours_ago(1), platforms="myspace", caption="a", status="pending")])
            self.patch_all(); poster.run("post")
        rows = {r["id"]: r for r in self.read()}
        self.assertEqual(rows["1"]["status"], "posted"); self.assertIn("pinterest=skipped", rows["1"]["done"])
        self.assertEqual(rows["2"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
