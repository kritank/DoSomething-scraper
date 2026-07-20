# Instagram Hybrid Pipeline Plan: Graph API primary + minimal cookie enrichment

**Goal:** Make the **official, free Instagram Graph API "Business Discovery"**
endpoint the *primary* Instagram data source — structured exactly like our
YouTube integration (token pool + quota tracking + rotation) — and shrink the
cookie-based scraper (`app/scraper/client.py`) into a small, low-volume
**enrichment layer** that fetches only what the API cannot provide:

1. **Reel view/play counts** on third-party accounts
2. **Comment text** on third-party posts (`comment_sync`)
3. **Full scrapes of personal (non-professional) accounts** the API can't read

Everything else (profile, followers, full post history, like/comment counts,
reels classification) moves to the API. Cookie request volume drops to a
fraction of today's, which is what actually reduces flag risk — the cookie
pool stays, but it works ~70% less.

This document is the implementation spec. It assumes familiarity with the
existing YouTube pipeline (`app/scraper/youtube_client.py`,
`app/workers/youtube_job_processor.py`, `app/models/youtube_api_key.py`,
`app/repositories/youtube_api_key_repo.py`) — the Graph pipeline mirrors it
1:1 wherever possible.

---

## 1. How the official API works (background)

Meta's **Business Discovery** endpoint lets an Instagram *professional*
account (Business or Creator type) read **public data of any OTHER
professional account** by username:

```
GET https://graph.facebook.com/v23.0/{OUR_IG_USER_ID}
    ?fields=business_discovery.username(natgeo){
        username,name,biography,website,followers_count,follows_count,
        media_count,profile_picture_url,is_verified,
        media.limit(25).after(CURSOR){
            id,caption,like_count,comments_count,media_type,
            media_product_type,media_url,thumbnail_url,permalink,timestamp,
            children{media_type,media_url,thumbnail_url}
        }
    }
    &access_token={TOKEN}
```

- One HTTP call returns the profile **and** a page of media. `media.after()`
  cursors paginate deeper history.
- It is **free**. There is no billing anywhere in this plan.
- Auth is a long-lived (60-day, refreshable) access token belonging to *our
  own* IG professional account — the accounts we track never log in, never
  know, never get flagged. Our account cannot be "checkpointed" for reading
  via the official API.

### Two app flavors (implementer: verify current docs at build time)

1. **"Instagram API with Facebook Login"** (classic Graph API): requires our
   IG professional account to be linked to a Facebook Page. Business
   Discovery has been supported here forever. Token is a long-lived FB user
   token → exchanged for a Page-scoped token that effectively doesn't expire.
2. **"Instagram API with Instagram Login"**: no Facebook Page needed; tokens
   come from `graph.instagram.com`, are long-lived (60 days), and are
   refreshed via `GET /refresh_access_token`. Meta has been porting Business
   Discovery to this flavor — **verify it's supported before choosing it**;
   if in doubt, use flavor 1 (Facebook Login), which is guaranteed.

The app stays in **Development mode indefinitely** — that's fine because the
only Instagram account authorizing it is our own (an app admin/developer's
account). Dev mode restricts *which users can grant tokens*, not what data
Business Discovery returns. **No App Review needed.** Permissions to request:
`instagram_basic`, `instagram_manage_insights`, `pages_show_list`,
`pages_read_engagement` (the last two only for the Facebook-Login flavor).

### Rate limits

Business Discovery is governed by Meta's **Business Use Case (BUC)** rate
limit, computed per app-user pair over a rolling 24h window and reported in
the `X-Business-Use-Case-Usage` response header (percentages for `call_count`,
`total_cputime`, `total_time`). Practical planning number: **budget ~200
calls/hour per token** and read the header as ground truth. One influencer
scrape ≈ 1–3 calls (profile+first page, plus 1–2 pagination pages), so a
single token supports roughly **1,500–4,000 influencer scrapes/day**. Scale =
add more tokens (each needs its own IG professional account + app, see §10),
pooled exactly like YouTube API keys.

On HTTP error: code `4` / `17` / `32` / `613` or `(#80004)` ⇒ rate limited ⇒
treat like YouTube `quotaExceeded` (cooldown the token, rotate). Code `190`
⇒ token expired/invalid ⇒ mark token `invalid` (like `keyInvalid`). Error
`code: 100, error_subcode: 2108006` or message mentioning the account not
being a professional account ⇒ target not readable via API (permanent for
now) ⇒ route that influencer to the cookie fallback path (§7).

---

## 2. Source-of-truth matrix (who fetches what)

| Data | Source | Notes |
|---|---|---|
| Profile: name, bio, website, followers, following, media_count, avatar | **API** | cookie fields `pronouns`, `bio_links`, `highlight_reel_count`, business contact info are lost for API-scraped accounts — none are load-bearing; keep last-known values |
| `is_verified` | **API** (verify field availability at build; else keep last known) | |
| Post/reel: caption, permalink/shortcode, timestamp, like_count, comments_count, media_type, FEED-vs-REELS | **API** | `like_count` null when creator hides likes — store null, don't coerce to 0 |
| **NEW — not captured before:** `media_url` (direct image/video CDN URL), `thumbnail_url` (video/reel poster), carousel `children` (per-child type + URLs) | **API** | store in new `Post` columns + `platform_metadata` (§4); enables real thumbnails in dashboard without oEmbed hacks |
| Reel `play_count` / video `view_count` (third-party) | **Cookies** (enrichment job, §7) | API does not expose these for accounts we don't own |
| Comment text / comment authors / replies | **Cookies** (`comment_sync`, unchanged) | API exposes only `comments_count` for third-party media |
| `reshare_count`, `is_paid_partnership`, `music_metadata`, `locations`, `coauthor_producers`, `tagged_usernames`, `accessibility_caption`, `is_pinned`, `counts_disabled` | **Cookies** (same enrichment job — they ride along free on the feed response) | already parsed by `InstagramParser.parse_feed`; enrichment upserts them onto API-created rows |
| Personal (non-professional) accounts — everything | **Cookies** (full legacy scrape) | flagged `api_supported=false`, routed to legacy `JobProcessor` |
| Stories, others' audience demographics | Neither | not available by either method |

Merge key: posts are matched across the two sources by **shortcode**
(`posts.shortcode` is already unique). API `permalink` →
`instagram.com/p|reel/{shortcode}/`; cookie feed items carry `code`. Both
also carry the media pk (`business_discovery.media.id` vs cookie `pk`) —
store it in `posts.media_pk` from whichever source writes first and assert
agreement in the enrichment job.

---

## 3. What is required from the human (Kritank) — do this first

The implementer is blocked until these exist. Estimated time: ~30 minutes.

1. **Create/repurpose one Instagram account** you control and convert it to a
   **Professional account** (Settings → Account type → switch to Business or
   Creator). This is the "reader" account; it needs no followers/content.
2. *(Facebook-Login flavor only)* Create a **Facebook Page** (can be empty/
   unpublished) and link the IG professional account to it (IG Settings →
   Business tools → Connect a Facebook Page).
3. Go to <https://developers.facebook.com> → **Create App** → type
   **Business** → add the **Instagram** product (choose the API-with-
   Facebook-Login setup if doing flavor 1). App stays in Development mode.
4. Generate a token:
   - Flavor 1: Graph API Explorer → select the app → get a User token with
     `instagram_basic, instagram_manage_insights, pages_show_list,
     pages_read_engagement` → exchange it for a long-lived token
     (`GET /oauth/access_token?grant_type=fb_exchange_token&...`), then fetch
     the Page token from `GET /me/accounts`. Also note the **IG User ID**
     (`GET /{page-id}?fields=instagram_business_account`).
   - Flavor 2: use the app dashboard's Instagram business-login token
     generator for your account; note the returned IG User ID.
5. Hand the implementer: **App ID, App Secret, long-lived access token, IG
   User ID** — via the existing encrypted-secrets path (they will be stored
   encrypted in the DB by the register script, not in git).
6. **Sanity check before implementation starts** (paste into a terminal):

   ```bash
   curl "https://graph.facebook.com/v23.0/<IG_USER_ID>?fields=business_discovery.username(instagram){username,followers_count,media_count}&access_token=<TOKEN>"
   ```

   A JSON payload with `followers_count` proves the whole chain works. Save
   one full response (profile + media page, token scrubbed) as a test
   fixture for the implementer.
7. **Keep the existing cookie account pool alive** — it is still needed for
   the enrichment layer, just at much lower volume. No new cookie accounts
   required.
8. Later, for scale: repeat 1–5 per additional token (one IG professional
   account + app each). Not needed for launch; one token covers current load.

---

## 4. Data model changes

### New table `instagram_api_tokens` (mirror of `youtube_api_keys`)

New model `app/models/instagram_api_token.py`, Alembic migration, and
`app/repositories/instagram_api_token_repo.py` cloned from
`YouTubeApiKeyRepo` semantics (`get_usable_key` round-robin by
`last_used_at`, `record_usage`, `mark_exhausted(cooldown_until)`,
`mark_invalid`). Columns:

| column | notes |
|---|---|
| `id, label` | as youtube_api_keys |
| `access_token_encrypted` | Fernet-encrypted like `api_key_encrypted` |
| `ig_user_id` | our account's IG user id — required in every request path |
| `app_id`, `app_secret_encrypted` | needed for token refresh (§8) |
| `auth_flavor` | `"facebook_login"` \| `"instagram_login"` |
| `token_expires_at` | null for non-expiring Page tokens |
| `status` | `active` \| `cooldown` \| `invalid` (reuse youtube semantics) |
| `calls_today`, `cooldown_until` | quota bookkeeping (from BUC header + errors) |
| `buc_usage_pct` | last-seen max percentage from `X-Business-Use-Case-Usage` |
| `last_used_at / last_success_at / last_failure_at / failure_count / error_message / created_at / updated_at` | as youtube_api_keys |

### `influencers` table

Add nullable `api_supported: bool | None` (null = unknown/untried, true =
Business Discovery works, false = personal account → legacy cookie path).
Set false on the specific "not a professional account" error; set true on
first successful API scrape. Expose in the dashboard influencer list so the
cookie-dependent stragglers are visible.

### `posts` table — new API-only fields

Add nullable columns `media_url: Text` and `thumbnail_url: Text` (expiring
CDN URLs — refresh on every scrape like `profile_pic_url`; route through the
existing image-proxy origin when rendering). Carousel `children` go into the
existing `platform_metadata` JSONB under key `"children"` — no new column.

### Snapshots / metrics

No schema change. The API scrape records the follower/likes/comments
snapshot; reel views arrive later via enrichment. The enrichment job must
**update the same day's `PostMetricsSnapshot` row in place** (matched by
post + snapshot window) rather than inserting a second row, so time-series
charts don't get double points per day. Verify scoring/`feature_extraction`
tolerate `play_count` null-or-lagging for platform="instagram"; add a
regression test.

---

## 5. New client: `app/scraper/instagram_graph_client.py`

Clone the *shape* of `youtube_client.py` — same dependency-injected provider
callbacks so the client stays DB-free and unit-testable:

```python
TokenProvider   = Callable[[], Awaitable[tuple[UUID, str, str]]]  # (id, token, ig_user_id)
UsageRecorder   = Callable[[UUID, int, float], Awaitable[None]]   # (id, calls, buc_pct)
TokenExhauster  = Callable[[UUID, datetime], Awaitable[None]]     # cooldown_until
TokenInvalidator= Callable[[UUID, str], Awaitable[None]]
```

- Plain `httpx.AsyncClient` (no curl_cffi — official API has no fingerprint
  gate). Reuse `TokenBucketRateLimiter` (default ~150 req/hour/token, setting
  `INSTAGRAM_GRAPH_RATE_PER_HOUR`).
- `_request_with_token()` mirroring `_request_with_key`: retries w/ backoff on
  429/5xx/network (reuse `_BACKOFF_BASE_S/_BACKOFF_MAX_S` constants and
  `SCRAPER_MAX_RETRIES`), `_ROTATE` sentinel on quota errors (codes 4, 17,
  32, 613, `#80004`), `TokenInvalidator` on 190, capped by
  `_MAX_TOKEN_ROTATIONS`.
- Parse `X-Business-Use-Case-Usage` on every response; when max pct ≥ ~95,
  proactively mark the token exhausted with `cooldown_until = now + 1h`
  (BUC is a rolling 24h window — 1h cooldown then re-probe; do NOT copy
  YouTube's midnight-Pacific reset).
- Public methods:
  - `get_business_profile(username) -> dict` — profile fields + first media
    page in one call.
  - `get_business_media(username, after) -> dict` — pagination pages via
    `media.after(cursor)`.
- Error taxonomy (reuse `app/core/exceptions.py`):
  `ScraperRateLimitError(retry_after=...)` when every token is spent;
  `InfluencerNotFoundError` on error 110 "does not exist"; **new**
  `InstagramAccountNotProfessionalError` for the unsupported-target case;
  `NoUsableInstagramTokenError` mirroring `NoUsableYouTubeKeyError`.

New parser `app/scraper/instagram_graph_parser.py` (pure functions like
`youtube_parser.py`): `parse_profile(payload)`, `parse_media_items(payload)`,
`extract_media_cursor(payload)` → emit the same normalized shapes
(`InstagramUser`, `InstagramMediaItem`) the cookie `InstagramParser` emits,
with API-only fields (`media_url`, `thumbnail_url`, `children`) added to
`InstagramMediaItem` as optional, so the persistence layer is shared.

## 6. Field mapping (Business Discovery → existing normalized fields)

| existing field | Business Discovery source |
|---|---|
| `platform_user_id` (IG numeric pk) | `business_discovery.id` |
| `full_name` / `biography` / `external_url` | `name` / `biography` / `website` |
| `followers` / `following` / `media_count` | `followers_count` / `follows_count` / `media_count` |
| `profile_pic_url` | `profile_picture_url` |
| `is_verified` | `is_verified` (verify availability; else keep last known) |
| post `shortcode` | parse from `permalink` |
| post `taken_at` | `timestamp` (ISO8601 → epoch) |
| post `like_count` / `comment_count` | `like_count` (nullable) / `comments_count` |
| `is_reel` / `product_type` | `media_product_type` (`REELS` / `FEED`) |
| post `caption` | `caption` |
| `media_pk` | `media.id` |
| **new** `media_url` / `thumbnail_url` / children | `media_url` / `thumbnail_url` / `children{...}` |
| `play_count` / `view_count` | — (enrichment job, §7) |

## 7. Cookie layer, reduced: enrichment + fallback

The legacy pipeline survives in two narrow roles. Everything else about the
cookie infrastructure (account pool, proxies, login automator, curl_cffi
client) stays as-is — it just serves far fewer requests.

### 7a. Enrichment job (new, platform job type `instagram_enrich`)

New worker `app/workers/instagram_enrich_processor.py`. Triggered after a
successful Graph API scrape for the same influencer (dispatcher enqueues it
as a follow-on message; the API job's completion is the trigger, mirroring
how comment_sync is driven today).

- Calls only `InstagramClient.get_user_feed` (1–2 pages — enough to cover
  recent posts; **no** `get_user_info` profile call). Per influencer this is
  ~1–2 cookie requests vs ~4–6 in the legacy full scrape.
- For each feed item matched by shortcode to an API-created `Post` row:
  upsert `play_count`/`view_count` into the day's metrics snapshot (in
  place, §4) and upsert the cookie-only ride-along fields (`reshare_count`,
  `is_paid_partnership`, `music_metadata`, `locations`,
  `coauthor_producers`, `tagged_usernames`, `accessibility_caption`,
  `is_pinned`, `counts_disabled`).
- Then runs the existing `comment_sync` flow unchanged.
- **Degradation contract:** enrichment failure must never fail or retry the
  already-committed API scrape. If the cookie pool is exhausted/cooling
  down, the job completes as `partial` (new terminal status or reuse
  existing failure status + alert) — views/comments lag a cycle, core
  metrics are already fresh. This isolation is the main reason enrichment is
  a separate job rather than a phase inside the API job.
- Optional volume dial: setting `INSTAGRAM_ENRICH_EVERY_N_CYCLES` (default 1)
  to run enrichment less often than API scrapes if cookie pressure returns.

### 7b. Legacy full-scrape fallback (existing `JobProcessor`, unchanged)

For influencers with `api_supported=false` (personal accounts), the
dispatcher enqueues the legacy full cookie scrape instead of the API job.
No code changes beyond routing (§8).

## 8. Workers, routing & scheduler

- **`app/workers/instagram_graph_job_processor.py`** cloned from
  `youtube_job_processor.py` flow: resolve influencer → `get_business_profile`
  → paginate media up to existing per-scrape post cap → upsert influencer
  fields/avatar/`platform_user_id`/`api_supported=true` → upsert posts →
  `_record_metrics_snapshot` (reuse `job_common.py` heartbeat/finalization
  helpers) → enqueue `instagram_enrich` follow-on.
  On `InstagramAccountNotProfessionalError`: set `api_supported=false`,
  finish this job, and enqueue a legacy cookie scrape so the influencer
  isn't skipped this cycle.
- **`app/workers/instagram_token_provider.py`** cloned from
  `youtube_key_provider.py`, backed by `InstagramApiTokenRepo`.
- **Routing:** extend `worker_runner._run_one` from the current two-way
  branch to: `youtube` → `YouTubeJobProcessor`; `instagram` + influencer
  `api_supported is not False` → `InstagramGraphJobProcessor`; `instagram` +
  `api_supported is False` → legacy `JobProcessor`; `instagram_enrich` →
  `InstagramEnrichProcessor`. Global kill-switch setting
  `INSTAGRAM_BACKEND = "hybrid" | "cookies"` (default `cookies` until
  cutover) forces the legacy path if the API integration misbehaves.
- **Token refresh job** (scheduler entry, daily): for `instagram_login`
  tokens, call `GET graph.instagram.com/refresh_access_token` when
  `token_expires_at < now + 10d`, persist new token+expiry; alert (existing
  `alerts_service`) when refresh fails or expiry < 3d. `facebook_login` Page
  tokens: skip (non-expiring), but alert on any 190 seen in traffic.
- **Registration script** `scripts/register_instagram_api_token.py` cloned
  from `register_youtube_api_key.py`: prompts for label/app_id/app_secret/
  token/flavor, **validates by making one live Business Discovery call**,
  resolves + stores `ig_user_id`, encrypts secrets.

## 9. Config additions (`app/core/config.py`)

`INSTAGRAM_BACKEND` (`"hybrid" | "cookies"`, default `"cookies"` until
cutover, flipped in the cutover PR), `INSTAGRAM_GRAPH_API_VERSION` (default
`"v23.0"` — check current at build), `INSTAGRAM_GRAPH_RATE_PER_HOUR`
(default 150), `INSTAGRAM_GRAPH_MEDIA_PAGE_SIZE` (default 25 — docs cap
business_discovery media page size; verify and clamp),
`INSTAGRAM_ENRICH_EVERY_N_CYCLES` (default 1),
`INSTAGRAM_ENRICH_FEED_PAGES` (default 2).

## 10. Scaling & ops

- API scale unit = one token (= one IG professional account + one dev app).
  Pool behaves exactly like the YouTube key pool; adding capacity is running
  the register script once per token. 3–5 tokens ≫ current needs.
- Do **not** create bulk fake accounts to farm tokens — a handful of
  legitimate accounts (team members' professional accounts) is compliant and
  sufficient.
- Cookie pool sizing: post-cutover cookie volume ≈ (2 feed pages + comment
  pages) per influencer per cycle, no profile calls, no personal-account
  overhead except the few `api_supported=false` stragglers. Expect the
  existing pool to be oversized — keep it; slack capacity = lower per-account
  request rate = fewer flags.
- Monitoring: extend `credential_health_snapshot`/dashboard to show the API
  token pool (`buc_usage_pct`, cooldowns, expiries) alongside YouTube keys
  and cookie-account health. Alert if enrichment lag (posts with fresh
  like counts but stale view counts) exceeds 2 cycles.

## 11. Implementation order (each step lands green tests)

1. **PR 1 — API foundation:** token model + migration + repo + register
   script + `InstagramGraphClient` + graph parser + new exceptions + config
   + `posts.media_url/thumbnail_url` migration. Unit tests cloned from
   `test_youtube_client.py` / `test_youtube_api_key_repo.py` /
   `test_youtube_parser.py` patterns, using the recorded fixture from §3.6.
2. **PR 2 — API pipeline:** `InstagramGraphJobProcessor` + token provider +
   routing + `api_supported` handling + token refresh scheduler job +
   null-`play_count` regression tests. Enrichment not wired yet — API path
   runs standalone behind `INSTAGRAM_BACKEND="hybrid"` in a dev environment.
3. **PR 3 — enrichment:** `InstagramEnrichProcessor` + follow-on enqueue +
   in-place snapshot merge + partial-completion semantics + legacy-fallback
   routing for `api_supported=false`.
4. **PR 4 — cutover:** flip default to `hybrid`; run
   `scripts/seed_and_scrape.py` against real influencers; compare snapshots
   vs cookie-era data (followers within drift, posts matched by shortcode,
   views populated by enrichment); dashboard token-pool health panel.
5. **PR 5 — slimming:** remove now-dead legacy code paths that neither the
   enrichment job nor the personal-account fallback uses (e.g. profile-info
   fetch inside enrichment scope), retire surplus proxies if cookie volume
   allows. The cookie client itself stays.

## 12. Verification checklist (PR 4)

- [ ] One full scheduled cycle: every `api_supported≠false` influencer scraped
      via API; cookie calls appear only from enrichment + fallback jobs.
- [ ] Influencer profile + ≥50 historical posts persisted for a paginated account.
- [ ] Reels: like/comment counts written by API job, `play_count` filled in by
      enrichment into the SAME day's snapshot row (no duplicate rows).
- [ ] Post thumbnails render in dashboard from new `media_url`/`thumbnail_url`
      via the image proxy.
- [ ] Comment sync still ingests comment text/replies post-cutover.
- [ ] Personal-account influencer → `api_supported=false` → legacy scrape ran
      same cycle, visible in UI.
- [ ] Cookie pool exhaustion during enrichment → API data committed, job
      `partial`, alert fired, no retry storm.
- [ ] Token cooldown path exercised (force with a tiny rate limit) and
      recovery observed; BUC percentages visible in health snapshot.
- [ ] `INSTAGRAM_BACKEND="cookies"` kill switch restores legacy behavior.
