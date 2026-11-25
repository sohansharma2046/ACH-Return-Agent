"""The agent's tools.

Read tools look things up. The two write tools only record drafts (a partner
notice, a briefing). Nothing here moves money or changes an account: every
action waits for a person to approve it.
"""

from __future__ import annotations

import re

from . import analytics
from .policy import ACTIONS, decide

BANNED_WORDS = ["fraudster", "criminal", "stole", "scam", "guarantee", "promise"]  # no accusations, no promises
MAX_NOTICE_WORDS = 90


class Toolbox:
    """The agent's view of the world, plus a log of every tool call."""

    def __init__(self, data):
        self.codes = data.return_codes()
        self.accounts = data.accounts()
        self.batch = sorted(data.returned_deposits(), key=lambda r: (r["return_date"], r["return_id"]))
        self.returns = {r["return_id"]: r for r in self.batch}
        self.as_of = analytics.as_of(self.batch)
        self.exposure = analytics.exposures(self.batch, self.accounts)
        self.partner_risk = analytics.partner_rates(self.batch, self.accounts, data.partner_volumes(), self.codes)
        self.handbook = analytics.handbook_sections(data.handbook())
        self.decisions = {r["return_id"]: self._decide(i, r) for i, r in enumerate(self.batch)}
        self.notices: dict[str, dict] = {}
        self.briefing: dict | None = None
        self.calls: list[dict] = []

    # ------------------------------------------------------------ helpers
    def _returns_on(self, account_id: str) -> list[dict]:
        return [r for r in self.batch if r["account_id"] == account_id]

    def _has_unauthorized(self, account_id: str) -> bool:
        acct = self.accounts.get(account_id, {})
        codes = [r["return_code"] for r in self._returns_on(account_id)]
        codes += [p["code"] for p in acct.get("prior_returns", [])]
        return any((self.codes.get(c) or {}).get("category") == "unauthorized" for c in codes)

    def _decide(self, index: int, r: dict):
        linked = [{"account_id": a, "unauthorized": self._has_unauthorized(a)}
                  for a in analytics.linked_accounts(r["account_id"], self.accounts)]
        earlier = [x["return_id"] for x in self.batch[:index] if x["account_id"] == r["account_id"]]
        return decide(r, self.codes.get(r["return_code"]), self.accounts.get(r["account_id"]),
                      exposure=self.exposure[r["return_id"]], linked=linked, earlier_returns=earlier,
                      as_of=self.as_of)

    def run(self, name: str, args: dict) -> dict:
        """Run a tool by name and log the call."""
        if name not in TOOL_NAMES:
            out = {"error": f"No tool named {name}"}
        else:
            try:
                out = getattr(self, name)(**(args or {}))
            except TypeError as e:
                out = {"error": f"Bad arguments for {name}: {e}"}
        self.calls.append({"tool": name, "args": args or {}, "error": "error" in out})
        return out

    # --------------------------------------------------------- read tools
    def lookup_return_code(self, code: str) -> dict:
        info = self.codes.get(code.strip().upper())
        if info is None:
            return {"code": code, "known": False, "note": "Not a recognized Nacha return code."}
        return {"code": code.strip().upper(), "known": True, **info}

    def get_account(self, account_id: str) -> dict:
        a = self.accounts.get(account_id)
        if a is None:
            return {"account_id": account_id, "found": False}
        return {"account_id": account_id, "found": True, "partner": a["partner"],
                "account_age_days": analytics.days_between(a["opened"], self.as_of),
                "cash_balance": a["cash_balance"], "positions_value": a["positions_value"],
                "prior_returns": a["prior_returns"],
                "returns_in_todays_batch": [r["return_id"] for r in self._returns_on(account_id)]}

    def find_linked_accounts(self, account_id: str) -> dict:
        return {"account_id": account_id, "shares_bank_account_with": [
            {"account_id": a, "partner": self.accounts[a]["partner"],
             "account_age_days": analytics.days_between(self.accounts[a]["opened"], self.as_of),
             "returns_today": [f"{r['return_id']} ({r['return_code']})" for r in self._returns_on(a)],
             "prior_return_codes": [p["code"] for p in self.accounts[a]["prior_returns"]],
             "has_unauthorized_return": self._has_unauthorized(a)}
            for a in analytics.linked_accounts(account_id, self.accounts)]}

    def get_policy_decision(self, return_id: str) -> dict:
        d = self.decisions.get(return_id)
        if d is None:
            return {"error": f"Unknown return_id {return_id}"}
        return {"binding": True, **d.to_dict()}

    def get_partner_risk(self, partner: str = "") -> dict:
        rows = [p for p in self.partner_risk if not partner or p["partner"].lower() == partner.lower()]
        return {"window": "trailing 60 days, including today's returns",
                "nacha_limits_pct": analytics.NACHA_LIMITS, "partners": rows}

    def search_policy_handbook(self, query: str) -> dict:
        return {"query": query, "sections": analytics.search_sections(self.handbook, query)}

    # -------------------------------------------- write tools (drafts only)
    def save_partner_notice(self, return_id: str, action_stated: str, notice: str) -> dict:
        if return_id not in self.returns:
            return {"error": f"Unknown return_id {return_id}"}
        checks = self.check_notice(return_id, action_stated, notice)
        failed = [k for k, ok in checks.items() if not ok]
        self.notices[return_id] = {"action_stated": action_stated, "notice": notice.strip(), "checks": checks,
                                   "status": "blocked" if failed else "ready"}
        return {"saved": True, "status": self.notices[return_id]["status"], "failed_checks": failed,
                "hint": "Fix the failed checks and save again." if failed else ""}

    def check_notice(self, return_id: str, action_stated: str, notice: str) -> dict:
        r, d = self.returns[return_id], self.decisions[return_id]
        text = notice.lower()
        amounts = {float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", notice)}
        return {
            "action_matches_policy": action_stated == d.action,
            "mentions_return_code": r["return_code"].lower() in text,
            "mentions_amount": round(r["amount"], 2) in amounts,
            "short_enough": len(notice.split()) <= MAX_NOTICE_WORDS,
            "neutral_language": not any(w in text for w in BANNED_WORDS),
        }

    def submit_briefing(self, headline: str, key_risks: list, leadership_summary: str,
                        extra_review: list | None = None) -> dict:
        added, ignored = [], []
        for item in extra_review or []:
            rid = (item or {}).get("return_id")
            (added if rid in self.decisions else ignored).append(
                {"return_id": rid, "reason": (item or {}).get("reason", "")})
        self.briefing = {"headline": headline, "key_risks": key_risks or [],
                         "leadership_summary": leadership_summary, "extra_review": added}
        return {"saved": True, "extra_reviews_added": [a["return_id"] for a in added],
                "ignored_unknown_return_ids": [i["return_id"] for i in ignored]}


def _schema(props: dict, required: list) -> dict:
    return {"type": "object", "properties": props, "required": required}


TOOLS = [
    {"name": "lookup_return_code",
     "description": "Look up a Nacha ACH return code (e.g. R01, R10): what it means, its category, whether it can be "
                    "re-presented, and which Nacha return-rate limit it counts toward.",
     "input_schema": _schema({"code": {"type": "string"}}, ["code"])},
    {"name": "get_account",
     "description": "The brokerage account behind a return: partner app, age in days, cash balance, value of "
                    "positions, prior ACH returns and other returns today. Contains no personal information.",
     "input_schema": _schema({"account_id": {"type": "string"}}, ["account_id"])},
    {"name": "find_linked_accounts",
     "description": "Other customer accounts funded from the same bank account (matched by a one-way fingerprint), "
                    "with their returns. One bank account behind several customers can signal fraud.",
     "input_schema": _schema({"account_id": {"type": "string"}}, ["account_id"])},
    {"name": "get_policy_decision",
     "description": "The BINDING decision for one return from the firm's rules engine: action, retry, restrictions, "
                    "severity, reasons, and money at risk. Call it for every return. Never contradict or weaken it.",
     "input_schema": _schema({"return_id": {"type": "string"}}, ["return_id"])},
    {"name": "get_partner_risk",
     "description": "Each partner program's ACH return rates over the trailing 60 days (including today) against "
                    "Nacha limits: unauthorized 0.5%, administrative 3%, overall 15%. Leave partner empty for all.",
     "input_schema": _schema({"partner": {"type": "string"}}, [])},
    {"name": "search_policy_handbook",
     "description": "Search the firm's ACH returns handbook and get the most relevant sections, to explain or cite "
                    "the firm's rules.",
     "input_schema": _schema({"query": {"type": "string"}}, ["query"])},
    {"name": "save_partner_notice",
     "description": "Save the notice for the partner app's operations team about one return. action_stated must "
                    "equal the policy action. Under 80 words, factual, include the amount, return code and next "
                    "step, no accusations or promises. The result lists failed checks so you can fix and save again.",
     "input_schema": _schema({"return_id": {"type": "string"},
                              "action_stated": {"type": "string", "enum": ACTIONS},
                              "notice": {"type": "string"}}, ["return_id", "action_stated", "notice"])},
    {"name": "submit_briefing",
     "description": "Submit the final briefing for the operations team. Call once, after every notice is saved.",
     "input_schema": _schema({
         "headline": {"type": "string", "description": "One sentence: the most important thing today."},
         "key_risks": {"type": "array", "description": "The 2-4 most important risks, most important first.",
                       "items": _schema({"title": {"type": "string"},
                                         "return_ids": {"type": "array", "items": {"type": "string"}},
                                         "why": {"type": "string"}}, ["title", "return_ids", "why"])},
         "extra_review": {"type": "array",
                          "description": "Optional: returns that need human review although the policy doesn't "
                                         "require it. This can only add caution.",
                          "items": _schema({"return_id": {"type": "string"}, "reason": {"type": "string"}},
                                           ["return_id", "reason"])},
         "leadership_summary": {"type": "string", "description": "3-5 plain-English sentences for a manager."}},
         ["headline", "key_risks", "leadership_summary"])},
]
TOOL_NAMES = {t["name"] for t in TOOLS}
