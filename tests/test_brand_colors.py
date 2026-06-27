"""Tests for the curated brand-colour table and its lookup/normalisation."""

import pytest

from ambilight.notifications.brand_colors import BRAND_COLORS, brand_color


def test_table_is_substantial():
    # Curated "top ~500" target; guard against an accidental truncation.
    assert len(BRAND_COLORS) >= 450


def test_all_values_are_valid_rgb():
    for name, rgb in BRAND_COLORS.items():
        assert isinstance(rgb, tuple) and len(rgb) == 3, name
        assert all(isinstance(c, int) and 0 <= c <= 255 for c in rgb), name


@pytest.mark.parametrize(
    "name,expected",
    [
        ("WhatsApp", (37, 211, 102)),    # simple-icons #25D366
        ("Discord", (88, 101, 242)),     # simple-icons #5865F2
        ("Spotify", (30, 215, 96)),      # simple-icons #1ED760
        ("Microsoft Teams", (70, 78, 184)),  # supplement #464EB8
        ("Slack", (74, 21, 75)),         # supplement #4A154B (aubergine)
        ("LinkedIn", (10, 102, 194)),    # supplement #0A66C2
        ("Amazon", (255, 153, 0)),       # supplement #FF9900
    ],
)
def test_known_brands(name, expected):
    assert brand_color(name) == expected


def test_normalisation_is_case_and_punctuation_insensitive():
    base = brand_color("WhatsApp")
    assert base is not None
    assert brand_color("whatsapp") == base
    assert brand_color("  WHATS APP! ") == base


def test_company_prefix_stripped_both_directions():
    # An app may report itself as "Microsoft Outlook" or just "Outlook".
    full = brand_color("Microsoft Outlook")
    assert full is not None
    assert brand_color("Outlook") == full
    # Same for Google-prefixed apps.
    assert brand_color("Google Chrome") == brand_color("Chrome")


def test_unknown_app_returns_none():
    assert brand_color("Some Private Internal Tool") is None
    assert brand_color("") is None
    assert brand_color(None) is None


@pytest.mark.parametrize(
    "app_id,expected_name",
    [
        ("com.squirrel.Discord.Discord", "Discord"),
        ("MicrosoftTeams_8wekyb3d8bbwe!App", "Microsoft Teams"),
        ("SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify", "Spotify"),
    ],
)
def test_matched_via_app_id_tokens(app_id, expected_name):
    # When the display name is unknown, a brand token in the AUMID still resolves.
    assert brand_color("", app_id) == brand_color(expected_name)


def test_app_name_takes_priority_over_app_id():
    # A known display name wins even if the app_id mentions a different brand.
    assert brand_color("Spotify", "com.squirrel.Discord.Discord") == brand_color("Spotify")
