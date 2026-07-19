from __future__ import annotations

from app.services.influencer_bulk_import import parse_bulk_import_rows


def _row(creator_name="MrBeast", category="Entertainment", type_="individual", instagram=None, youtube=None):
    return {
        "creator_name": creator_name,
        "category": category,
        "type": type_,
        "instagram_handle": instagram,
        "youtube_handle": youtube,
    }


def test_valid_row_with_both_handles():
    [row] = parse_bulk_import_rows([_row(instagram="mrbeast", youtube="@MrBeast")])
    assert row.error is None
    assert row.row_number == 1
    assert row.creator_name == "MrBeast"
    assert row.category_name == "Entertainment"
    assert row.account_type == "individual"
    assert row.instagram_handle == "mrbeast"
    assert row.youtube_handle == "@MrBeast"


def test_valid_row_with_only_instagram_handle():
    [row] = parse_bulk_import_rows([_row(instagram="mrbeast", youtube=None)])
    assert row.error is None
    assert row.instagram_handle == "mrbeast"
    assert row.youtube_handle is None


def test_row_numbers_are_1_indexed_and_sequential():
    rows = parse_bulk_import_rows([_row(instagram="a"), _row(instagram="b"), _row(instagram="c")])
    assert [r.row_number for r in rows] == [1, 2, 3]


def test_strips_leading_at_from_instagram_handle():
    [row] = parse_bulk_import_rows([_row(instagram="@mrbeast")])
    assert row.instagram_handle == "mrbeast"


def test_leaves_leading_at_on_youtube_handle():
    # YouTube's own normalize_handle (InfluencerRepo) expects/produces the
    # "@name" form -- stripping it here would just make that function
    # re-add it, so youtube_handle is passed through untouched.
    [row] = parse_bulk_import_rows([_row(instagram=None, youtube="@MrBeast")])
    assert row.youtube_handle == "@MrBeast"


def test_missing_creator_name_errors():
    [row] = parse_bulk_import_rows([_row(creator_name="", instagram="mrbeast")])
    assert row.error == "creator_name is required"


def test_missing_category_errors():
    [row] = parse_bulk_import_rows([_row(category="", instagram="mrbeast")])
    assert row.error == "category is required"


def test_missing_type_errors():
    [row] = parse_bulk_import_rows([_row(type_="", instagram="mrbeast")])
    assert row.error == "type is required (individual or business)"


def test_invalid_type_errors():
    [row] = parse_bulk_import_rows([_row(type_="influencer", instagram="mrbeast")])
    assert row.error == "type must be 'individual' or 'business', got 'influencer'"


def test_type_is_case_insensitive():
    [row] = parse_bulk_import_rows([_row(type_="Business", instagram="mrbeast")])
    assert row.error is None
    assert row.account_type == "business"


def test_no_handles_at_all_errors():
    [row] = parse_bulk_import_rows([_row(instagram=None, youtube=None)])
    assert row.error == "at least one of instagram_handle or youtube_handle is required"


def test_blank_handle_cells_treated_as_absent():
    # Cells with whitespace-only content (a common spreadsheet artifact)
    # must not count as "a handle was provided".
    [row] = parse_bulk_import_rows([_row(instagram="   ", youtube=None)])
    assert row.error == "at least one of instagram_handle or youtube_handle is required"


def test_column_names_are_case_and_spacing_insensitive():
    raw = {
        "Creator Name": "MrBeast",
        "CATEGORY": "Entertainment",
        "Type": "individual",
        "Instagram Handle": "mrbeast",
        "YouTube Handle": None,
    }
    [row] = parse_bulk_import_rows([raw])
    assert row.error is None
    assert row.creator_name == "MrBeast"
    assert row.instagram_handle == "mrbeast"


def test_multiple_rows_validated_independently():
    rows = parse_bulk_import_rows([
        _row(instagram="good_row"),
        _row(creator_name="", instagram="bad_row"),
        _row(instagram="another_good_row"),
    ])
    assert [r.error for r in rows] == [None, "creator_name is required", None]
