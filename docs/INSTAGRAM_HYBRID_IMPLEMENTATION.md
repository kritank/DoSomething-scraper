# Instagram Hybrid Pipeline — Detailed Implementation Plan

Companion to `docs/INSTAGRAM_GRAPH_API_PLAN.md` (the design spec — read it
first for the why, the source-of-truth matrix, and rate-limit semantics).
This document is the execution plan: per-PR, per-file tasks with exact
signatures, migrations, tests, and acceptance criteria. File references were
verified against the codebase on 2026-07-18 (branch
`feat/combined-creator-view`).

**Ground rule for the implementer:** the Graph API pipeline is a structural
clone of the YouTube pipeline. When this doc says "mirror X", open X and copy
its shape — locking, error taxonomy, test style — rather than inventing new
patterns.

---

## Phase 0 — Prerequisites (HUMAN, blocks everything)

Owner: Kritank. See design doc §3 for step-by-step. Deliverables:

- [ ] Meta app created (Business type, Instagram product, Development mode)
- [ ] IG professional "reader" account (+ linked FB Page if Facebook-Login flavor)
- [ ] Long-lived access token + IG User ID + App ID + App Secret handed over
      via the encrypted-secrets path
- [ ] Sanity curl (design doc §3.6) returns `followers_count`
- [ ] **Fixture captured:** one full Business Discovery response for a real
      account with >25 posts including reels and a carousel — profile fields
      + media page 1 + media page 2 (using the `after` cursor), token
      scrubbed. Save as
      `tests/fixtures/instagram_graph/business_discovery_page1.json` and
      `..._page2.json`. Also capture one error response for a personal
      account (e.g. a friend's) → `..._not_professional_error.json`, and
      one for a nonexistent username → `..._not_found_error.json`.

### Phase 0.5 — Doc verification (implementer, ~30 min, before PR 1)

Check current Meta docs and record answers at the top of PR 1's description:

- [ ] Current Graph API version (plan assumes `v23.0`)
- [ ] Is `business_discovery` supported on the Instagram-Login flavor, or
      Facebook-Login only? (Determines which flavor Phase 0 uses.)
- [ ] Is `is_verified` a valid `business_discovery` field? If not, drop it
      from the field list (keep last-known value in DB).
- [ ] Max `media.limit()` page size for business_discovery (clamp
      `INSTAGRAM_GRAPH_MEDIA_PAGE_SIZE` to it)
- [ ] Are `children{...}` and `media_url` returned for third-party media?
      (Some CDN-URL fields are omitted on copyright-flagged media — parser
      must treat all of them as optional.)
- [ ] Exact error `code`/`error_subcode` for "target is not a professional
      account" (plan assumes 100/2108006 — confirm against the Phase 0
      fixture, which is authoritative over docs)

---

## Conventions used below

- "clone of X" = copy X's structure, adapt names/fields; keep comment
  density and style of the original.
- All new secrets encrypted with the existing Fernet helper used by
  `YouTubeApiKeyRepo.create` (`app/repositories/youtube_api_key_repo.py:43`).
- Every PR lands with `pytest` green and an Alembic migration that
  upgrades AND downgrades cleanly.

---

## PR 1 — API foundation (no behavior change; nothing wired to workers)

### 1.1 Model: `app/models/instagram_api_token.py`

Clone `app/models/youtube_api_key.py`. Table `instagram_api_tokens`:

```
id UUID pk · label str(255) unique · access_token_encrypted Text
ig_user_id str(64) · app_id str(64) · app_secret_encrypted Text
auth_flavor str(16) ("facebook_login"|"instagram_login")
token_expires_at DateTime(tz) nullable
status str(32) default "active" index  ("active"|"cooldown"|"invalid")
calls_today int default 0 · cooldown_until DateTime(tz) nullable
buc_usage_pct float nullable
last_used_at / last_success_at / last_failure_at DateTime(tz) nullable
failure_count int default 0 · error_message Text nullable
created_at / updated_at (server defaults, as youtube_api_keys)
```

Register in `app/models/__init__.py`.

### 1.2 Migration A

Single Alembic revision adding:
- `instagram_api_tokens` (above)
- `influencers.api_supported BOOLEAN NULL` (no default — null means untried)
- `posts.media_url TEXT NULL`, `posts.thumbnail_url TEXT NULL`
- `scrape_jobs.job_type VARCHAR(16) NOT NULL DEFAULT 'scrape'`
  (values: `scrape` | `enrich`; needed by PR 3 but ship the column now so
  there's exactly one migration touching `scrape_jobs`)
- `scrape_jobs.instagram_api_token_id UUID NULL REFERENCES
  instagram_api_tokens(id)` — mirrors the existing
  `youtube_api_key_id` attribution column (`app/models/scrape_job.py:70`)

### 1.3 Repo: `app/repositories/instagram_api_token_repo.py`

Clone `YouTubeApiKeyRepo` method-for-method:

```python
class InstagramApiTokenRepo:
    async def get_all() -> list[InstagramApiToken]
    async def get_by_id(token_id) -> InstagramApiToken
    async def create(label, access_token, ig_user_id, app_id, app_secret,
                     auth_flavor, token_expires_at) -> InstagramApiToken
    def decrypt_token(tok) -> str
    def decrypt_app_secret(tok) -> str
    async def get_usable_token() -> Optional[InstagramApiToken]
    async def add_usage(token_id, calls: int, buc_pct: float | None) -> None
    async def mark_exhausted(token_id, cooldown_until: datetime) -> None
    async def mark_invalid(token_id, detail: str) -> None
    async def update_token(token_id, access_token, token_expires_at) -> None  # refresh job
    async def update_status(token_id, status) -> InstagramApiToken
    async def delete(token_id) -> None
```

Differences from YouTube worth care:
- **No midnight-Pacific reset.** `_reset_if_due` analog: a token in
  `cooldown` with `cooldown_until <= now` flips back to `active` inside
  `get_usable_token` (BUC is a rolling 24h window; see design doc §5).
- `mark_exhausted` takes an explicit `cooldown_until` (client computes
  `now + 1h`).
- `calls_today` resets at UTC midnight (bookkeeping only, not quota logic).

### 1.4 Exceptions: `app/core/exceptions.py`

Add `InstagramAccountNotProfessionalError(Exception)` (carries `username`)
and `NoUsableInstagramTokenError(Exception)` — mirror
`NoUsableYouTubeKeyError`'s shape.

### 1.5 Client: `app/scraper/instagram_graph_client.py`

Clone the skeleton of `app/scraper/youtube_client.py` (provider callbacks,
`_ROTATE` sentinel, `_request_with_key` retry loop, `_MAX_KEY_ROTATIONS`
analog). Full spec in design doc §5. Deltas from the YouTube client:

- `httpx.AsyncClient(timeout=settings.SCRAPER_TIMEOUT_S)` — plain TLS is fine.
- Provider signatures (token pool):
  ```python
  TokenProvider    = Callable[[], Awaitable[tuple[UUID, str, str]]]  # (id, token, ig_user_id)
  UsageRecorder    = Callable[[UUID, int, float | None], Awaitable[None]]
  TokenExhauster   = Callable[[UUID, datetime], Awaitable[None]]
  TokenInvalidator = Callable[[UUID, str], Awaitable[None]]
  ```
- Error classification (from JSON body `error` object):
  - `code in {4, 17, 32, 613}` or `code == 80004` in message → `_ROTATE`
    (call TokenExhauster with `now + 1h` first)
  - `code == 190` → TokenInvalidator, `_ROTATE`
  - "not professional account" signature (per Phase 0.5) →
    `InstagramAccountNotProfessionalError`
  - `code == 100` + "does not exist"/error 110 → `InfluencerNotFoundError`
  - 5xx / network / timeout → backoff retry against same token
    (`SCRAPER_MAX_RETRIES`, `_BACKOFF_BASE_S=5.0`, `_BACKOFF_MAX_S=120.0`)
- `X-Business-Use-Case-Usage` header: JSON — take max pct across all
  entries/metrics; pass to UsageRecorder on every response; if ≥ 95,
  proactively exhaust the token after recording.
- Public API:
  ```python
  async def get_business_profile(self, username: str) -> dict[str, Any]
  async def get_business_media(self, username: str, after: str) -> dict[str, Any]
  async def close(self) -> None
  ```
  Field lists exactly as design doc §1's example query (minus anything
  Phase 0.5 disproved). `get_business_media` requests ONLY the `media`
  subfield with `.after()` — no profile re-fetch.

### 1.6 Parser: `app/scraper/instagram_graph_parser.py`

Pure functions, no I/O (mirror `youtube_parser.py`):

```python
def parse_profile(payload: dict) -> InstagramUser
def parse_media_items(payload: dict) -> list[InstagramMediaItem]
def extract_media_cursor(payload: dict) -> str   # "" when no more pages
```

Mapping table: design doc §6. Specifics:
- shortcode: last path segment of `permalink`
  (`https://www.instagram.com/{p|reel}/{shortcode}/`)
- `taken_at`: ISO8601 `timestamp` → epoch seconds (int)
- `like_count`: **preserve null** (hidden likes) — requires
  `InstagramMediaItem.like_count` to become `Optional[int]` (see 1.7)
- `is_reel` / `product_type`: `media_product_type == "REELS"` →
  `product_type="clips"` to match what the cookie parser's feed items carry,
  so downstream reels classification is source-agnostic (verify the cookie
  value is `"clips"` by grepping existing data/code; else match whatever
  the dashboard's posts-vs-reels split keys on)
- `media_type`: map `IMAGE→1, VIDEO→2, CAROUSEL_ALBUM→8` (cookie numeric
  convention already in `InstagramMediaItem.media_type`)
- new optional fields: `media_url`, `thumbnail_url`, `children`
  (list of `{media_type, media_url, thumbnail_url}`) — all may be absent
- `play_count`/`view_count`: leave at parser default (0/None) — enrichment
  owns these; make sure the processor does NOT overwrite an existing
  non-null snapshot view count with the API's absence (see 2.1)

### 1.7 Schema tweaks: `app/schemas/instagram.py`

- `InstagramMediaItem`: `like_count: Optional[int]` (was int), add
  `media_url: Optional[str]`, `thumbnail_url: Optional[str]`,
  `children: Optional[list[dict]]`, `permalink: Optional[str]`.
- `InstagramUser`: no changes (API-absent fields already have defaults).
- Audit uses of `like_count` for null-safety (`grep -rn "like_count"`).

### 1.8 Config: `app/core/config.py`

Next to the `YOUTUBE_*` block (~line 128):

```python
INSTAGRAM_BACKEND: str = "cookies"            # "cookies" | "hybrid"
INSTAGRAM_GRAPH_API_VERSION: str = "v23.0"    # from Phase 0.5
INSTAGRAM_GRAPH_RATE_PER_HOUR: int = 150
INSTAGRAM_GRAPH_MEDIA_PAGE_SIZE: int = 25     # clamp per Phase 0.5
INSTAGRAM_ENRICH_EVERY_N_CYCLES: int = 1
INSTAGRAM_ENRICH_FEED_PAGES: int = 2
```

### 1.9 Register script: `scripts/register_instagram_api_token.py`

Clone `scripts/register_youtube_api_key.py`. Prompts label / flavor /
app_id / app_secret / token. Validation call = live
`get_business_profile("instagram")`; on success it also resolves and stores
`ig_user_id` (flavor 1: `GET /me/accounts` → page →
`instagram_business_account`; flavor 2: `GET /me?fields=user_id` — verify
exact shape at build) and `token_expires_at` via `GET /debug_token`.

### 1.10 PR 1 tests (all unit, fixture-driven)

- `tests/unit/test_instagram_graph_parser.py` — against Phase 0 fixtures:
  profile fields, media mapping incl. reel/carousel/hidden-likes-null,
  cursor extraction, page-2 parse, absent `media_url` tolerated.
- `tests/unit/test_instagram_graph_client.py` — clone structure of
  `test_youtube_client.py` (mock transport): success; 5xx retry+backoff;
  rate-limit code → exhaust+rotate; 190 → invalidate+rotate; all tokens
  spent → `ScraperRateLimitError(retry_after≈1h)`; not-professional error →
  typed exception, **no** rotation/retry; BUC header ≥95 → proactive
  exhaust; rotation cap respected.
- `tests/unit/test_instagram_api_token_repo.py` — clone
  `test_youtube_api_key_repo.py`: round-robin by `last_used_at`, cooldown
  expiry auto-reactivation, mark_invalid excluded from `get_usable_token`,
  encryption round-trip.

**Acceptance:** new modules import nowhere in worker/scheduler code;
`alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
clean; full test suite green.

---

## PR 2 — API pipeline (runs standalone behind the flag)

### 2.1 Processor: `app/workers/instagram_graph_job_processor.py`

Clone the flow of `app/workers/youtube_job_processor.py` (heartbeat via
`job_common`, cancellation checks, finalization, `raw_response` archiving if
the YouTube processor does it — match it). Steps:

1. Load job + influencer; heartbeat task.
2. `get_business_profile(handle)` → `parse_profile` + first media page.
3. Paginate `get_business_media` until the existing per-scrape post cap
   (grep the cap the cookie `JobProcessor._run_scrape` uses; reuse the same
   setting) or cursor exhausted.
4. Upsert influencer: `platform_user_id` (set-once semantics, as cookie path),
   `profile_pic_url`, `api_supported=True`.
5. Upsert posts by `shortcode` (existing unique constraint): caption,
   posted_at, permalink, media_pk, product_type, **media_url,
   thumbnail_url**, `platform_metadata["children"]`. **Never write
   play/view/cookie-only columns — don't clobber enrichment's data.**
6. Record `ProfileSnapshot` (API-known fields; `is_professional_account=True`
   by definition of the endpoint; leave cookie-only fields at defaults) and
   `PostMetricsSnapshot` rows (likes nullable, comments; **do not touch view
   fields** — see PostMetricsSnapshot columns before writing: null them, not 0,
   for platform="instagram" API-sourced rows).
7. Set `scrape_jobs.instagram_api_token_id` for attribution (token id is
   known via the provider callback — mirror how the YouTube processor
   records `youtube_api_key_id`).
8. Finalize success. **If `settings.INSTAGRAM_BACKEND == "hybrid"` → enqueue
   enrich follow-on (wired in PR 3; in PR 2 leave a no-op hook).**

Error handling:
- `InstagramAccountNotProfessionalError` → set `api_supported=False`, mark
  job failed with explicit `error_message`, **and dispatch a legacy cookie
  scrape job for the same influencer** so the cycle isn't lost (use
  `DispatchService`; guard against infinite loops — the legacy job must not
  re-dispatch an API job).
- `ScraperRateLimitError` / `NoUsableInstagramTokenError` → same
  fail/retry-later semantics the YouTube processor uses.

### 2.2 Provider: `app/workers/instagram_token_provider.py`

Clone `app/workers/youtube_key_provider.py` (session-per-call pattern):
`provide_token() -> (UUID, str, str)`, `record_usage(id, calls, buc_pct)`,
`mark_exhausted(id, until)`, `mark_invalid(id, detail)`. Raise
`NoUsableInstagramTokenError` when pool is empty.

### 2.3 Routing: `app/workers/worker_runner.py:27` and queue message

- `ScrapeJobMessage` (`app/queue/base.py`): add
  `job_type: str = "scrape"` (defaulted → in-flight messages decode).
- `_run_one` routing table:

```python
if msg.platform == "youtube":                 YouTubeJobProcessor
elif msg.job_type == "enrich":                InstagramEnrichProcessor   # PR 3
elif settings.INSTAGRAM_BACKEND == "hybrid" and influencer.api_supported is not False:
                                              InstagramGraphJobProcessor
else:                                         JobProcessor               # legacy cookies
```

The `api_supported` check needs the influencer row; do the lookup inside the
processor selection (one indexed PK read) or — simpler and race-free —
have `DispatchService` stamp the decision into the message
(`backend: "graph" | "cookies"`) at enqueue time and route purely on the
message. **Choose the message-stamp approach**; it keeps `_run_one` DB-free.

### 2.4 Dispatch: `app/services/dispatch_service.py`

`dispatch_scrape_job` decides backend at enqueue time
(platform=="instagram" and `INSTAGRAM_BACKEND=="hybrid"` and
`api_supported is not False` → `backend="graph"`). Add
`dispatch_enrich_job(influencer_id)` (creates `scrape_jobs` row with
`job_type="enrich"`, enqueues message with `job_type="enrich"`) — used from
PR 3; harmless to land now.

### 2.5 Token refresh: `app/scheduler/runner.py`

New coroutine `refresh_instagram_tokens()` scheduled daily alongside
`snapshot_credential_health` (mirror its registration in `main()`):
- flavor `instagram_login` & `token_expires_at < now+10d` →
  `GET https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token`
  → `repo.update_token(...)`
- refresh failure or any token with `token_expires_at < now+3d` → alert via
  existing `alerts_service` pattern
- flavor `facebook_login`: skip.

### 2.6 Health snapshot

Extend `snapshot_credential_health` / `credential_health_repo` to include
API-token pool state (count active/cooldown/invalid, max `buc_usage_pct`,
soonest `token_expires_at`). Follow whatever shape it already stores for
cookie accounts + YouTube keys.

### 2.7 PR 2 tests

- `tests/unit/test_instagram_graph_job_processor.py` — clone structure of
  `test_youtube_job_processor.py`: happy path persists profile+posts+
  snapshots with nulled view fields; pagination stops at cap;
  not-professional → `api_supported=False` + legacy job dispatched exactly
  once; token-pool-empty → retryable failure; API job never writes
  `play_count`/cookie-only columns.
- `tests/unit/test_dispatch_service.py` — extend: backend stamping matrix
  (flag × api_supported), enrich dispatch creates `job_type="enrich"`.
- `tests/unit/test_run_daily_scrapes.py` — unchanged behavior under
  `INSTAGRAM_BACKEND="cookies"` (regression).
- Refresh job unit test: refreshes only due `instagram_login` tokens; alert
  on failure.

**Acceptance:** with `INSTAGRAM_BACKEND="cookies"` (default) production
behavior is byte-identical. In a dev env with `"hybrid"` + a registered
token, a manually dispatched job scrapes a real professional account
end-to-end (profile row, ≥25 posts, snapshots) with zero cookie-client calls.

---

## PR 3 — Enrichment + fallback (the hybrid becomes whole)

### 3.1 Shared comment sync

`JobProcessor._sync_comments_for_post` / `_sync_replies` /
`_normalize_comment` (`app/workers/job_processor.py:527–579`) move to
module-level functions in `app/workers/comment_sync.py` (which already holds
the pure helpers), parameterized on `(session, client: InstagramClient,
post)`. `JobProcessor` delegates to them — no behavior change, covered by
existing tests.

### 3.2 Processor: `app/workers/instagram_enrich_processor.py`

Handles `job_type="enrich"`. Uses the **cookie** account pool exactly as
`JobProcessor` does (account lease, `InstagramClient.from_account`, lease
release — copy that lifecycle, including `instagram_account_id` job
attribution).

1. `get_user_feed(handle)` up to `INSTAGRAM_ENRICH_FEED_PAGES` pages
   (**no `get_user_info` call**).
2. `InstagramParser.parse_feed` → for each item, match `Post` by
   `code`→`shortcode`. Unmatched items (posted since the API scrape):
   skip — next API cycle picks them up; log count.
   If `posts.media_pk` set and ≠ cookie `pk`: log warning, still update
   (shortcode is the authority).
3. Update matched posts' cookie-only columns (`reshare_count` → snapshot,
   `is_paid_partnership`, `music_metadata`, `locations`,
   `coauthor_producers`, `tagged_usernames`, `accessibility_caption`,
   `is_pinned`, `counts_disabled`).
4. **In-place snapshot merge:** for each matched post, find today's
   `PostMetricsSnapshot` (post_id + `scraped_at == current_date`); update
   its view/play fields (and `reshare_count`) if found, else insert a full
   row from the cookie item. Never insert a second same-day row —
   enforce with a unit test.
5. Comment sync via the 3.1 shared functions (unchanged flow, including
   `update_engagement_timing_features`).
6. Finalize. Failure semantics: any cookie-side failure (pool empty,
   rate-limit, checkpoint) fails **this job only** with its normal
   retry path; it must not touch the parent scrape job. No new "partial"
   status needed — the enrich job's own status is the partial signal;
   surface "enrich lag" in the dashboard instead (§4.3).

### 3.3 Wiring

- `InstagramGraphJobProcessor` success hook (2.1 step 8) →
  `dispatch_enrich_job`, honoring `INSTAGRAM_ENRICH_EVERY_N_CYCLES`
  (cycle counter: days-since-epoch % N == 0, or a per-influencer counter in
  `scheduler_metadata` — pick the simpler days-modulo).
- `worker_runner` routes `job_type=="enrich"` → `InstagramEnrichProcessor`.
- `retry_failed_scrapes` (`app/scheduler/runner.py:82`): confirm it treats
  enrich jobs like scrape jobs (it should — same table); ensure the
  not-professional permanent failure is excluded from retry (match on
  error_message or add it to whatever permanent-failure convention that
  function already uses).

### 3.4 PR 3 tests

- Enrich processor: views merged into existing same-day snapshot (no dup
  row); insert path when no same-day row; unmatched feed item skipped;
  cookie failure leaves API data intact + parent job untouched; comment
  sync invoked; account lease released on failure.
- Refactor guard: existing `JobProcessor` comment tests still green after
  3.1 extraction.
- Every-N-cycles gating test.

**Acceptance:** dev env, `"hybrid"`: dispatch API scrape → enrich follows
automatically → posts have API likes/comments AND cookie views AND comment
text; snapshot table has exactly one row per post per day.

---

## PR 4 — Cutover

1. Register the production token (`scripts/register_instagram_api_token.py`).
2. Staging/dev soak: run `scripts/seed_and_scrape.py` over ~10 real tracked
   influencers under `"hybrid"`. Produce a comparison (scratch script is
   fine, doesn't need to land): per influencer, followers delta vs last
   cookie snapshot (<2% drift expected), % of cookie-era posts matched by
   shortcode (expect ~100% of recent), views populated within one enrich
   cycle, one personal account exercising the fallback.
3. Flip default `INSTAGRAM_BACKEND: str = "hybrid"` in config.
4. Dashboard: token-pool health panel (buc %, cooldowns, expiry) next to
   YouTube keys; influencer list shows `api_supported=false` badge; alert
   when a post's like-snapshot is ≥2 cycles newer than its view-snapshot
   (enrich lag).
5. Run the full verification checklist in design doc §12 and paste it,
   checked, into the PR description.

Rollback = set `INSTAGRAM_BACKEND=cookies` (env var, no deploy).

---

## PR 5 — Slimming (after ≥1 week of stable hybrid)

- Delete dead cookie-path code the enrich/fallback flow doesn't reach
  (candidates only — verify call graphs first): profile-info handling in
  the legacy processor is still needed for the fallback path, so most of
  `client.py` stays; the real wins are ops-side: shrink proxy count,
  reduce cookie-account pool, lower legacy rate budgets.
- Reduce `INSTAGRAM_ENRICH_FEED_PAGES`/frequency if view-freshness allows.
- Update `README.md` + `docs/CREATOR_STATS_V2_PLAN.md` references to the
  cookie scraper being primary.

---

## Task tracker

| # | Task | PR | Depends on | Status |
|---|---|---|---|---|
| 0.1 | Meta app + token + fixtures | — | Kritank | ☐ |
| 0.2 | Doc verification answers | — | 0.1 helps | ☐ |
| 1.1–1.2 | Token model + migration A | 1 | — | ☐ |
| 1.3 | Token repo | 1 | 1.1 | ☐ |
| 1.4–1.6 | Exceptions, client, parser | 1 | 0.1 fixtures | ☐ |
| 1.7–1.9 | Schema/config/register script | 1 | 1.3, 1.5 | ☐ |
| 1.10 | PR 1 tests | 1 | above | ☐ |
| 2.1–2.2 | Graph processor + provider | 2 | PR 1 | ☐ |
| 2.3–2.4 | Message/job_type routing + dispatch | 2 | PR 1 | ☐ |
| 2.5–2.6 | Token refresh + health snapshot | 2 | 1.3 | ☐ |
| 2.7 | PR 2 tests | 2 | above | ☐ |
| 3.1 | Comment-sync extraction | 3 | — | ☐ |
| 3.2–3.3 | Enrich processor + wiring | 3 | PR 2, 3.1 | ☐ |
| 3.4 | PR 3 tests | 3 | above | ☐ |
| 4.x | Soak, flip, dashboard, checklist | 4 | PR 3, token registered | ☐ |
| 5.x | Slimming | 5 | 1 week stable | ☐ |
