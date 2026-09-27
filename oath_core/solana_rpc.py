"""Minimal Solana JSON-RPC client (httpx). Every failure raises; callers fail closed."""
from __future__ import annotations

import time

import httpx


class RpcError(RuntimeError):
    pass


class Rpc:
    def __init__(self, url: str, timeout: float = 20.0, retries: int = 4):
        self.url = url
        self.retries = retries
        self._http = httpx.Client(timeout=timeout)

    def call(self, method: str, params: list | None = None):
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
        delay = 1.0
        for attempt in range(self.retries + 1):
            try:
                r = self._http.post(self.url, json=body)
            except httpx.HTTPError as e:
                if attempt == self.retries:
                    raise RpcError(f"{method}: {e!r}") from e
            else:
                if r.status_code == 429 or r.status_code >= 500:
                    if attempt == self.retries:
                        raise RpcError(f"{method}: HTTP {r.status_code}")
                else:
                    r.raise_for_status()
                    data = r.json()
                    if "error" in data:
                        raise RpcError(f"{method}: {data['error']}")
                    return data["result"]
            time.sleep(delay)
            delay *= 2
        raise RpcError(f"{method}: exhausted retries")

    # --- reads --------------------------------------------------------------

    def get_latest_blockhash(self) -> str:
        return self.call("getLatestBlockhash", [{"commitment": "confirmed"}])["value"]["blockhash"]

    def get_balance(self, pubkey: str) -> int:
        return self.call("getBalance", [pubkey, {"commitment": "confirmed"}])["value"]

    def get_min_rent(self, data_len: int) -> int:
        return self.call("getMinimumBalanceForRentExemption", [data_len])

    def get_fee_for_message(self, message_b64: str) -> int:
        fee = self.call("getFeeForMessage", [message_b64, {"commitment": "confirmed"}])["value"]
        if fee is None:
            raise RpcError("getFeeForMessage returned null (blockhash expired?)")
        return fee

    def get_account_info(self, pubkey: str) -> dict | None:
        return self.call("getAccountInfo", [pubkey, {"encoding": "jsonParsed", "commitment": "confirmed"}])["value"]

    def get_transaction(self, sig: str) -> dict | None:
        return self.call("getTransaction", [sig, {"encoding": "jsonParsed", "commitment": "confirmed",
                                                  "maxSupportedTransactionVersion": 0}])

    def wait_transaction(self, sig: str, timeout_s: float = 60.0) -> dict:
        """Poll until the tx is readable at `confirmed`. Raises on timeout."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            tx = self.get_transaction(sig)
            if tx:
                return tx
            time.sleep(2)
        raise RpcError(f"transaction {sig} not found within {timeout_s}s")

    def get_signatures_for_address(self, address: str, limit: int = 1000) -> list[dict]:
        """All signatures touching `address`, newest first (paginated)."""
        out: list[dict] = []
        before = None
        while True:
            opts = {"limit": min(limit, 1000), "commitment": "confirmed"}
            if before:
                opts["before"] = before
            page = self.call("getSignaturesForAddress", [address, opts])
            out.extend(page)
            if len(page) < opts["limit"]:
                return out
            before = page[-1]["signature"]

    # --- writes -------------------------------------------------------------

    def send_transaction(self, tx_b64: str) -> str:
        return self.call("sendTransaction", [tx_b64, {"encoding": "base64", "skipPreflight": False,
                                                      "preflightCommitment": "confirmed", "maxRetries": 5}])

    def simulate_transaction(self, tx_b64: str) -> dict:
        return self.call("simulateTransaction", [tx_b64, {"encoding": "base64", "sigVerify": True,
                                                          "commitment": "confirmed"}])["value"]

    def confirm(self, sig: str, timeout_s: float = 90.0) -> int:
        """Wait for `confirmed`; return slot. Raises if the tx failed or never confirmed."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            st = self.call("getSignatureStatuses", [[sig], {"searchTransactionHistory": True}])["value"][0]
            if st:
                if st.get("err"):
                    raise RpcError(f"transaction {sig} failed: {st['err']}")
                if st.get("confirmationStatus") in ("confirmed", "finalized"):
                    return st["slot"]
            time.sleep(2)
        raise RpcError(f"transaction {sig} not confirmed within {timeout_s}s")
