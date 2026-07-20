from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.scraper.instagram_graph_parser import (
    _parse_timestamp,
    _shortcode_from_permalink,
    extract_media_cursor,
    parse_media_items,
    parse_profile,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "instagram_graph"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(scope="module")
def page1() -> dict:
    return _load("business_discovery_page1.json")["business_discovery"]


@pytest.fixture(scope="module")
def page2() -> dict:
    return _load("business_discovery_page2.json")["business_discovery"]


# ── parse_profile ────────────────────────────────────────────────────────

def test_parse_profile_maps_real_fixture_fields(page1):
    user = parse_profile(page1)
    assert user.username == "myntra"
    assert user.follower_count > 0
    assert user.media_count > 0
    assert user.is_business_account is True
    assert user.is_professional_account is True
    assert user.is_private is False


def test_parse_profile_defaults_fields_business_discovery_does_not_expose():
    # is_verified, pronouns, bio_links, highlight_reel_count etc. aren't
    # returned by Business Discovery at all -- must land at InstagramUser's
    # defaults, not raise/KeyError, so callers can preserve last-known values.
    user = parse_profile({"username": "x", "id": "1"})
    assert user.is_verified is False
    assert user.pronouns == []
    assert user.bio_links == []
    assert user.highlight_reel_count == 0


# ── parse_media_items ────────────────────────────────────────────────────

def test_parse_media_items_returns_all_items_on_a_page(page1):
    items = parse_media_items(page1)
    assert len(items) == 25


def test_parse_media_items_maps_reel_to_short_form_product_type(page1):
    items = parse_media_items(page1)
    reels = [i for i in items if i.product_type == "clips"]
    assert len(reels) == 11  # matches media_product_type=="REELS" count in the fixture
    for reel in reels:
        assert reel.media_type == 2  # VIDEO


def test_parse_media_items_feed_image_has_no_product_type(page1):
    items = parse_media_items(page1)
    images = [i for i in items if i.media_type == 1]
    assert len(images) == 4  # matches IMAGE count in the fixture
    for img in images:
        assert img.product_type is None


def test_parse_media_items_carousel_children_preserved_as_raw_dicts(page1):
    items = parse_media_items(page1)
    carousels = [i for i in items if i.media_type == 8]
    assert len(carousels) == 10  # matches CAROUSEL_ALBUM count in the fixture
    with_children = [c for c in carousels if c.children]
    assert with_children
    child = with_children[0].children[0]
    assert "media_type" in child


def test_parse_media_items_preserves_null_like_count_as_hidden_signal():
    items = parse_media_items(
        {"media": {"data": [{"id": "1", "like_count": None, "media_type": "IMAGE"}]}}
    )
    assert items[0].like_count is None


def test_parse_media_items_wraps_caption_string_in_text_dict(page1):
    items = parse_media_items(page1)
    captioned = [i for i in items if i.caption]
    assert captioned
    assert isinstance(captioned[0].caption, dict)
    assert "text" in captioned[0].caption


def test_parse_media_items_tolerates_missing_media_url():
    # API-only fields may be absent (e.g. copyright-flagged media) --
    # must not raise.
    items = parse_media_items({"media": {"data": [{"id": "1", "media_type": "IMAGE"}]}})
    assert items[0].media_url is None
    assert items[0].thumbnail_url is None


def test_parse_media_items_empty_when_no_media_connection():
    assert parse_media_items({}) == []


def test_parse_media_items_page2_parses_cleanly(page2):
    items = parse_media_items(page2)
    assert len(items) == 25
    assert all(i.code for i in items)  # every item resolved a shortcode


# ── extract_media_cursor ─────────────────────────────────────────────────

def test_extract_media_cursor_returns_real_cursor_on_full_page(page1):
    cursor = extract_media_cursor(page1)
    assert cursor
    assert isinstance(cursor, str)


def test_extract_media_cursor_empty_string_when_no_paging():
    assert extract_media_cursor({"media": {"data": []}}) == ""
    assert extract_media_cursor({}) == ""


# ── _shortcode_from_permalink ────────────────────────────────────────────

@pytest.mark.parametrize(
    "permalink,expected",
    [
        ("https://www.instagram.com/p/DbAE99LJAdt/", "DbAE99LJAdt"),
        ("https://www.instagram.com/reel/DbANXSSJ9SA/", "DbANXSSJ9SA"),
        (None, ""),
        ("", ""),
    ],
)
def test_shortcode_from_permalink(permalink, expected):
    assert _shortcode_from_permalink(permalink) == expected


# ── _parse_timestamp ──────────────────────────────────────────────────────

def test_parse_timestamp_handles_bare_offset_format():
    # Confirmed against a real fixture: Business Discovery returns
    # "+0000" (no colon), which datetime.fromisoformat rejects outright.
    assert _parse_timestamp("2026-07-18T09:36:51+0000") > 0


def test_parse_timestamp_returns_zero_for_missing_or_invalid():
    assert _parse_timestamp(None) == 0
    assert _parse_timestamp("") == 0
    assert _parse_timestamp("not-a-date") == 0
