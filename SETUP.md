# Social Autopost: setup guide

Free auto-poster for **Facebook, Instagram, LinkedIn, X and Pinterest**.
GitHub Actions runs `poster.py` every 30 minutes. It reads `content_calendar.csv`, publishes whatever is due, and saves the result back into the CSV.

Platforms change their API rules often. Treat the steps below as a map and check each portal's current screens. **Connect one platform at a time and test with `check` mode before moving on.**

---

## 1. Put it on GitHub (10 minutes)

1. Create a **public** GitHub repository (public = unlimited free Actions minutes, and Instagram/Pinterest can fetch your images from it). Your API keys never go in the repo; they live in GitHub Secrets.
2. Upload everything in this folder, including the hidden `.github` folder.
3. Repo → **Settings → Actions → General → Workflow permissions** → choose **Read and write permissions** → Save.
4. Repo → **Settings → Secrets and variables → Actions**. This is where each key below goes (**New repository secret**).
5. Optional: under the **Variables** tab add `TIMEZONE` (default is `Asia/Karachi`).

Test any time: **Actions → Social Autopost → Run workflow → mode: `check`**. It prints `[OK]`, `[--]` (not configured) or `[!!]` (broken) for each platform.

---

## 2. Facebook Page + Instagram (one Meta app covers both)

Needs: a Facebook Page you admin; an Instagram **Business or Creator** account linked to that Page.

1. Go to developers.facebook.com → **Create App** → type **Business** (or "Other"). Keep it in **Development mode**. For your own Page you don't need app review.
2. Open **Tools → Graph API Explorer**. Pick your app and generate a **User token** with these permissions:
   `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`, `instagram_basic`, `instagram_content_publish`, `business_management`
3. Make it long-lived. Open this URL in a browser (fill in the three values from your app's Settings → Basic):
   `https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=SHORT_USER_TOKEN`
4. Get the **Page token** (a Page token made from a long-lived user token does not expire). In Graph API Explorer, paste the long-lived token and call `GET /me/accounts`. Copy your Page's `id` and `access_token`.
5. Get the Instagram ID: `GET /PAGE_ID?fields=instagram_business_account` and copy the `id` inside it.

Secrets to add:

| Secret | Value |
|---|---|
| `FB_PAGE_ID` | the Page id |
| `FB_PAGE_ACCESS_TOKEN` | the Page access token |
| `IG_USER_ID` | the `instagram_business_account` id |

Instagram notes: every post needs an image (JPEG), and links in captions are not clickable.

---

## 3. LinkedIn

1. developers.linkedin.com → **Create app**. It must be tied to a LinkedIn Page (create a free one if you only have a personal profile).
2. **Products** tab: request **Share on LinkedIn** (instant, personal profile posting) and **Sign In with LinkedIn using OpenID Connect**.
3. Open the **OAuth token generator** (developers.linkedin.com/tools → OAuth Token Generator), tick `w_member_social`, `openid`, `profile`, and generate a token. **It lasts 60 days.** Generate a new one and update the secret when `check` mode shows `[!!] linkedin`.
4. Get your member id:
   `curl -H "Authorization: Bearer YOUR_TOKEN" https://api.linkedin.com/v2/userinfo` → copy `sub`. Your author URN is `urn:li:person:` + that value.

| Secret | Value |
|---|---|
| `LINKEDIN_ACCESS_TOKEN` | the token |
| `LINKEDIN_AUTHOR_URN` | `urn:li:person:xxxxxxxx` |

Posting to a **company page** instead needs LinkedIn's Community Management API approval (a form review, not instant). Then use `urn:li:organization:ID` with `w_organization_social`.

---

## 4. X (Twitter)

1. developer.x.com → sign up for the **Free** tier → create a Project and App.
2. App → **User authentication settings** → set permissions to **Read and write** *first*.
3. **Keys and tokens** → copy API Key & Secret, then **generate** Access Token & Secret. Generate them *after* step 2, otherwise they are read-only and posting fails with 403.

| Secret | Value |
|---|---|
| `X_API_KEY` / `X_API_SECRET` | consumer key and secret |
| `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET` | the access token pair |

The free tier allows about 500 posts per month. If X refuses image upload on the free tier, the script posts the text and link without the image and says so in the log. Use the `x_text` column to write a shorter 280-character version.

---

## 5. Pinterest (the strictest one)

1. developers.pinterest.com → **My apps → Connect app**.
2. New apps start with **Trial access**, which only works against the **sandbox** (test pins aren't public). To post for real, apply for **Standard access** from the app page. Pinterest reviews it manually and may ask for a short demo video.
3. Generate an access token (scopes `boards:read`, `pins:read`, `pins:write`) from the app page. For long-term use, also save the **refresh token**, so the script gets a fresh access token on every run.
4. Find your board id: run `check` mode (it lists your boards and ids).

| Secret | Value |
|---|---|
| `PINTEREST_ACCESS_TOKEN` | token (skip if using refresh token) |
| `PINTEREST_REFRESH_TOKEN`, `PINTEREST_APP_ID`, `PINTEREST_APP_SECRET` | recommended for long-term use |
| `PINTEREST_BOARD_ID` | default board |

While on Trial access, add a repository **variable** `PINTEREST_API_BASE` = `https://api-sandbox.pinterest.com`. Delete it once Standard access is approved.

---

## 6. Using the calendar

Edit `content_calendar.csv` (Excel or Google Sheets works; export as CSV), commit, done.

| Column | What to put |
|---|---|
| `id` | any unique number |
| `publish_at` | `2026-11-02 10:00` (in your `TIMEZONE`) |
| `platforms` | `all`, or a list like `facebook,linkedin,x`. Names: facebook, instagram, linkedin, x, pinterest |
| `caption` | main text (hashtags included) |
| `link` | optional URL |
| `image` | file name from the `images/` folder (e.g. `promo1.jpg`) **or** a full public image URL |
| `x_text` | optional shorter text for X |
| `pinterest_title` / `pinterest_board_id` | optional |
| `status`, `done`, `errors`, `attempts`, `posted_at` | filled by the bot, leave blank |

Behaviour worth knowing:
- Runs every 30 minutes, so a post goes out within about 30 to 40 minutes of `publish_at`. GitHub sometimes delays scheduled runs.
- Rows that are more than 24 hours late are marked `missed` instead of posting stale content (`MAX_LATE_HOURS`).
- If one platform fails, the others still post, and only the failed one is retried (up to 3 attempts, then `failed`).
- Platforms without secrets are skipped, not errored. If you connect one later, posts already marked `posted` won't be re-sent to it.
- Instagram and Pinterest are skipped for rows with no image.
- GitHub pauses scheduled workflows after 60 days with no repo activity. If posts stop, open the Actions tab and re-enable it.
- To preview without posting: **Run workflow → mode: `dry-run`**.

## 7. Run it on your own computer (optional)

```
pip install -r requirements.txt
export FB_PAGE_ID=... FB_PAGE_ACCESS_TOKEN=...   # and the other secrets
python poster.py --mode check
python poster.py --mode dry-run
python -m unittest discover -s tests            # offline self-tests
```
