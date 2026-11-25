"""The numbers behind every decision: money at risk, shared bank accounts, and
partner return rates against Nacha limits. All deterministic, no AI."""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path

NACHA_LIMITS = {"unauthorized": 0.5, "administrative": 3.0, "overall": 15.0}  # % of ACH debits, trailing 60 days
WATCH_AT = 0.8                                                               # flag at 80% of a limit
STATUS_ORDER = ["ok", "watch", "over"]
SQL = (Path(__file__).parent / "partner_rates.sql").read_text()


def days_between(start: str, end) -> int:
    end = end if isinstance(end, date) else date.fromisoformat(end)
    return (end - date.fromisoformat(start)).days


def as_of(batch: list[dict]) -> date:
    return max(date.fromisoformat(r["return_date"]) for r in batch)


# ---------------------------------------------------------------- money at risk
def exposures(batch: list[dict], accounts: dict) -> dict:
    """What happens to each account when its deposit is reversed.

    deficit: money the customer already used that never arrived.
    covered_by_positions: part of the deficit their stocks could cover if sold.
    uncovered: the unsecured shortfall, a likely loss.

    Reversals on one account stack, so two small returns can overdraw an
    account that could absorb either one alone."""
    cash = {a: v["cash_balance"] for a, v in accounts.items()}
    positions = {a: v["positions_value"] for a, v in accounts.items()}
    out = {}
    for r in sorted(batch, key=lambda r: (r["return_date"], r["return_id"])):
        acct = r["account_id"]
        if acct not in cash:
            out[r["return_id"]] = {"deficit": None, "covered_by_positions": None, "uncovered": None}
            continue
        deficit = max(0.0, r["amount"] - max(cash[acct], 0.0))
        cash[acct] -= r["amount"]
        covered = min(deficit, positions[acct])
        positions[acct] -= covered
        out[r["return_id"]] = {"deficit": round(deficit, 2),
                               "covered_by_positions": round(covered, 2),
                               "uncovered": round(deficit - covered, 2)}
    return out


# ---------------------------------------------------------- shared bank accounts
def linked_accounts(account_id: str, accounts: dict) -> list[str]:
    """Other customer accounts funded from the same bank account."""
    fp = accounts.get(account_id, {}).get("bank_fingerprint")
    return sorted(a for a, v in accounts.items() if fp and a != account_id and v.get("bank_fingerprint") == fp)


def shared_bank_groups(accounts: dict) -> list[list[str]]:
    groups: dict[str, list[str]] = {}
    for a, v in accounts.items():
        groups.setdefault(v.get("bank_fingerprint"), []).append(a)
    return [sorted(g) for fp, g in groups.items() if fp and len(g) > 1]


# --------------------------------------------------- partner Nacha return rates
def partner_rates(batch: list[dict], accounts: dict, partners: dict, codes: dict) -> list[dict]:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE partners (partner TEXT, ach_debits_60d INT, unauthorized_returns_60d INT,"
               " administrative_returns_60d INT, total_returns_60d INT)")
    db.executemany("INSERT INTO partners VALUES (?, ?, ?, ?, ?)",
                   [(p, v["ach_debits_60d"], v["unauthorized_returns_60d"], v["administrative_returns_60d"],
                     v["total_returns_60d"]) for p, v in partners.items()])
    db.execute("CREATE TABLE todays_returns (return_id TEXT, partner TEXT, nacha_rate TEXT)")
    db.executemany("INSERT INTO todays_returns VALUES (?, ?, ?)",
                   [(r["return_id"], accounts.get(r["account_id"], {}).get("partner"),
                     (codes.get(r["return_code"]) or {}).get("nacha_rate")) for r in batch])

    out = []
    for partner, debits, unauthorized, administrative, total in db.execute(SQL):
        metrics = {}
        for name, count in (("unauthorized", unauthorized), ("administrative", administrative), ("overall", total)):
            rate = 100.0 * count / debits if debits else 0.0
            limit = NACHA_LIMITS[name]
            status = "over" if rate >= limit else "watch" if rate >= WATCH_AT * limit else "ok"
            metrics[name] = {"returns": count, "rate_pct": round(rate, 2), "limit_pct": limit, "status": status}
        worst = max((m["status"] for m in metrics.values()), key=STATUS_ORDER.index)
        out.append({"partner": partner, "ach_debits_60d": debits, "status": worst, "metrics": metrics})
    db.close()
    return out


# ------------------------------------------------------------------- totals
def totals(batch: list[dict], exposure: dict, decisions: list[dict]) -> dict:
    def total(key):
        return round(sum((exposure[r["return_id"]][key] or 0) for r in batch), 2)
    return {
        "returns": len(batch),
        "total_returned": round(sum(r["amount"] for r in batch), 2),
        "deficits": total("deficit"),
        "covered_by_positions": total("covered_by_positions"),
        "uncovered": total("uncovered"),
        "need_human_review": sum(d["human_review"] for d in decisions),
        "fraud_escalations": sum("fraud" in d["action"] for d in decisions),
        "high_severity": sum(d["severity"] == "high" for d in decisions),
    }


# ------------------------------------------------- handbook search (retrieval)
def handbook_sections(markdown: str) -> list[dict]:
    parts = re.split(r"^## ", markdown, flags=re.M)[1:]
    return [{"title": p.split("\n", 1)[0].strip(), "text": p.split("\n", 1)[1].strip() if "\n" in p else ""}
            for p in parts]


def search_sections(sections: list[dict], query: str, k: int = 2) -> list[dict]:
    """Simple keyword retrieval: rank handbook sections by query words they contain."""
    words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2 or re.fullmatch(r"r\d\d", w)}
    scored = []
    for i, s in enumerate(sections):
        text = (s["title"] + " " + s["text"]).lower()
        score = sum(text.count(w) for w in words) + 3 * sum(w in s["title"].lower() for w in words)
        if score:
            scored.append((-score, i, s))
    return [s for _, _, s in sorted(scored)[:k]]
