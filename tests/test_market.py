"""price_info source handling (liquidity is required by the firewall)."""
from decimal import Decimal

import pytest

import oath_core.market as market
from oath_core.clawpump import ClawPumpError

SOL = "So11111111111111111111111111111111111111112"


class CP:
    def __init__(self, resp=None, err=False):
        self.resp, self.err = resp, err

    def call(self, tool, args):
        if self.err:
            raise ClawPumpError("down")
        return self.resp


class Resp:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise market.httpx.HTTPStatusError("x", request=None, response=None)

    def json(self):
        return self.body


@pytest.fixture
def jup(monkeypatch):
    state = {"body": {SOL: {"usdPrice": 122.5, "liquidity": 9.6e8}}, "fail": False}

    def get(url, params=None, timeout=None):
        if state["fail"]:
            raise market.httpx.ConnectError("down")
        return Resp(state["body"])
    monkeypatch.setattr(market.httpx, "get", get)
    return state


def test_clawpump_with_liquidity_used_as_is(jup):
    info = market.price_info(CP({"prices": {SOL: {"usd": 121.9, "liquidity": 7.2e9, "source": "birdeye"}}}), SOL)
    assert info.usd == Decimal("121.9") and info.liquidity_usd == Decimal("7200000000.0")
    assert info.source == "clawpump:birdeye"


def test_coingecko_path_without_liquidity_takes_jupiter_liquidity(jup):
    """Live 2026-09-27: ClawPump answered from coingecko with no liquidity field."""
    info = market.price_info(CP({"prices": {SOL: {"usd": 121.94, "source": "coingecko"}}}), SOL)
    assert info.usd == Decimal("121.94")                     # price stays ClawPump's
    assert info.liquidity_usd == Decimal("960000000.0")       # liquidity from Jupiter
    assert info.source == "clawpump:coingecko+jupiter-liquidity"


def test_no_liquidity_anywhere_stays_none_so_firewall_blocks(jup):
    jup["fail"] = True
    info = market.price_info(CP({"prices": {SOL: {"usd": 121.94, "source": "coingecko"}}}), SOL)
    assert info.usd == Decimal("121.94") and info.liquidity_usd is None


def test_clawpump_down_falls_back_to_jupiter(jup):
    info = market.price_info(CP(err=True), SOL)
    assert info.source == "jupiter" and info.usd == Decimal("122.5")


def test_everything_down_is_none(jup):
    jup["fail"] = True
    assert market.price_info(CP(err=True), SOL) is None
