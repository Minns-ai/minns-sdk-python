"""Tests for fetch_agent_prompt — the "in" half of the optimization loop.

Regression pinned here: the control plane can serve a prompt whose temperature
or maxTokens is JSON ``null`` (a nullable column). ``dict.get(k, default)``
returns the default only for an ABSENT key, so ``float(None)`` used to raise and
the blanket ``except`` discarded the whole optimized prompt — the agent then ran
its built-in prompt forever with no error. Mirrors the TS twin's guards.
"""

from unittest.mock import patch

import minns
from minns.observability import MinnsRails, fetch_agent_prompt, _num


def _rails():
    return MinnsRails(prompt_url="https://cp.example/prompt", token="t")


class _Resp:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


class _Client:
    """Minimal context-manager stand-in for httpx.Client returning one body."""

    def __init__(self, body, status_code=200):
        self._resp = _Resp(body, status_code)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, *a, **k):
        return self._resp


def _patch_client(body, status_code=200):
    return patch(
        "minns.observability.httpx.Client",
        lambda *a, **k: _Client(body, status_code),
    )


def test_num_accepts_numbers_rejects_null_bool_and_strings():
    assert _num(0.3, 0.7) == 0.3
    assert _num(5, 0.7) == 5.0
    assert _num(None, 0.7) == 0.7      # JSON null
    assert _num("0.9", 0.7) == 0.7     # string-encoded
    assert _num(True, 0.7) == 0.7      # bool is not a real number here


def test_null_temperature_and_max_tokens_do_not_discard_the_prompt():
    body = {
        "prompt": "opto-optimized",
        "model": "claude-sonnet-4-6",
        "temperature": None,   # the shape that used to blow up
        "maxTokens": None,
        "version": "v2",
    }
    with _patch_client(body):
        cfg = fetch_agent_prompt(_rails())
    assert cfg is not None
    assert cfg.prompt == "opto-optimized"
    assert cfg.temperature == 0.7   # fell back to default, prompt preserved
    assert cfg.max_tokens == 1024
    assert cfg.version == "v2"


def test_real_values_are_honoured():
    body = {"prompt": "p", "model": "m", "temperature": 0.2, "maxTokens": 4096}
    with _patch_client(body):
        cfg = fetch_agent_prompt(_rails())
    assert cfg.temperature == 0.2
    assert cfg.max_tokens == 4096


def test_missing_prompt_or_error_returns_none():
    with _patch_client({"model": "m"}):
        assert fetch_agent_prompt(_rails()) is None
    with _patch_client({"prompt": "p"}, status_code=500):
        assert fetch_agent_prompt(_rails()) is None
    assert fetch_agent_prompt(MinnsRails(prompt_url=None)) is None


def test_version_string_matches_published_package():
    # __version__ drifted behind pyproject before; keep them in lockstep.
    assert minns.__version__ == "0.8.7"
