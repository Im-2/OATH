import pytest

from oath_core.clawpump import ClawPumpError, decode


def test_success_json_is_parsed():
    assert decode(False, '{"txHash": "abc", "status": "executed"}', "swap_execute") == {
        "txHash": "abc", "status": "executed"}
    assert decode(False, "[1, 2]", "get_wallet_history") == [1, 2]


def test_success_plain_text_is_returned_not_raised():
    # Real response seen from remove_from_whitelist on 2026-09-27.
    text = "Address FhpJ6i5oaBiCpNJasksf2qBgFmTv6ikgSUuqDzSBiUod removed from whitelist."
    assert decode(False, text, "remove_from_whitelist") == {"text": text}


def test_plain_text_success_cannot_pass_as_a_swap():
    resp = decode(False, "Swap submitted!", "swap_execute")
    assert resp.get("txHash") is None  # executor refuses: no executed txHash


def test_error_still_raises_even_if_json():
    with pytest.raises(ClawPumpError):
        decode(True, "Authentication failed", "list_agents")
    with pytest.raises(ClawPumpError):
        decode(True, '{"error": "boom"}', "swap_execute")
