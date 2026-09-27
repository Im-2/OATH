import hashlib

import pytest

from oath_core.thesis import (ThesisError, build_thesis, canonical_json, digest, fmt_decimal,
                              parse_canonical, validate)

AGENT = "9jxuhhv7pe3iL8tFfDvS1TuRRC18LCyT7g6c5wR332bY"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL = "So11111111111111111111111111111111111111112"
SALT = bytes(range(32))

GOLDEN_CANONICAL = (
    '{"agent":"9jxuhhv7pe3iL8tFfDvS1TuRRC18LCyT7g6c5wR332bY","conf":"0.78","entry":"214.200000",'
    '"horizon_min":"240","in_mint":"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v","mkt":"SOL/USDC",'
    '"out_mint":"So11111111111111111111111111111111111111112","seq":"42","side":"long","size_usd":"5.00",'
    '"stop":"208.500000","strat":"momentum","tp":"225.000000","ts":"2026-09-28T14:03:11Z","v":"1",'
    '"why":"MOM_BREAKOUT: 4h close above range high on rising volume"}'
).encode()
GOLDEN_DIGEST = "9a29b8e2878a759ccd5cef07a5415ae3aadb580c793dd401f8c8c45e90644549"


def golden(**over):
    kw = dict(agent=AGENT, seq=42, mkt="SOL/USDC", in_mint=USDC, out_mint=SOL, size_usd="5",
              entry="214.2", stop="208.5", tp="225", horizon_min=240, conf="0.78", strat="momentum",
              why="MOM_BREAKOUT: 4h close above range high on rising volume", ts="2026-09-28T14:03:11Z")
    kw.update(over)
    return build_thesis(**kw)


def test_golden_vector():
    c = canonical_json(golden())
    assert c == GOLDEN_CANONICAL
    assert digest(c, SALT) == GOLDEN_DIGEST
    assert hashlib.sha256(GOLDEN_CANONICAL + SALT).hexdigest() == GOLDEN_DIGEST  # formula, independently


def test_number_formatting_is_input_independent():
    a = golden(size_usd="5", entry="214.2", conf="0.78")
    b = golden(size_usd="5.000", entry="214.20000000", conf=".780")
    assert canonical_json(a) == canonical_json(b)


def test_key_order_does_not_matter():
    t = golden()
    reordered = dict(reversed(list(t.items())))
    assert canonical_json(reordered) == GOLDEN_CANONICAL


@pytest.mark.parametrize("field,value", [("why", "MOM_BREAKOUT: 4h close above range high on rising volumf"),
                                         ("entry", "214.200001"), ("seq", "43"), ("ts", "2026-09-28T14:03:12Z")])
def test_one_char_thesis_change_changes_digest(field, value):
    t = golden()
    t[field] = value
    assert digest(canonical_json(t), SALT) != GOLDEN_DIGEST


def test_one_bit_salt_change_changes_digest():
    salt = bytearray(SALT)
    salt[31] ^= 1
    assert digest(GOLDEN_CANONICAL, bytes(salt)) != GOLDEN_DIGEST


def test_parse_canonical_roundtrip_and_rejects_noncanonical():
    assert parse_canonical(GOLDEN_CANONICAL) == golden()
    with pytest.raises(ThesisError):
        parse_canonical(GOLDEN_CANONICAL.replace(b'","', b'", "', 1))  # whitespace
    with pytest.raises(ThesisError):
        parse_canonical(GOLDEN_CANONICAL.replace(b'"5.00"', b'"5.0"'))  # non-fixed decimal


@pytest.mark.parametrize("over", [
    dict(stop="215"),                       # stop >= entry
    dict(tp="214.2"),                       # tp == entry
    dict(size_usd="0"),
    dict(size_usd="-1"),
    dict(entry="NaN"),
    dict(entry="Infinity"),
    dict(conf="1.01"),
    dict(side="short"),
    dict(why=""),
    dict(why="x" * 141),
    dict(why="line\nbreak"),
    dict(in_mint=SOL),                      # in == out
    dict(agent="not-a-pubkey"),
    dict(mkt="sol-usdc"),
    dict(strat="Has Spaces"),
    dict(ts="2026-09-28 14:03:11"),
])
def test_invalid_theses_rejected(over):
    with pytest.raises(ThesisError):
        golden(**over)


def test_seq_and_horizon_must_be_ints():
    with pytest.raises(ThesisError):
        golden(seq="42")
    with pytest.raises(ThesisError):
        golden(seq=True)
    with pytest.raises(ThesisError):
        golden(horizon_min=0)


def test_policy_caps():
    from decimal import Decimal
    t = golden()
    with pytest.raises(ThesisError):
        validate(t, max_size_usd=Decimal("2.00"))
    with pytest.raises(ThesisError):
        validate(t, max_horizon_min=60)


def test_non_string_values_rejected():
    t = golden()
    t["seq"] = 42
    with pytest.raises(ThesisError):
        canonical_json(t)


def test_salt_length_enforced():
    with pytest.raises(ThesisError):
        digest(GOLDEN_CANONICAL, b"short")


def test_fmt_decimal_rounds_half_even():
    assert fmt_decimal("0.125", 2) == "0.12"
    assert fmt_decimal("0.135", 2) == "0.14"
