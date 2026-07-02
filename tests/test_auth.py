"""Tests for the service-token authorization helper."""

from auth import token_is_authorized


def test_disabled_when_no_expected_token():
    # With no configured token, auth is disabled and accepts anything.
    assert token_is_authorized(None, None) is True
    assert token_is_authorized("anything", None) is True
    assert token_is_authorized(None, "") is True


def test_accepts_matching_token():
    assert token_is_authorized("s3cr3t-token", "s3cr3t-token") is True


def test_rejects_wrong_token():
    assert token_is_authorized("wrong", "s3cr3t-token") is False


def test_rejects_missing_token_when_required():
    assert token_is_authorized(None, "s3cr3t-token") is False
    assert token_is_authorized("", "s3cr3t-token") is False
