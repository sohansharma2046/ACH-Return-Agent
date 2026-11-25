"""Tools the agent can call. Each one is a plain Python function plus a schema
that tells Claude what the tool does and what inputs it takes."""

import csv
import json
from pathlib import Path

from .policy import decide

DATA = Path(__file__).resolve().parent.parent / "data"


def load_return_codes() -> dict:
    return json.loads((DATA / "return_codes.json").read_text())


def load_accounts() -> dict:
    return {k: v for k, v in json.loads((DATA / "accounts.json").read_text()).items() if not k.startswith("_")}


def load_batch(path: Path | None = None) -> list[dict]:
    with open(path or DATA / "returns_batch.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["amount"] = float(r["amount"])
    return rows


class Toolbox:
    """Holds the data and runs tool calls by name."""

    def __init__(self, batch: list[dict]):
        self.codes = load_return_codes()
        self.accounts = load_accounts()
        self.returns = {r["return_id"]: r for r in batch}
        self.notices: dict[str, str] = {}   # return_id -> drafted partner notice

    # --- tools -----------------------------------------------------------
    def lookup_return_code(self, code: str) -> dict:
        info = self.codes.get(code.upper())
        return {"code": code, "known": info is not None, **(info or {"note": "Not a recognized Nacha return code."})}

    def get_account(self, account_id: str) -> dict:
        acct = self.accounts.get(account_id)
        return {"account_id": account_id, "found": acct is not None, **(acct or {})}

    def get_policy_decision(self, return_id: str) -> dict:
        ret = self.returns.get(return_id)
        if ret is None:
            return {"error": f"Unknown return_id {return_id}"}
        d = decide(ret, self.codes.get(ret["return_code"]), self.accounts.get(ret["account_id"]))
        return {"return_id": return_id, "binding": True, **d.to_dict()}

    def save_partner_notice(self, return_id: str, notice: str) -> dict:
        if return_id not in self.returns:
            return {"error": f"Unknown return_id {return_id}"}
        self.notices[return_id] = notice.strip()
        return {"saved": True, "return_id": return_id}

    def run(self, name: str, args: dict) -> dict:
        fn = getattr(self, name, None)
        if fn is None or name.startswith("_") or name == "run":
            return {"error": f"No tool named {name}"}
        try:
            return fn(**args)
        except TypeError as e:
            return {"error": f"Bad arguments for {name}: {e}"}


TOOL_SCHEMAS = [
    {
        "name": "lookup_return_code",
        "description": "Look up a Nacha ACH return code (e.g. R01, R10): its meaning, category, return window, and whether it can be re-presented.",
        "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
    },
    {
        "name": "get_account",
        "description": "Get the brokerage account behind a returned deposit: partner app, account age, cash balance, instant buying power already used, and prior ACH returns.",
        "input_schema": {"type": "object", "properties": {"account_id": {"type": "string"}}, "required": ["account_id"]},
    },
    {
        "name": "get_policy_decision",
        "description": "Get the BINDING triage decision for one return from the firm's deterministic rules engine. You must call this for every return and must not contradict it.",
        "input_schema": {"type": "object", "properties": {"return_id": {"type": "string"}}, "required": ["return_id"]},
    },
    {
        "name": "save_partner_notice",
        "description": "Save a short notice to the partner app's operations team explaining what happened and what action is being taken. Plain, factual, no blame, no promises.",
        "input_schema": {"type": "object",
                         "properties": {"return_id": {"type": "string"}, "notice": {"type": "string"}},
                         "required": ["return_id", "notice"]},
    },
]
