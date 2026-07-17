# Creator Stats v2 — format split, daily history, about, key events, UI polish

Builds on the shipped v1 (`docs/CREATOR_STATS_PLAN.md`, PR #3): the CreatorProfile
page at `/influencers/:influencerId`, `CreatorStatsService`, and the three
`/influencers/{id}/stats|growth|posts/performance` endpoints all exist and work.
Reference for look/feel and scope: https://vidiq.com/youtube-stats/channel/@5minutecraftsyoutube/

Required features (from the user, all must ship):
1. **Long-form vs Shorts split** (YouTube) / **Posts vs Reels** (Instagram), with a
   filter on the content list.
2. **Daily subscriber growth & view history** — vidiq-style daily-delta charts.
3. **About section** — channel/account description, links, topics, metadata.
4. **Views / subscribers / estimated-earnings graphs with key events plotted** on them.
5. **UI banners + tooltips explaining every metric**; overall clean, functional, polished.

**No scraper or migration changes are needed for any of this.** Verified against the
live schema and real local data:
- YouTube `posts.product_type` is already `"video" | "short" | "live"` — classified at
  scrape time by `YouTubeVideo.media_label` (`app/schemas/youtube.py`, ≤183s heuristic).
- Instagram `posts.product_type` is `"clips"` (= Reels) vs `"feed"`,
  `"carousel_container"`, `"igtv"`, or NULL (= Posts).
- About data all lives in the latest `ProfileSnapshot` (biography, external_url,
  bio_links, business fields, is_verified) + its `platform_metadata` JSONB (YT country,
  published_at, keywords, topic_categories, made_for_kids) + `Influencer`.
- Daily history comes from `profile_snapshots` (one row/day, already deduped by v1's
  `get_growth_series`).

Conventions to preserve (from v1 — read `app/analytics/creator_stats.py` first):
- NULL means "not computable", never a fabricated 0.
- `views == 0` on Instagram photo posts means "no view metric", treat like NULL.
- Same-day duplicate snapshots are deduped by `created_at DESC`.
- Rankings/copy always say "tracked", never imply a global rank.

---

## Phase A — Backend: content-format split

### A1. Format classifier — `app/analytics/creator_stats.py`

Module-level pure function (unit-testable, no DB):

```python
def content_format(platform: str, product_type: str | None) -> str:
    """'short_form' | 'long_form' | 'live'.
    YouTube: product_type is already media_label ('video'|'short'|'live').
    Instagram: 'clips' is a Reel; everything else ('feed',
    'carousel_container', 'igtv', None) is a regular post."""
```
- youtube: `"short"` → short_form, `"live"` → live, else long_form.
- instagram: `"clips"` → short_form, else long_form (igtv is long video — long_form).

### A2. Format breakdown — new service method

`async def get_format_breakdown(influencer_id, days) -> FormatBreakdownOut`
- Posts with `posted_at` in the window, joined to each post's **latest**
  `PostMetricsSnapshot` (reuse v1's `latest_metric` row_number subquery pattern).
- Per format (`long_form`, `short_form`; fold `live` into long_form for display):
  `post_count`, `total_views`, `total_likes`, `total_comments`, `avg_views`
  (NULL-safe: posts with no usable view/like metric are excluded from avg, and
  Instagram falls back to likes where views are 0/NULL — same rule as v1 outliers).
- Also return each format's `views_share` (0..1 of the window total) for the split bar.

### A3. Format filter on the posts list

- `get_post_performance(..., format: str | None)` — SQL-side filter. Map the filter to
  product_type sets via `content_format` logic (`short_form` → youtube `('short',)` /
  instagram `('clips',)`, etc.). Keep outlier medians computed over ALL formats
  (comparing a Short against the channel's overall median is what vidiq's outlier
  does) — filter only which rows are returned.
- Each returned `PostPerformance` gains a `format` field so the UI can badge rows.

### A4. API + schemas

- `app/schemas/creator_stats.py`: `FormatBreakdownOut { window_days, formats:
  [FormatStats], total_views }`, `FormatStats { format, post_count, total_views,
  total_likes, total_comments, avg_views, views_share }`; add `format: str` to
  `PostPerformance`.
- `app/api/v1/creator_stats.py`:
  - `GET /influencers/{id}/formats?days=28` (days ∈ 7|28|90|365|3650).
  - `posts/performance` gains `format=all|long_form|short_form` query param
    (default all).

### A5. Tests — `tests/unit/test_creator_stats_scoring.py` (extend)

`content_format` for every product_type value seen in prod data
(`video, short, live, clips, feed, carousel_container, igtv, None`).

---

## Phase B — Backend: daily history, earnings series, key events

### B1. Daily history (extends v1 `get_growth_series`)

The v1 series already returns `(date, value, daily_delta)` deduped per day — that IS
the "Daily Subscriber Growth" data. Add:
- `metric="earnings"` (derived, YouTube only): for each day, `daily_views_delta ×
  RPM_range / 1000` using `app/analytics/earnings.py`'s country RPM table. Return
  `value_low`/`value_high` for this metric (a band, not a line). For Instagram return
  an empty series (earnings basis is per-post, not time-based — the UI hides the tab).
- `GrowthPoint` gains optional `value_low`/`value_high` (NULL except for earnings).

### B2. Key events — new service method

`async def get_key_events(influencer_id, days) -> list[KeyEvent]`
Two event types, both derived (no new tables):
1. `"top_post"` — the window's top-N posts by latest views/likes (N=8 max, and only
   posts whose outlier score ≥ 2 if at least 3 such exist, else top 3 by views):
   `{date: posted_at.date, type: "top_post", label: title (truncated 60ch),
   post_id, permalink, metric_value: views_or_likes}`.
2. `"milestone"` — follower round-number crossings found by scanning consecutive
   daily snapshots: thresholds at 1e4, 5e4, 1e5, 5e5, every 1e6. Label like
   "Crossed 21M followers". Uses the same deduped daily series as B1.

### B3. About payload — extend the `/stats` composite

New `AboutOut` on `CreatorStatsOut` (one fetch keeps the page simple):
```
AboutOut {
  description: str | None          # ProfileSnapshot.biography
  external_url: str | None         # IG external_url / YT custom_url (prefix https://youtube.com/ for YT)
  bio_links: list[str]             # IG bio_links (extract url fields); [] for YT
  country: str | None              # platform_metadata.country (YT)
  created_at_platform: str | None  # platform_metadata.published_at (YT); None IG
  topics: list[str]                # YT topic_categories -> last URL path segment, de-underscored ("Lifestyle_(sociology)" -> "Lifestyle (sociology)")
  keywords: list[str]              # YT brandingSettings keywords, split on spaces respecting quotes; [] IG
  is_verified: bool                # IG; False YT (API doesn't expose it)
  is_business_account: bool        # IG
  business_category: str | None    # IG business_category_name / category_name
  made_for_kids: bool | None       # YT; None IG
  platform_user_id: str | None     # UC... / IG pk, shown as "Channel ID"
}
```
Populate in `CreatorStatsService.get_about(influencer_id)` from the latest snapshot;
wire into the `/stats` endpoint response.

### B4. API

- `GET /influencers/{id}/growth` — accepts `metric=followers|total_views|posts|earnings`.
- `GET /influencers/{id}/events?days=90` → `list[KeyEvent]`.
- `/stats` response gains `about: AboutOut`.

### B5. Tests

- Milestone detection (crossing exactly at/over thresholds, no snapshot history, one
  snapshot only).
- Earnings series band math + Instagram returns empty.
- About topic-URL prettification and keyword splitting.

---

## Phase C — UI (dashboard/) — restructure + polish

All in React 19 / Tailwind v4 / recharts v3, matching existing components. Update
`creatorStatsService.js` with `getFormatBreakdown`, `getKeyEvents`, and the new params.

### C1. Two new reusable primitives — `dashboard/src/components/common/`

1. **`InfoTip.jsx`** — small `Info` (lucide) icon; on hover/focus shows a dark tooltip
   (absolute-positioned div, `max-w-[260px]`, `z-50`, arrow optional; use CSS
   `group-hover` — no new deps). Props: `text`, optional `side`. Keyboard accessible
   (`tabIndex=0`, shows on focus).
2. **`Banner.jsx`** — inline callout bar. Props: `variant` (`info` accent / `warning`
   amber / `estimate` violet), `icon`, `children`, optional `dismissible` (state only,
   no persistence). Rounded-xl, subtle tinted background using existing CSS vars
   (`--color-accent-dim`, `--color-warning-muted`).

Use these everywhere below — every stat tile, section header, and chart gets an
InfoTip; every estimated/derived figure gets a Banner or inline disclaimer.

**Exact tooltip copy** (implement verbatim, platform-aware where noted):
| Where | Copy |
|---|---|
| Followers/Subscribers tile | "Latest scraped count. YouTube rounds subscriber counts to 3 significant figures, so large channels move in visible steps." (YT) / "Latest scraped follower count — exact, updated on each daily scrape." (IG) |
| 28d delta chip | "Change vs the closest snapshot ~28 days ago. Shows '(partial)' when we've been tracking this account for less time." |
| Views tile | "Lifetime channel views reported by YouTube." (YT) / "Views gained across posts in the last 28 days, reconstructed from per-post daily snapshots. Undercounts right after an account is first backfilled." (IG) |
| Engagement rate | "Average likes + comments on the last 12 posts, divided by current followers. Posts with hidden like counts are excluded." |
| Estimated earnings | "Rough industry-rate estimate (not real revenue): monthly views × typical ad RPM for the channel's country." (YT) / "Estimated price for one sponsored post: follower count × typical rate, adjusted by engagement rate." (IG) |
| Tracked rank | "Rank among the accounts tracked in this dashboard only — not a global or industry rank." |
| Outlier column | "This post's views (or likes) vs the account's median over its previous 30 posts. 2× = twice the typical post." |
| Velocity/hr | "Average views (or likes) per hour since publishing. Shown only for posts under 7 days (YouTube) / 48 hours (Instagram) old." |
| Long-form/Shorts split | "Shorts are videos of 3 minutes or less, as classified by YouTube." (YT) / "Reels vs regular posts (photos, carousels)." (IG) |
| Daily growth chart | "Day-over-day change between consecutive daily snapshots. Gaps mean no snapshot was captured that day." |
| Key events | "Markers show standout posts (2×+ outliers) and follower milestones. Hover a marker for details." |

### C2. CreatorProfile restructure — section nav

Keep one page (no router change) but add a sticky in-page section nav under the
header: `Overview · Content · Growth · About` — buttons that `scrollIntoView` their
section (`useRef`s). Sections:

1. **Overview** (existing tiles + earnings + rankings cards, now with InfoTips, plus:)
   - **Format split card** (new): horizontal stacked bar of views_share
     (long vs short, platform colors at 2 opacities), with per-format columns:
     count, total views, avg views. Range pills 7D/28D/3M/1Y/Max (days=7/28/90/365/3650)
     backed by `GET /formats`. Platform-aware labels: "Videos / Shorts" vs
     "Posts / Reels". Banner (info) when one format has 0 posts in range:
     "No {Shorts|Reels} in this period."
2. **Content** (existing recent-posts table, plus:)
   - Segmented filter pills above the table: `All · Videos · Shorts` (YT) /
     `All · Posts · Reels` (IG) → refetches `posts/performance?format=`.
   - New "Type" column rendering a small format badge per row.
   - Keep outlier + velocity columns (now with InfoTips in the header cells).
3. **Growth** (new section replacing the single v1 chart card):
   - Metric tabs: `Subscribers/Followers · Views · Earnings` (Earnings tab hidden on
     Instagram; Views tab on Instagram uses metric=posts? NO — hide Views tab on
     Instagram since there's no channel-level counter; show only Followers + note).
   - Range pills 7D/28D/3M/1Y/Max shared across both charts.
   - **Chart 1 — cumulative**: v1's `GrowthChart` area chart, now with key-event
     markers: recharts `ReferenceDot` at each event date (y = series value at that
     date), colored by type (accent = milestone, success = top_post), custom tooltip
     on hover showing the event label; clicking a top_post dot opens its permalink.
     Earnings metric renders the low/high band (two Areas, `value_low`/`value_high`)
     instead of one line.
   - **Chart 2 — daily change**: recharts `BarChart` of `daily_delta` (green positive
     / red negative bars, `Cell`-based fill). This is the "Daily Subscriber Growth"
     vidiq view. Same events overlaid as small triangles via ReferenceDot on the zero
     line is optional — skip if noisy; events live on chart 1.
   - Banner (warning) when series length < selected range: "Tracking began
     {first_date} — showing {n} days of data."
4. **About** (new): two-column grid card —
   - Left: description (whitespace-preserved, clamp to 6 lines with Show more/less),
     link chips (external_url + bio_links, ExternalLink icon, `noreferrer`).
   - Right: metadata rows (Country, Created on platform, Category, Business
     category, Channel/Account ID with copy-on-click, Made for kids, Verified) —
     omit rows whose value is null, and topics/keywords as rounded chips (cap at 10,
     "+n more" expander).

### C3. Polish pass (do last, whole page)

- Consistent card paddings (p-5), section headings (`text-sm font-semibold` + InfoTip),
  `animate-fade-in` on sections.
- Loading: skeleton per section (reuse `Skeleton`), never layout-shift.
- All charts: shared axis/tooltip styling from v1's GrowthChart; compact number
  formatting via `utils/format.js` everywhere (add `formatDate` helper there for
  chart tooltips, 'MMM d, yyyy').
- Empty states per section with specific copy (e.g. Growth: "Charts appear after a
  few daily scrapes.").
- Mobile: nav pills wrap; grids collapse to 1 col (`grid-cols-1 lg:grid-cols-2`);
  posts table stays in its `overflow-x-auto` wrapper.
- A single top-of-page Banner (estimate variant, dismissible) once per profile:
  "All figures are derived from public data scraped daily. Earnings are rough
  estimates." — this is the page-level disclaimer banner the user asked for.

---

## Phase D — Verification (each phase lands green before the next)

1. Phase A: `uv run pytest tests/unit` green; `curl
   'localhost:8000/api/v1/influencers/<yt-id>/formats?days=3650'` shows the 22-video
   channel entirely long_form; an IG account with `clips` posts shows both formats;
   `posts/performance?format=short_form` returns only Reels for IG.
2. Phase B: growth `metric=earnings` returns a band for YT and `[]` for IG; events
   for `bhuvan.bam22` include its 52× outlier post; `/stats.about.description`
   non-empty for both platforms.
3. Phase C: `npm run build` clean; manual click-through on both a YouTube and an
   Instagram profile at localhost (API `DEBUG=true
   CORS_ALLOWED_ORIGINS=http://localhost:5173`): every tile shows an InfoTip on
   hover AND on keyboard focus, format filter refetches the table, both growth
   charts respond to range pills, event dots show tooltips and open permalinks,
   About renders with Show more toggle, page-level banner dismisses.
4. Full suite + `npm run build` one final time before PR.

Known pre-existing failures to ignore (NOT caused by this work): 2 in
`tests/unit/test_config.py` (env pollution), 1 in
`tests/unit/test_dispatch_service.py` (stale mock) — present on main.

Non-goals: vidiq's global/country ranks, FAQ section, thumbnails in the posts table
(no image URLs stored for YouTube), true hourly VPH (still Phase 5 of v1's plan),
any scraper or Alembic changes.
