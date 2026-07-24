# Graph Report - .  (2026-07-24)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1757 nodes · 5138 edges · 101 communities (90 shown, 11 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 444 edges (avg confidence: 0.58)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `960732e8`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67
- Community 69
- Community 70
- Community 71
- Community 72
- Community 74
- Community 75
- Community 76
- Community 77
- Community 78
- Community 79
- Community 102

## God Nodes (most connected - your core abstractions)
1. `Influencer` - 89 edges
2. `Post` - 72 edges
3. `CreatorStatsService` - 68 edges
4. `InfluencerRepo` - 60 edges
5. `ScrapeJobRepo` - 56 edges
6. `InstagramAccountRepo` - 52 edges
7. `Base` - 48 edges
8. `get_session()` - 46 edges
9. `ScrapeJob` - 44 edges
10. `PostMetricsSnapshot` - 40 edges

## Surprising Connections (you probably didn't know these)
- `lifespan()` --calls--> `init_db()`  [EXTRACTED]
  main.py → app/core/database.py
- `viralytics_error_handler()` --references--> `ViralyticBaseError`  [EXTRACTED]
  main.py → app/core/exceptions.py
- `_PostMetricPoint` --uses--> `Comment`  [INFERRED]
  app/analytics/creator_stats.py → app/models/comment.py
- `_PostMetricPoint` --uses--> `FeatureStore`  [INFERRED]
  app/analytics/creator_stats.py → app/models/feature_store.py
- `_PostMetricPoint` --uses--> `Influencer`  [INFERRED]
  app/analytics/creator_stats.py → app/models/influencer.py

## Import Cycles
- None detected.

## Communities (101 total, 11 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (48): AddAccountForm(), METHODS, AddInstagramTokenForm(), FLAVORS, InstagramBackendToggle(), OPTIONS, AccountTypeBadge(), STYLES (+40 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (35): aggregateByDate(), PerformanceChart(), InfoTip(), PlatformBadge(), STYLES, PlatformFilter(), PlatformIcon(), PlatformVerifiedBadge() (+27 more)

### Community 2 - "Community 2"
Cohesion: 0.09
Nodes (45): Avatar(), ScrapeStatusIndicator(), STYLES, AboutSection(), FormatSplitCard(), ReplyTimeCard(), SponsorshipCard(), CombinedCreatorProfile() (+37 more)

### Community 3 - "Community 3"
Cohesion: 0.07
Nodes (35): DailyGrowthChart(), EngagementTrendChart(), FollowerRatioChart(), CustomTooltip(), EVENT_COLORS, EVENT_TYPE_LABELS, GrowthChart(), METRIC_LABELS (+27 more)

### Community 4 - "Community 4"
Cohesion: 0.05
Nodes (23): get_dlq_contents(), get_queue_status(), BaseModel, QueueBackend, Enqueue a message and return the receipt handle/message ID., Dequeue messages, returning a list of (receipt_handle, message)., Delete a message from the queue after successful processing., Return the approximate number of messages in the queue. (+15 more)

### Community 5 - "Community 5"
Cohesion: 0.11
Nodes (36): ErrorState(), HeaderPill(), AddCategoryForm(), InfluencerRow(), MassImportInfluencersForm(), STATUS_ICON, CategoryProfile(), EMPTY_DRAFT (+28 more)

### Community 6 - "Community 6"
Cohesion: 0.11
Nodes (33): Post, comment_row(), count_stored_comments(), _delete_missing_comments(), get_latest_comment_synced_at(), last_comment_count(), normalize_comment(), NormalizedComment (+25 more)

### Community 7 - "Community 7"
Cohesion: 0.07
Nodes (34): Accounts, App(), CategoryProfile, CombinedCreatorProfile, Content, CreatorProfile, Export, Influencers (+26 more)

### Community 8 - "Community 8"
Cohesion: 0.08
Nodes (23): JobNotCancellableError, ScrapeJobNotFoundError, Human-readable label for whichever credential ran this job --         the Instag, ScrapeJob, JobStats, AsyncSession, date, datetime (+15 more)

### Community 9 - "Community 9"
Cohesion: 0.08
Nodes (38): get_schema(), run_query(), InstagramApiTokenValidationError, QueryExecutionError, QueryNotAllowedError, Raised when a token being registered fails the live Business     Discovery valid, ValidationError, validate_readonly_sql() (+30 more)

### Community 10 - "Community 10"
Cohesion: 0.12
Nodes (19): _compute_vph_current(), content_format(), CreatorStatsService, AsyncSession, date, UUID, Daily estimated-earnings band: each point is that day's view         growth time, Shared by get_post_performance and recompute_outlier_metrics --         the last (+11 more)

### Community 11 - "Community 11"
Cohesion: 0.10
Nodes (32): download_bulk_import_template(), get_instagram_backend(), list_posts(), register_instagram_token_facebook_login(), register_instagram_token_instagram_login(), register_youtube_key(), set_instagram_backend(), update_account_status() (+24 more)

### Community 12 - "Community 12"
Cohesion: 0.08
Nodes (18): ConflictError, InstagramAccountNotFoundError, NotFoundError, NoUsableInstagramTokenError, NoUsableYouTubeKeyError, Any, Exception, QueueConnectionError (+10 more)

### Community 13 - "Community 13"
Cohesion: 0.09
Nodes (16): CredentialHealthSnapshot, A periodic point-in-time snapshot of one pooled credential's health     (an Inst, InstagramAccount, A pooled Instagram session, logged in via app.scraper.login_automator     or by, Whether an egress proxy is pinned. Surfaced to the dashboard so an         opera, InstagramApiToken, A pooled Instagram Graph API (Business Discovery) credential.      Structurally, ScrapeRun (+8 more)

### Community 14 - "Community 14"
Cohesion: 0.08
Nodes (21): AccountOutcome, list_accounts(), register_account_via_cookies(), register_account_via_login(), set_account_proxy(), InstagramAccountRepo, AsyncSession, UUID (+13 more)

### Community 15 - "Community 15"
Cohesion: 0.16
Nodes (10): Base, AnalyticsCache, AppSetting, Small runtime-mutable key/value override store.      Exists specifically because, AuditLog, Category, Creator, Groups the per-platform Influencer rows (Instagram, YouTube, ...)     that repre (+2 more)

### Community 16 - "Community 16"
Cohesion: 0.11
Nodes (25): RawResponse, PostMetricsSnapshot, InstagramMediaItem, InstagramUser, BaseModel, extract_media_cursor(), parse_media_items(), parse_profile() (+17 more)

### Community 17 - "Community 17"
Cohesion: 0.17
Nodes (9): Settings, decrypt_json(), encrypt_json(), _fernet(), Any, The account's pinned egress proxy URL, or None for a direct         connection., AlertOut, BaseModel (+1 more)

### Community 18 - "Community 18"
Cohesion: 0.14
Nodes (31): _aggregate_format_breakdown(), _aggregate_performance_decay(), _aggregate_sponsorship_breakdown(), _clamp(), _comment_stats_from_bucket(), _compute_composite_outlier_score(), _decay_bucket_index(), _DecayRow (+23 more)

### Community 19 - "Community 19"
Cohesion: 0.09
Nodes (23): health(), Returns 200 immediately. Used by load balancers / container orchestrators., Returns 200 when all dependencies are reachable, 503 otherwise.     Checked by E, ready(), close_db(), Dispose the engine connection pool on shutdown., configure_logging(), get_logger() (+15 more)

### Community 20 - "Community 20"
Cohesion: 0.12
Nodes (17): A pooled YouTube Data API v3 key.      Unlike InstagramAccount, keys are safely, YouTubeApiKey, AsyncSession, UUID, Atomic increment (not read-modify-write) -- safe under the         concurrent re, Register (or re-register) a key. Upserts by label, same pattern         as Insta, Picks the active key with the most quota headroom.          Unlike InstagramAcco, YouTubeApiKeyRepo (+9 more)

### Community 21 - "Community 21"
Cohesion: 0.11
Nodes (16): InstagramApiTokenNotFoundError, InstagramApiTokenRepo, AsyncSession, datetime, UUID, Atomic increment (not read-modify-write) -- safe under the         concurrent re, Applies a refreshed access token (see the daily         refresh_instagram_tokens, Register (or re-register) a token. Upserts by label, same         pattern as You (+8 more)

### Community 22 - "Community 22"
Cohesion: 0.14
Nodes (28): estimate_instagram_earnings(), estimate_youtube_earnings(), instagram_value_per_1k_views_range(), Estimated-earnings heuristics for the creator-stats profile page.  These are rou, (low, high) USD RPM for a channel's country -- exposed separately     from estim, (low, high) USD estimated content value per 1,000 views for     Instagram -- exp, Monthly ad-revenue estimate from trailing-28-day views. None if we     don't hav, Estimated price for a single sponsored post. None when followers are     hidden (+20 more)

### Community 23 - "Community 23"
Cohesion: 0.12
Nodes (29): get_db(), _get_engine(), get_session(), _get_session_factory(), init_db(), async_sessionmaker, AsyncSession, Async context manager for use in background jobs, workers, and scripts.      Exa (+21 more)

### Community 24 - "Community 24"
Cohesion: 0.12
Nodes (17): A specific YouTube resource is permanently unavailable for a reason     that isn, YouTubeResourceGoneError, _extract_error_message(), _extract_error_reason(), Any, UUID, The key currently in use, for ops visibility into "which key ran         this jo, Total quota units this client has spent so far -- i.e. this job's         runnin (+9 more)

### Community 25 - "Community 25"
Cohesion: 0.12
Nodes (26): bulk_import_influencers(), update_influencer_active(), update_influencer_details(), update_influencer_scrape_settings(), DuplicateInfluencerError, BulkImportResult, BulkImportRowResult, BaseModel (+18 more)

### Community 26 - "Community 26"
Cohesion: 0.13
Nodes (20): CredentialHealthChart(), pivotByDate(), STATUS_COLORS, JobStatusChart(), pivotByDate(), STATUS_COLORS, QueueDepthChart(), AlertsBanner() (+12 more)

### Community 27 - "Community 27"
Cohesion: 0.11
Nodes (23): _aggregate_comment_engagement(), _aggregate_reply_time_heatmap(), _CommentEngagementRow, _empty_comment_bucket(), _FormatRow, _OutlierDetail, Everything the batch persistence path (docs/OUTLIERS_PLAN.md Phase 1)     needs, How quickly the creator replies to comments, bucketed by         time-since-post (+15 more)

### Community 28 - "Community 28"
Cohesion: 0.12
Nodes (25): cancel_job(), delete_account(), delete_category(), delete_creator(), delete_influencer(), delete_instagram_token(), delete_youtube_key(), get_dashboard_status() (+17 more)

### Community 29 - "Community 29"
Cohesion: 0.18
Nodes (20): get_credential_health(), get_dashboard_metrics(), get_queue_history(), get_recent_verify_jobs(), get_verify_jobs_summary(), date, CredentialHealthBucket, CredentialHealthOut (+12 more)

### Community 30 - "Community 30"
Cohesion: 0.18
Nodes (24): get_public_creator_performance_decay(), get_public_creator_sponsorship(), _merge_growth_series(), _merge_performance_decay(), _merge_posting_times(), _merge_sponsorship_stats(), Combines per-platform series into one "combined" line. Always     returns a seri, Post-count-weighted average of the avg_* fields across platforms --     a straig (+16 more)

### Community 31 - "Community 31"
Cohesion: 0.16
Nodes (15): create_category(), list_categories(), register_influencer(), update_category(), CategoryNotFoundError, DuplicateCategoryError, CategoryRepo, AsyncSession (+7 more)

### Community 32 - "Community 32"
Cohesion: 0.16
Nodes (14): InstagramAccountNotProfessionalError, Business Discovery can only read Instagram professional (Business or     Creator, ScraperRateLimitError, _extract_error(), InstagramGraphClient, _max_usage_pct(), Any, UUID (+6 more)

### Community 33 - "Community 33"
Cohesion: 0.13
Nodes (11): InfluencerRepo, AsyncSession, Row, UUID, Partial update -- only fields actually present in the request         are applie, Pause/resume tracking without touching any scraped data -- the         default,, Corrects a wrong handle or moves an influencer to a different         category a, Hard delete -- cascades to posts/comments/snapshots/feature_store         via DB (+3 more)

### Community 34 - "Community 34"
Cohesion: 0.21
Nodes (12): BaseModel, YouTubeChannel, YouTubeComment, YouTubeVideo, parse_iso8601_duration(), parse_iso8601_to_datetime(), _parse_iso8601_to_epoch(), Any (+4 more)

### Community 35 - "Community 35"
Cohesion: 0.13
Nodes (18): get_public_creator_profile(), Response, Public combined creator profile for the marketing site's creator     detail page, get_influencer_avatar(), get_top_influencers(), AsyncSession, BaseModel, Response (+10 more)

### Community 36 - "Community 36"
Cohesion: 0.12
Nodes (12): UsageRecorder, curl_proxies(), curl_cffi's AsyncSession takes a requests-style {scheme: url} mapping.     Retur, Paces every outbound request against one account/session/key.      Replaces per-, TokenBucketRateLimiter, UsageRecorder, KeyExhauster, KeyInvalidator (+4 more)

### Community 37 - "Community 37"
Cohesion: 0.11
Nodes (19): devDependencies, eslint, @eslint/js, eslint-plugin-react-hooks, eslint-plugin-react-refresh, globals, @types/react, @types/react-dom (+11 more)

### Community 38 - "Community 38"
Cohesion: 0.18
Nodes (10): InfluencerHandleNotFoundError, The public (unauthenticated) youtube.com channel page couldn't be     fetched or, The platform itself confirms this handle/channel doesn't exist --     distinct f, YouTubeChannelPageError, fetch_is_verified(), Reads the verification checkmark off youtube.com's public channel page.  The Dat, Exactly one of handle/channel_id must be set -- same shape as     YouTubeClient., AsyncSession (+2 more)

### Community 39 - "Community 39"
Cohesion: 0.11
Nodes (20): Shared by both platforms' scrapers -- originally Instagram-only (the     message, ScraperBlockedError, ScraperTimeoutError, InstagramClient, _is_checkpoint_response(), _is_soft_throttle_body(), Any, Convenience constructor for an InstagramAccount pool row. (+12 more)

### Community 40 - "Community 40"
Cohesion: 0.18
Nodes (9): CreatorNotFoundError, DuplicateCreatorError, CreatorRepo, AsyncSession, UUID, Eager-loads Creator.influencers so the API layer can summarize         which pla, Same as get_by_id but eager-loads Creator.influencers -- plain         get_by_id, Case-insensitive match on the trimmed name -- so registering a         creator's (+1 more)

### Community 41 - "Community 41"
Cohesion: 0.18
Nodes (14): _classify_page(), _human_delay(), LoginResult, perform_login(), Return (status, detail) if the page matches a terminal, non-success     state; N, _type_like_human(), playwright_proxy(), Playwright wants the credentials split out of the server URL:     {"server": "sc (+6 more)

### Community 42 - "Community 42"
Cohesion: 0.12
Nodes (17): clsx, cmdk, dependencies, clsx, cmdk, date-fns, echarts, react (+9 more)

### Community 43 - "Community 43"
Cohesion: 0.23
Nodes (16): get_public_creator_growth(), get_public_creator_posting_frequency(), get_public_creator_posting_times(), get_public_creator_posts(), _merge_posting_frequency(), AsyncSession, UUID, Public recent/top posts for the creator detail page, combining every     linked (+8 more)

### Community 44 - "Community 44"
Cohesion: 0.23
Nodes (8): InfluencerNotFoundError, InstagramGraphJobProcessor, AsyncSession, UUID, Marks the influencer as not API-supported (so future dispatches         route st, Gated by INSTAGRAM_ENRICH_EVERY_N_CYCLES (days-since-epoch % N         == 0, the, Insert a new Post, or refresh an existing one's expiring         CDN URLs and ca, Updates today's snapshot in place if one already exists (e.g.         cookie enr

### Community 45 - "Community 45"
Cohesion: 0.24
Nodes (7): JobProcessor, AsyncSession, UUID, The platform confirmed this handle doesn't resolve to any         account -- dea, Best-effort: re-score and persist this influencer's recent posts'         outlie, Background ticker for the duration of process(): every         JOB_HEARTBEAT_INT, Delegates to the platform-agnostic-signature shared function         (app.worker

### Community 46 - "Community 46"
Cohesion: 0.21
Nodes (9): BenchmarkOut, get_latest_benchmark(), AsyncSession, BaseModel, UUID, CategoryAggregator, AsyncSession, UUID (+1 more)

### Community 47 - "Community 47"
Cohesion: 0.21
Nodes (9): get_influencer_recommendations(), AsyncSession, BaseModel, UUID, RecommendationOut, Recommendation, AsyncSession, UUID (+1 more)

### Community 48 - "Community 48"
Cohesion: 0.21
Nodes (6): PostOutlierMetrics, Persisted, re-computed-on-scrape outlier/velocity scoring for a post     -- one, Each row: {post_id, outlier_score, baseline_multiple, vph_current,         vph_l, PostRepo, AsyncSession, UUID

### Community 49 - "Community 49"
Cohesion: 0.22
Nodes (8): InstagramEnrichProcessor, _is_comment_sync_candidate(), AsyncSession, UUID, Best-effort, same as JobProcessor/InstagramGraphJobProcessor's         counterpa, Fields the Graph API never exposes for third-party media, which         only rid, Updates today's PostMetricsSnapshot in place with view/play data         (the on, Should this matched post get a comment-sync attempt this run?      A post with z

### Community 50 - "Community 50"
Cohesion: 0.21
Nodes (11): _aggregate_posting_times(), _compute_outlier_and_velocity(), _compute_outlier_details(), _point_engagement_rate(), _PostMetricPoint, datetime, views when the platform exposes it, else likes -- Instagram has         no publi, (likes + comments) / outlier_metric for one post -- None when either     side is (+3 more)

### Community 51 - "Community 51"
Cohesion: 0.17
Nodes (9): AppSettingRepo, AsyncSession, Upsert -- one round trip, no read-then-write race between two         concurrent, push_critical_alerts(), AsyncSession, Push channel for critical alerts (alert_service.get_alerts is otherwise pull-onl, _signature(), get_alerts() (+1 more)

### Community 52 - "Community 52"
Cohesion: 0.23
Nodes (10): COLUMNS, formatDuration(), IN_FLIGHT_STATUSES, RELIABILITY_WINDOWS, reliabilityTooltip(), StatusTable(), CANCELLABLE_STATUSES, formatDuration() (+2 more)

### Community 53 - "Community 53"
Cohesion: 0.23
Nodes (11): _detect_milestones(), _format_milestone_label(), _InstagramMetricSnapshotRow, _interpolate_daily_gaps(), Reconstructs a daily cumulative-views series for Instagram from         per-post, Pure function (no DB access) so this logic is unit-testable in     isolation. `p, A leading 0-value point in a followers/total_views series is a     broken/seed s, Fills any gap between two known (date, value) points -- dates more     than a da (+3 more)

### Community 54 - "Community 54"
Cohesion: 0.20
Nodes (7): QueueDepthSnapshot, A periodic point-in-time sample of the scrape job queue's depth,     taken every, AsyncSession, date, Row, QueueDepthRepo, Hour-bucketed, not day-bucketed like everything else in this         dashboard -

### Community 55 - "Community 55"
Cohesion: 0.26
Nodes (10): process_pending_logins(), Event, Runs alongside the main scrape-job dequeue loop in worker_runner.py.      Polls, _effective_max_workers(), handle_sigterm(), main(), Runs up to the effective concurrency cap (see     _effective_max_workers) jobs c, max(static floor, healthy Instagram accounts + YouTube buffer),     refreshed at (+2 more)

### Community 56 - "Community 56"
Cohesion: 0.27
Nodes (10): get_creator(), list_creators(), Every creator group, with which platforms each has a linked account     on -- po, Powers the combined cross-platform creator view -- just the name and     each li, rename_creator(), CreatorDetailOut, CreatorInfluencerRef, CreatorOut (+2 more)

### Community 57 - "Community 57"
Cohesion: 0.44
Nodes (8): FeatureExtractor, count_words(), detect_language(), extract_emojis(), extract_hashtags(), extract_mentions(), has_cta(), has_question()

### Community 58 - "Community 58"
Cohesion: 0.40
Nodes (5): InstagramComment, InstagramParser, Any, Parse a page of top-level comments from the GraphQL Relay         connection sha, Parse a page of replies to a single comment from the GraphQL         Relay conne

### Community 59 - "Community 59"
Cohesion: 0.20
Nodes (9): name, private, scripts, build, dev, lint, preview, type (+1 more)

### Community 60 - "Community 60"
Cohesion: 0.32
Nodes (7): do_run_migrations(), Alembic environment — async SQLAlchemy 2.x edition.  Loads DATABASE_URL from app, Emit SQL to stdout without a live DB connection., run_async_migrations(), run_migrations_offline(), run_migrations_online(), Connection

### Community 61 - "Community 61"
Cohesion: 0.60
Nodes (4): _bucket_engagement_trend(), _EngagementTrendRow, Engagement rate ((likes+comments)/followers), averaged per         posting-date, EngagementTrendPoint

### Community 62 - "Community 62"
Cohesion: 0.38
Nodes (6): export_dump(), DumpExportError, create_dump(), _libpq_url(), pg_dump speaks libpq URIs (`postgresql://...`), not SQLAlchemy's     driver-qual, Runs `pg_dump -Fc` to a temp file and returns (path, filename).      Custom form

### Community 63 - "Community 63"
Cohesion: 0.33
Nodes (4): LeaderboardEntry, Shared projection behind get_top_ranked and get_public_accounts:         each in, One /influencers/top row -- either a single platform account, or a     creator's, Ranked leaderboard for the public "Top Influencers" page.          A creator wit

### Community 64 - "Community 64"
Cohesion: 0.50
Nodes (5): get_public_creator_engagement_trend(), _merge_engagement_trend(), Averages the engagement rate across whichever platforms posted in a     given bu, Public engagement-rate trend for the creator detail page. No auth     required -, PublicEngagementTrendPoint

### Community 65 - "Community 65"
Cohesion: 0.50
Nodes (5): get_public_creator_follower_ratio(), _merge_follower_ratio(), Forward-fills each platform's last known followers/following so     differing sc, Public followers/following ratio history for the creator detail     page. No aut, PublicFollowerRatioPoint

### Community 67 - "Community 67"
Cohesion: 0.67
Nodes (3): _bucket_posting_frequency(), How many posts landed per week (or day) over the window --         answers "are, PostingFrequencyPoint

### Community 69 - "Community 69"
Cohesion: 0.50
Nodes (3): date, Row, One row per (day, platform, status): how many of that day's         snapshots la

## Knowledge Gaps
- **97 isolated node(s):** `name`, `private`, `version`, `type`, `dev` (+92 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Influencer` connect `Community 10` to `Community 6`, `Community 8`, `Community 15`, `Community 16`, `Community 18`, `Community 27`, `Community 31`, `Community 33`, `Community 38`, `Community 44`, `Community 45`, `Community 46`, `Community 47`, `Community 48`, `Community 49`, `Community 50`, `Community 53`, `Community 61`, `Community 63`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Why does `InfluencerRepo` connect `Community 33` to `Community 6`, `Community 8`, `Community 10`, `Community 11`, `Community 15`, `Community 16`, `Community 23`, `Community 25`, `Community 27`, `Community 28`, `Community 29`, `Community 30`, `Community 31`, `Community 35`, `Community 40`, `Community 43`, `Community 44`, `Community 51`, `Community 63`, `Community 64`, `Community 65`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Why does `CreatorStatsService` connect `Community 10` to `Community 64`, `Community 65`, `Community 67`, `Community 6`, `Community 43`, `Community 44`, `Community 45`, `Community 16`, `Community 49`, `Community 18`, `Community 50`, `Community 53`, `Community 22`, `Community 27`, `Community 61`, `Community 30`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Are the 61 inferred relationships involving `Influencer` (e.g. with `_CommentEngagementRow` and `CreatorStatsService`) actually correct?**
  _`Influencer` has 61 INFERRED edges - model-reasoned connections that need verification._
- **Are the 39 inferred relationships involving `Post` (e.g. with `_CommentEngagementRow` and `CreatorStatsService`) actually correct?**
  _`Post` has 39 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `CreatorStatsService` (e.g. with `Comment` and `FeatureStore`) actually correct?**
  _`CreatorStatsService` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `InfluencerRepo` (e.g. with `TopInfluencerOut` and `DuplicateInfluencerError`) actually correct?**
  _`InfluencerRepo` has 14 INFERRED edges - model-reasoned connections that need verification._