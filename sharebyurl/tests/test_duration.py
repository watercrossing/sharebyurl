from datetime import timedelta

import pytest

from sharebyurl.duration import DurationError, format_delta, parse_duration


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("7d", timedelta(days=7)),
        ("12h", timedelta(hours=12)),
        ("4w", timedelta(weeks=4)),
        ("30m", timedelta(minutes=30)),
        ("1y", timedelta(days=365)),
        ("  7d  ", timedelta(days=7)),
        ("7 d", timedelta(days=7)),
        ("7D", timedelta(days=7)),
    ],
)
def test_parses_valid_durations(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["never", "none", "forever", "NEVER"])
def test_never_words_mean_no_expiry(text):
    assert parse_duration(text) is None


def test_legacy_minus_one_means_never():
    # Version 0.3 wrote `default_expiry = -1` for "no expiry".
    assert parse_duration("-1") is None


@pytest.mark.parametrize("text", ["", "soon", "7", "d7", "7x", "7 months", "-"])
def test_rejects_nonsense(text):
    with pytest.raises(DurationError):
        parse_duration(text)


def test_rejects_zero_length_rather_than_expiring_immediately():
    with pytest.raises(DurationError, match="never"):
        parse_duration("0d")


def test_m_is_minutes_not_months():
    assert parse_duration("1m") == timedelta(minutes=1)


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(days=14), "2 weeks"),
        (timedelta(days=1), "1 day"),
        (timedelta(hours=5), "5 hours"),
        (timedelta(minutes=1), "1 minute"),
        (timedelta(seconds=5), "less than a minute"),
    ],
)
def test_format_delta(delta, expected):
    assert format_delta(delta) == expected
