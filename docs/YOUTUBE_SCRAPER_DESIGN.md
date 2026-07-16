# YouTube Scraper — Design Document

Status: **approved for implementation** · Target implementer: Claude Sonnet · Last updated: 2026-07-16

This document specifies how Viralytics gains a second platform (YouTube) alongside the
existing Instagram scraper. It is written to be implemented top-to-bottom without further
design decisions. Read `app/workers/job_processor.py` and `app/scraper/client.py` first —
the YouTube pipeline deliberately mirrors their structure and reuses their job/queue/
scheduler machinery.

---

## 1. Goals & non-goals

**Goals**
- Scrape YouTube channels (profile), videos (posts), and comments (incl. reply threads)
  into the *same* core tables the Instagram pipeline writes, so benchmarks,
  recommendations, the dashboard, and the feature store work across both platforms.
- Robustness parity: backfill with resumable cursor, heartbeats, cancellation, retries,
  graceful partial progress, raw-payload capture for schema-drift diagnosis.
- Efficiency: minimum API calls per unit of data (batched lookups, change-diffed comment
  sync — same tricks the IG pipeline already uses).

**Non-goals (v1)**
- No transcript/audio scraping, no YouTube Shorts-feed discovery beyond the uploads
  playlist, no Studio/owner analytics (retention, CTR — not public), no live-chat capture.
- No cross-posting identity resolution (linking an IG influencer row to a YT row).

---

## 2. Data source decision

**Use the official YouTube Data API v3, not HTML/Innertube scraping.**

| | Data API v3 (chosen) | Innertube / HTML scraping |
|---|---|---|
| Auth | Plain API key, no login, no cookies | None, but bot-detection arms race |
| Accuracy | Canonical counts, documented semantics | Rendered/abbreviated counts ("1.2M") |
| Cost | Free, 10,000 units/project/day | Free |
| Fragility | Versioned, stable for years | Breaks silently on frontend changes |
| Infra | No proxies, no TLS impersonation, plain httpx | curl_cffi + residential proxies |

Everything this platform needs (subscriber/view counts, video stats, full comment
threads) is served by the API at ~1 quota unit per request. All of the Instagram
pipeline's hardest problems — session pools, checkpoints, TLS fingerprinting, sticky
proxies — simply do not exist here. The only scarce resource is **daily quota**, which we
manage with a key pool (§6).

Quota math per influencer per daily run: 1 (channel) + 1–2 (uploads pages) + 1–2
(videos.list batches) + ~1–3 per comment-synced video. A 30-day comment window over an
active channel is ≈ 50–150 units/day, so **one key supports ~60–100 influencers/day**;
backfills cost more and are why the pool exists.

---

## 3. Review of current captured data → YouTube mapping

Full audit of what the IG pipeline stores today and what YouTube provides. Legend:
✅ maps directly · 🔧 needs schema change · 🆕 new YT-only field · ❌ not publicly available
on YouTube (store NULL, never 0).

### 3.1 Profile (`profile_snapshots`) ← `channels.list` (part=snippet,statistics,contentDetails,brandingSettings,status,topicDetails)

| Column | YouTube source | Notes |
|---|---|---|
| followers | `statistics.subscriberCount` | ✅ **Accuracy caveat:** the API rounds to 3 significant figures (e.g. 2,340,000, not 2,341,982). Store as-is; document in dashboard. If `statistics.hiddenSubscriberCount` is true, store NULL → needs `followers` to stay 0-default but write NULL via new `subscribers_hidden` flag (see 🆕 below). |
| following | — | ❌ NULL/0 — channels don't follow. Write 0. |
| posts | `statistics.videoCount` | ✅ |
| biography | `snippet.description` | ✅ |
| external_url | `brandingSettings.channel.unsubscribedTrailer`? No — use custom URL: `snippet.customUrl` (e.g. `@mkbhd`) | ✅ store customUrl here |
| is_verified | — | ❌ Data API doesn't expose the verification badge. Write false. |
| category_name / category_enum / overall_category_name | `topicDetails.topicCategories` (Wikipedia URLs) | 🔧 store first topic's trailing path segment in `category_name`, full list in `platform_metadata` |
| bio_links | — | ❌ (channel links not in Data API). NULL. |
| business_email etc. | — | ❌ NULL. |
| highlight_reel_count, has_clips, has_guides, has_channel, mutual_followers_count, is_meta_verified, has_ar_effects, hides_like_view_counts | — | ❌ IG-only. Defaults. |
| 🆕 total channel views | `statistics.viewCount` | **Missing today and important** — a channel-level lifetime view count has no IG equivalent and is a core YT benchmark input. Needs a new `total_views BIGINT NULL` column (MrBeast is ~90B — must be BIGINT). |
| 🆕 subscribers_hidden | `statistics.hiddenSubscriberCount` | New `BOOLEAN NOT NULL DEFAULT false` column — distinguishes "0 subscribers" from "hidden". |
| 🆕 channel created date, country, keywords, madeForKids | `snippet.publishedAt`, `snippet.country`, `brandingSettings.channel.keywords`, `status.madeForKids` | Store in new `platform_metadata JSONB NULL` column on `profile_snapshots` — don't mint one column each. |

### 3.2 Posts (`posts`) ← `playlistItems.list` (discovery) + `videos.list` (detail, batched ×50)

`videos.list` parts: `snippet,statistics,contentDetails,status,topicDetails,liveStreamingDetails,paidProductPlacementDetails`.

| Column | YouTube source | Notes |
|---|---|---|
| shortcode | video ID (11 chars) | ✅ unique across YT; String(64) fits. This stays the natural key exactly as for IG. |
| media_pk | video ID again | ✅ (keeps comment-sync code uniform) |
| caption | `snippet.description` | 🔧 YouTube separates **title** from description; IG has no title. Add `title TEXT NULL` to `posts` (NULL for IG rows). Do **not** concatenate title into caption — it would corrupt caption_length/word_count benchmarks. |
| hashtags / mentions | parsed from description (+ title) by the existing `nlp_utils` | ✅ also merge `snippet.tags` (creator-set, invisible on page) into `platform_metadata` — tags are a distinct signal from in-description hashtags; don't mix them. |
| posted_at | `snippet.publishedAt` (ISO8601) | ✅ |
| permalink | `https://www.youtube.com/watch?v={id}` | ✅ |
| accessibility_caption | `contentDetails.caption` ("true"/"false" = has closed captions) | 🔧 semantic mismatch; store `"captions_available"` / NULL instead of abusing it — better: put in `platform_metadata.has_captions` and leave column NULL. |
| is_paid_partnership | `paidProductPlacementDetails.hasPaidProductPlacement` | ✅ |
| product_type | derived: `"video"` \| `"short"` \| `"live"` \| `"upcoming"` | ✅ same role as IG's `"clips"`/`"feed"`. Shorts detection: `liveBroadcastContent=="none"` and duration ≤ 183s **and** (aspect from thumbnail unavailable in API) — accept the duration heuristic in v1, it drives `media_type` labeling only. Live: `liveStreamingDetails` present. |
| music_metadata | — | ❌ NULL. |
| original_height/width | `snippet.thumbnails.maxres` dims | 🔧 thumbnail dims, not video dims — put in `platform_metadata`, leave columns NULL. `contentDetails.definition` ("hd"/"sd") + `dimension` ("2d"/"3d") also go to `platform_metadata`. |
| locations | `recordingDetails.location` (usually absent) | ✅ same JSONB shape `[{lat,lng,...}]` when present. |
| coauthor_producers / tagged_usernames | — | ❌ NULL. |
| counts_disabled | true when `statistics.likeCount` is **absent** (creator hid likes) | ✅ same semantics as IG. |
| 🆕 duration | `contentDetails.duration` (ISO8601 e.g. `PT12M34S`) | Parse to seconds → feeds `feature_store.reel_duration_s` (existing column — reuse, rename is not worth a migration; it's documented as "video duration"). Also store raw in `platform_metadata`. |
| 🆕 category, default language, madeForKids, licensedContent, topicCategories | snippet/status/topicDetails | `platform_metadata JSONB` on posts. |

**New column summary for `posts`:** `title TEXT NULL`, `platform_metadata JSONB NULL`.

### 3.3 Post metrics (`post_metrics_snapshots`) ← `videos.list statistics`

| Column | YouTube source | Notes |
|---|---|---|
| likes | `statistics.likeCount` | 🔧 **Absent when creator hides likes** — current column is `Integer NOT NULL default 0`, which would silently record "0 likes" for hidden. Migration: make `likes` **nullable** (NULL = hidden/unavailable, matches the existing `views` convention). Max real-world likes (~60M) fits Integer. |
| comments | `statistics.commentCount` | 🔧 **Absent when comments are disabled** — same fix: make `comments` **nullable**. |
| views | `statistics.viewCount` | ✅ already `BigInteger NULL` — correct, YT views exceed 2.1B routinely. Always present for public videos. |
| reposts | — | ❌ YouTube has **no public share count**. Current column is `NOT NULL default 0` → would fabricate "0 shares". Migration: make `reposts` **nullable**; IG writes keep passing real values, YT writes NULL. |
| ❌ dislikes | removed from public API in 2021 | Do not attempt (third-party estimate APIs are out of scope). |
| ❌ favoriteCount | deprecated, always 0 | Do not store. |

### 3.4 Comments (`comments`) ← `commentThreads.list` + `comments.list`

`commentThreads.list?videoId=…&part=snippet,replies&maxResults=100&order=time&textFormat=plainText`.
Each thread inlines up to 5 replies; when `snippet.totalReplyCount > len(replies.comments)`,
page the full thread via `comments.list?parentId=…&maxResults=100`.

| Column | YouTube source | Notes |
|---|---|---|
| comment_id | thread/comment `id` | 🔧 **Reply IDs are `parentId.childId` (~53 chars each side) and can exceed 64 chars.** Migration: widen `comments.comment_id` and `parent_comment_id` to `String(128)`. |
| parent_comment_id | `snippet.parentId` | ✅ |
| username | `snippet.authorDisplayName` | ✅ |
| full_name | "" | ✅ (no separate full name) |
| is_verified | — | ❌ false. |
| is_from_creator | `snippet.authorChannelId.value == influencer's channel_id` | 🔧 IG compares usernames; YT must compare **channel IDs** (display names are not unique). Requires storing the influencer's resolved channel ID (§4.1). Also store the raw author channel id in a new `author_external_id VARCHAR(64) NULL` column so the check is reproducible. |
| text | `snippet.textOriginal` | ✅ (plainText requested) |
| like_count | `snippet.likeCount` | ✅ |
| child_comment_count | `snippet.totalReplyCount` | ✅ — drives the same "only re-walk changed threads" diff as IG. |
| liked_by_creator | — | ❌ (creator hearts not exposed). false. |
| is_edited | `updatedAt != publishedAt` | ✅ derive. |
| reported_as_spam | — | ❌ false. |
| commented_at | `snippet.publishedAt` | ✅ |
| author_profile_pic_url | `snippet.authorProfileImageUrl` | ✅ |
| author_is_private | — | ❌ false. |

**Ordering caveat:** `order=time` is newest-first and stable — equivalent to IG's
`chronological` fix. Use it always.

### 3.5 Feature store — no schema change

`FeatureExtractor.extract_features` runs on `post.caption` (the description) unchanged.
Additions in the YT processor:
- `media_type`: `"video"` / `"short"` / `"live"` (replaces IG's image/video/carousel labels).
- `reel_duration_s`: parsed duration seconds (finally populating a column IG never fills).
- Engagement-timing features (`first_comment_at`, creator replies) work as-is — they're
  computed from the `comments` table, which YT populates identically.

---

## 4. Schema changes (one Alembic migration, autogenerate then hand-check)

### 4.1 `influencers` — platform discriminator + resolved ID

```python
platform:        Mapped[str] = mapped_column(String(16), nullable=False, server_default="instagram", index=True)
# Resolved canonical platform ID: YT channel ID ("UC..."), IG numeric pk (backfilled lazily).
# Resolved once on first scrape from the handle, then reused — handle renames don't orphan the row.
platform_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
```

- Change `handle` uniqueness: drop the plain unique constraint, add
  `UniqueConstraint("platform", "handle")` — `@mkbhd` can exist on both platforms.
- `InfluencerCreate`/`InfluencerOut`/`InfluencerDetailsUpdate` schemas gain
  `platform: Literal["instagram", "youtube"] = "instagram"`.
- YT handle normalization on create: accept `@name`, bare `name`, or a full channel URL;
  store the `@name` form (strip URL prefixes; prepend `@` if missing).

### 4.2 `posts`
```python
title:             Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
platform_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
```

### 4.3 `post_metrics_snapshots`
- `likes`, `comments`, `reposts` → nullable (NULL = "not publicly available", per §3.3).
  Existing IG code paths keep writing non-NULL values; no backfill needed.

### 4.4 `comments`
- `comment_id`, `parent_comment_id` → `String(128)`.
- Add `author_external_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)`.

### 4.5 `profile_snapshots`
```python
total_views:        Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
subscribers_hidden: Mapped[bool]          = mapped_column(Boolean, nullable=False, server_default="false")
platform_metadata:  Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
```

### 4.6 New table: `youtube_api_keys` (mirrors `instagram_accounts`' role)

```python
class YouTubeApiKey(Base):
    __tablename__ = "youtube_api_keys"
    id:               UUID pk
    label:            Mapped[str] = mapped_column(String(255), unique=True, nullable=False)  # human name, e.g. "gcp-project-1"
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet, same ACCOUNT_ENCRYPTION_KEY
    status:           Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
                      # "active" | "quota_exhausted" | "invalid" | "disabled"
    quota_used_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quota_reset_at:   Mapped[Optional[datetime]]  # next midnight US/Pacific — YouTube's reset boundary
    last_used_at / last_success_at / last_failure_at / failure_count / error_message / created_at / updated_at
    # NOTE: no lease/lock columns — API keys are safely shareable across concurrent
    # jobs (unlike IG sessions); the repo just picks the active key with the most
    # remaining quota. No proxy, no user_agent, no cookies.
```

Repo `app/repositories/youtube_api_key_repo.py`:
- `get_usable_key() -> YouTubeApiKey | None` — `status='active'`, ordered by
  `quota_used_today asc`; first lazily resets any key whose `quota_reset_at <= now()`
  (`quota_used_today=0`, `status='active' if status=='quota_exhausted'`).
- `add_usage(key_id, units: int)` — `UPDATE ... SET quota_used_today = quota_used_today + :units`
  (atomic increment, not read-modify-write).
- `mark_exhausted(key_id)` / `mark_invalid(key_id, message)`.
- `decrypt_key(row) -> str` — reuse `app/core/crypto.py` exactly as
  `InstagramAccountRepo.decrypt_cookies` does.

Registration script `scripts/register_youtube_api_key.py` (pattern:
`register_instagram_account.py`, minus Playwright): prompt for key (hidden input),
validate it with one live `channels.list?forHandle=@youtube` call, encrypt, insert.

---

## 5. New modules

```
app/scraper/youtube_client.py     # HTTP client: quota-aware, key-rotating
app/scraper/youtube_parser.py     # raw JSON -> Pydantic schemas
app/schemas/youtube.py            # YouTubeChannel, YouTubeVideo, YouTubeComment
app/workers/youtube_job_processor.py
app/models/youtube_api_key.py
app/repositories/youtube_api_key_repo.py
scripts/register_youtube_api_key.py
tests/test_youtube_parser.py, tests/test_youtube_client.py, tests/test_youtube_job_processor.py
```

### 5.1 `YouTubeClient` (`app/scraper/youtube_client.py`)

Plain `httpx.AsyncClient` (no curl_cffi, no proxies — official API). Constructor takes a
`key_provider` callback (the processor wires it to the repo) rather than a single key, so
mid-job rotation on quota exhaustion is possible.

```python
class YouTubeClient:
    BASE = "https://www.googleapis.com/youtube/v3"

    def __init__(self, key_provider, usage_recorder):
        # key_provider() -> (key_id, api_key) | raises NoUsableYouTubeKeyError
        # usage_recorder(key_id, units) -> None (fire-and-forget quota accounting)
        self._rate_limiter = TokenBucketRateLimiter(          # reuse the class from client.py —
            settings.YOUTUBE_RATE_LIMIT_RPS,                  # move it to app/scraper/rate_limit.py
            settings.YOUTUBE_RATE_LIMIT_BURST)                # and import from both clients
```

`_get(resource, params, quota_units=1)` loop (mirror `InstagramClient._get`'s
retry/backoff structure, `_BACKOFF_BASE_S`/`_BACKOFF_MAX_S` identical):

1. `await self._rate_limiter.acquire()`; fetch current `(key_id, key)`.
2. On HTTP 200 → record usage, return JSON.
3. **403 with `errors[0].reason == "quotaExceeded"` or `"dailyLimitExceeded"`** →
   `mark_exhausted(key_id)`, immediately re-fetch a new key and retry (does **not** count
   against `SCRAPER_MAX_RETRIES`; it counts against a separate "keys tried" cap = pool size).
   If no key remains → raise `ScraperRateLimitError(retry_after=seconds_until_midnight_pacific())` —
   the existing job retry machinery then parks the job exactly like an IG rate limit.
4. **400 `keyInvalid` / 403 `accessNotConfigured`** → `mark_invalid(key_id)`, rotate like (3).
5. **403 `commentsDisabled` / 404** → raise typed `YouTubeResourceGoneError(reason)` —
   callers decide (comments disabled = skip that video, channel 404 = `ScraperBlockedError`-style
   permanent fail with a clear message).
6. 429 / 5xx / network error → same exponential backoff + jitter as IG.

Endpoint methods (each documents its quota cost; **all list costs are 1 unit**):
```python
async def get_channel(handle_or_id) -> dict      # channels.list; forHandle=@x or id=UC...
async def get_uploads_page(uploads_playlist_id, page_token="") -> dict   # playlistItems.list, maxResults=50, part=contentDetails
async def get_videos(video_ids: list[str]) -> dict   # videos.list, comma-joined ≤50 ids — ONE unit for the whole batch
async def get_comment_threads(video_id, page_token="") -> dict  # commentThreads.list, maxResults=100, order=time
async def get_comment_replies(parent_id, page_token="") -> dict # comments.list, maxResults=100
```

### 5.2 `YouTubeParser` (`app/scraper/youtube_parser.py`)

Pure functions, defensive `.get(...) or default` style like `InstagramParser` (the API
omits keys rather than sending nulls — `statistics.likeCount` missing means hidden, so
**preserve None**, don't coerce to 0, for likes/comments; coerce for everything else).
All counts arrive as **strings** (`"12345"`) — `int(...)` everywhere.

```python
parse_channel(raw) -> YouTubeChannel          # incl. uploads_playlist_id = contentDetails.relatedPlaylists.uploads
parse_uploads_page(raw) -> (list[video_id], next_page_token, video_published_at_by_id)
parse_videos(raw) -> list[YouTubeVideo]       # duration ISO8601 -> seconds (regex PT(\d+H)?(\d+M)?(\d+S)?; also P#DT… for livestream archives)
parse_comment_threads(raw) -> (list[YouTubeComment], inline_replies: list[YouTubeComment], next_page_token)
parse_comment_replies(raw, parent_id) -> (list[YouTubeComment], next_page_token)
```

`YouTubeVideo.media_label` property: `"live"` if liveStreamingDetails present and not
ended-VOD-short, `"short"` if `duration_s <= 183`, else `"video"`.

### 5.3 `YouTubeJobProcessor` (`app/workers/youtube_job_processor.py`)

Copy the *structure* of `JobProcessor.process()` verbatim — heartbeat task, cancel event,
retry/outcome bookkeeping, `retry_pending` on "no usable key" (mirroring the
"no healthy Instagram accounts" branch, uncounted against retries). Differences only:

- Acquires a **key**, not a leased account (`get_usable_key()`; no release/lease renewal —
  drop the `renew_lease` call from the heartbeat, keep the job heartbeat + cancel check).
- `_run_scrape` phases:
  1. **Resolve channel**: if `influencer.platform_user_id` is set → `get_channel(id=...)`,
     else `get_channel(forHandle=handle)` and persist `platform_user_id = channel_id`.
     Empty `items` → raise (channel deleted/handle wrong) with a clear message.
     Write `ProfileSnapshot` (§3.1). Capture one `RawResponse(endpoint="yt_channels_list")`.
  2. **Discover videos**: paginate `get_uploads_page(uploads_playlist_id, cursor)`.
     Cursor/backfill semantics identical to IG: `backfill_cursor` stores `nextPageToken`;
     `scrape_posts_since` cutoff compares `contentDetails.videoPublishedAt`
     (**not** the playlist-add date). The uploads playlist is newest-first and has **no
     pinned-item exemption** — the IG pinned-post special case does not apply; when
     `backfill_completed` and a known video outside the comment window is reached, stop.
     One `RawResponse` for the first page only, same as IG.
     **Invalid/expired pageToken (400 `invalidPageToken`)**: clear `backfill_cursor`,
     restart from page 1 (idempotent thanks to the existing-post bulk lookup).
  3. **Hydrate**: collect the page's video IDs (playlistItems' contentDetails only carries
     id + publishedAt), call `get_videos(ids)` — one unit per 50. From the result build/
     update `Post` rows (bulk existing-lookup by `shortcode`, exactly the IG pattern),
     write `PostMetricsSnapshot` per video (`views` always, `likes`/`comments` None-safe,
     `reposts=None`), create `FeatureStore` for new posts
     (`media_type=video.media_label`, `reel_duration_s=video.duration_s`).
  4. **Comment sync**: same `sync_candidates` selection — new posts in window + known
     posts whose latest snapshot `comments` differs (treat NULL prev as changed). Same
     `asyncio.Semaphore(settings.COMMENT_SYNC_CONCURRENCY)` + per-task session. Per post:
     page `get_comment_threads`; upsert top-level comments *and* the ≤5 inline replies in
     the same bulk upsert; only when `totalReplyCount > inline replies count` **and**
     `totalReplyCount != stored child_comment_count` page `get_comment_replies`.
     `commentsDisabled` → log, return 0, don't fail the job.
     Reuse `MAX_COMMENT_PAGES`/`MAX_REPLY_PAGES` caps and `_upsert_comments_bulk`
     (works unchanged once `comment_id` is widened; add `author_external_id` to its
     update-columns list). `is_from_creator = author_channel_id == influencer.platform_user_id`.
  5. `_update_engagement_timing_features` — call the existing method unchanged (extract
     it and `_upsert_comments_bulk`/`_comment_row`/`_last_comment_count` into a shared
     `app/workers/comment_sync.py` mixin/helpers module rather than copy-pasting;
     parameterize `_comment_row`'s is_from_creator check with a predicate).

### 5.4 Routing (queue → worker)

- `ScrapeJobMessage` gains `platform: str = "instagram"` (default keeps in-flight
  messages during deploy decodable).
- `DispatchService.dispatch_scrape_job` passes `influencer.platform` into the message.
- `worker_runner._run_one`:
  ```python
  processor = YouTubeJobProcessor(msg) if msg.platform == "youtube" else JobProcessor(msg)
  await processor.process()
  ```
- Scheduler (`run_daily_scrapes`, retry loops) is platform-agnostic already — it
  dispatches by influencer id. **No changes.**

### 5.5 Config additions (`app/core/config.py`)

```python
# ── YouTube ──────────────────────────────────────────────────────────────
YOUTUBE_RATE_LIMIT_RPS: float = 5.0    # official API: generous; this is politeness + burst smoothing
YOUTUBE_RATE_LIMIT_BURST: int = 5
YOUTUBE_DAILY_QUOTA_PER_KEY: int = 10000
YOUTUBE_QUOTA_SOFT_STOP: int = 200     # stop picking a key when remaining quota < this,
                                       # so a job never strands mid-scrape on a dry key
```

`COMMENT_SYNC_WINDOW_DAYS`, `MAX_POSTS_PER_SCRAPE`, `COMMENT_SYNC_CONCURRENCY`,
`SCRAPER_MAX_RETRIES` are shared knobs — reuse, don't duplicate.

---

## 6. Failure-mode matrix (implement exactly)

| Condition | Detection | Handling |
|---|---|---|
| Daily quota exhausted (one key) | 403 `quotaExceeded` | mark key exhausted, rotate to next key mid-request, transparent to job |
| All keys exhausted | rotation finds none | `ScraperRateLimitError(retry_after=until midnight PT)` → job `retry_pending`, account-less |
| No keys registered | `get_usable_key() is None` at job start | `retry_pending`, uncounted (mirror "no healthy accounts" branch) |
| Key revoked/invalid | 400 `keyInvalid`, 403 `accessNotConfigured` | mark `invalid` + error_message, rotate |
| Channel deleted / handle typo | channels.list empty `items` | job fails with explicit message (counted retry — mirrors IG blocked semantics) |
| Video deleted mid-backfill | videos.list returns fewer items than ids asked | skip silently (id simply absent from response) |
| Comments disabled on a video | 403 `commentsDisabled` | skip that video's comment sync, log, continue |
| Expired backfill pageToken | 400 `invalidPageToken` | clear cursor, restart discovery from page 1 |
| 429 / 5xx / network stall | status / exception | existing exponential backoff + jitter, `SCRAPER_MAX_RETRIES` |
| Cancellation | `cancel_requested_at` via heartbeat | identical cooperative unwind (`JobCancelledError`) |
| Worker killed | heartbeat stops | existing `reap_stale_jobs` — nothing YT-specific (no lease to reap) |

---

## 7. Implementation order (each step leaves the system green)

1. **Migration + models**: §4 columns/table; update `app/models/__init__.py`; run IG test
   suite — nothing behavioral changes (new columns nullable/defaulted; nullable metrics
   columns require touching `_record_metrics_snapshot` not at all — it always passes values).
2. **Schemas + parser** (`schemas/youtube.py`, `youtube_parser.py`) with unit tests using
   captured fixture JSON (store fixtures under `tests/fixtures/youtube/*.json` — hand-build
   from the API reference examples; include: hidden likeCount, disabled comments,
   hiddenSubscriberCount, a >5-reply thread, a Short, a livestream VOD, string counts).
3. **Key pool**: model, repo, registration script, encryption round-trip test.
4. **Client** with a mocked transport: quota rotation, all-exhausted, invalid-key,
   backoff paths.
5. **Processor + routing + dispatch**: extract shared comment-sync helpers from
   `JobProcessor` first (pure refactor, IG tests must stay green), then build
   `YouTubeJobProcessor` on top; wire `worker_runner` + `ScrapeJobMessage.platform`.
6. **API/schema surface**: `platform` in influencer create/read endpoints + dashboard list.
7. **End-to-end verify** (manual, real key): register key, create a small real channel as
   influencer (e.g. a channel with <100 videos), `POST /api/v1/admin/scrape`, then check:
   profile snapshot row, posts count == channel videoCount (within window), metrics
   snapshots with NULL reposts, comments incl. a reply thread, feature_store rows with
   `media_type in ('video','short')` and `reel_duration_s` set, `RawResponse` rows, and a
   second run produces *zero* comment requests for unchanged videos (log inspection).

## 8. Explicitly out of scope / known accuracy limits (document in README)

- Subscriber counts are API-rounded to 3 significant figures (YouTube-wide limitation).
- No dislikes, no share counts, no save counts (not public) — stored as NULL, never 0.
- Verification badge, channel bio links, creator-hearted comments: not exposed by Data API.
- Shorts classification is a duration heuristic (≤183s); revisit only if benchmarks need
  more precision (a `HEAD https://youtube.com/shorts/{id}` redirect check is the known
  upgrade path, but it leaves the official-API-only posture).
- `topicCategories` are coarse Wikipedia topics, not the creator-picked upload category
  name (that would cost a `videoCategories.list` join — do it lazily if benchmarks want it).
