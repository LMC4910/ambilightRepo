"""Tests for GitHub webhook HMAC verification + header parsing."""

import hashlib
import hmac

from ambilight.integrations.github import webhook


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_accepted():
    body = b'{"action":"opened"}'
    sig = _sign("s3cr3t", body)
    assert webhook.verify_signature("s3cr3t", body, sig) is True


def test_wrong_secret_rejected():
    body = b'{"action":"opened"}'
    sig = _sign("s3cr3t", body)
    assert webhook.verify_signature("other", body, sig) is False


def test_tampered_body_rejected():
    sig = _sign("s3cr3t", b'{"action":"opened"}')
    assert webhook.verify_signature("s3cr3t", b'{"action":"closed"}', sig) is False


def test_missing_secret_or_header_fails_closed():
    body = b"{}"
    assert webhook.verify_signature("", body, _sign("x", body)) is False
    assert webhook.verify_signature("x", body, None) is False
    assert webhook.verify_signature("x", body, "md5=deadbeef") is False


def test_parse_headers():
    headers = {"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "abc-123"}
    event, delivery = webhook.parse_headers(headers)
    assert event == "pull_request"
    assert delivery == "abc-123"
