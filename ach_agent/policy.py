"""Binding triage rules for returned ACH deposits. No AI in this file.

The agent must call these rules and can never weaken them. It may ask for extra
human review, but it can't change an action or allow a retry.
DECISIONS.md explains every rule in plain English.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

from .analytics import days_between

MAX_REPRESENTMENTS = 2          # Nacha: R01/R09 may be re-presented at most twice in 180 days
REPEAT_WINDOW_DAYS = 90         # a second return inside this window is a pattern
NEW_ACCOUNT_DAYS = 30           # young accounts carry new-account fraud risk
UNSECURED_REVIEW_USD = 100.00   # an unsecured shortfall this large needs a person
LEVELS = ["low", "medium", "high"]

ACTIONS = [
    "represent_once",
    "stop_retries_and_contact_customer",
    "request_new_bank_link",
    "stop_debits_and_contact_customer",
    "freeze_and_escalate_to_fraud",
    "hold_and_escalate_to_fraud",
    "escalate_to_compliance",
    "escalate_to_operations",
]


@dataclass
class Decision:
    return_id: str
    action: str
    retry: bool = False
    restrict_buying_power: bool = False
    freeze_account: bool = False
    human_review: bool = False
    severity: str = "low"
    reasons: list = field(default_factory=list)
    exposure: dict = field(default_factory=dict)

    def raise_to(self, level: str) -> None:
        if LEVELS.index(level) > LEVELS.index(self.severity):
            self.severity = level

    def to_dict(self) -> dict:
        return asdict(self)


def decide(ret: dict, code_info: dict | None, account: dict | None, *,
           exposure: dict, linked: list[dict], earlier_returns: list[str], as_of: date) -> Decision:
    """The binding decision for one returned deposit.

    linked: accounts funded from the same bank account, each {"account_id", "unauthorized": bool}
    earlier_returns: other returns on this account earlier in today's batch
    """
    rid, code = ret["return_id"], ret["return_code"]

    if account is None:
        return Decision(rid, "escalate_to_operations", human_review=True, severity="high", exposure=exposure,
                        reasons=["Account not found, so the money at risk can't be measured."])

    category = code_info["category"] if code_info else "unknown"

    # 1. Base action from the return code
    if code_info is None:
        d = Decision(rid, "escalate_to_operations", restrict_buying_power=True, human_review=True, severity="medium",
                     reasons=[f"{code} is not a recognized Nacha return code, so a person must classify it."])
    elif category == "unauthorized":
        d = Decision(rid, "freeze_and_escalate_to_fraud", freeze_account=True, restrict_buying_power=True,
                     human_review=True, severity="high",
                     reasons=[f"{code}: the account holder says this debit wasn't authorized. "
                              "Possible fraud or account takeover. Never re-present."])
    elif category == "nsf":
        attempts = max((p.get("represent_attempts", 0) for p in account.get("prior_returns", [])
                        if p["code"] in ("R01", "R09") and days_between(p["date"], as_of) <= 180), default=0)
        if attempts >= MAX_REPRESENTMENTS:
            d = Decision(rid, "stop_retries_and_contact_customer", restrict_buying_power=True, human_review=True,
                         severity="medium",
                         reasons=[f"Already re-presented {attempts} times; Nacha allows at most {MAX_REPRESENTMENTS}."])
        else:
            d = Decision(rid, "represent_once", retry=True,
                         reasons=[f"{code}: not enough money in the bank account. Nacha allows re-presenting "
                                  f"up to {MAX_REPRESENTMENTS} times within 180 days."])
    elif category == "revoked":
        d = Decision(rid, "stop_debits_and_contact_customer", severity="medium",
                     reasons=[f"{code}: the customer revoked or stopped this payment. "
                              "Never debit again without new authorization."])
    elif category == "frozen":
        d = Decision(rid, "escalate_to_compliance", restrict_buying_power=True, human_review=True, severity="high",
                     reasons=[f"{code}: the bank account is frozen, possibly under OFAC sanctions rules. "
                              "Compliance must review."])
    else:  # bad_account
        d = Decision(rid, "request_new_bank_link",
                     reasons=[f"{code}: the bank details don't work. The customer must link a valid account."])
    d.exposure = exposure

    # 2. Money at risk
    deficit, uncovered = exposure.get("deficit") or 0, exposure.get("uncovered") or 0
    if deficit > 0:
        d.restrict_buying_power = True
        d.raise_to("medium")
        d.reasons.append(f"Reversing this deposit leaves a ${deficit:,.2f} deficit: the customer already used money "
                         f"that never arrived. Selling their positions could cover "
                         f"${exposure['covered_by_positions']:,.2f}; ${uncovered:,.2f} is unsecured.")
        if uncovered >= UNSECURED_REVIEW_USD:
            d.human_review = True
            d.raise_to("high")

    # 3. Shared bank accounts: the pattern one-at-a-time review misses
    risky = [l["account_id"] for l in linked if l["unauthorized"]]
    if risky and category != "unauthorized":
        d.action, d.retry = "hold_and_escalate_to_fraud", False
        d.restrict_buying_power = d.human_review = True
        d.raise_to("high")
        d.reasons.append(f"Funded from the same bank account as {', '.join(risky)}, which has an unauthorized "
                         "return. Re-presenting would likely trigger another unauthorized return, so hold it for "
                         "fraud review.")
    elif linked:
        d.human_review = True
        d.raise_to("medium")
        d.reasons.append(f"Shares a bank account with {', '.join(l['account_id'] for l in linked)}. "
                         "Review these accounts together.")

    # 4. Repeat returns and new accounts
    recent = [p for p in account.get("prior_returns", []) if days_between(p["date"], as_of) <= REPEAT_WINDOW_DAYS]
    if (recent or earlier_returns) and category != "nsf":
        d.human_review = True
        d.raise_to("high")
        d.reasons.append(f"Another return on this account within {REPEAT_WINDOW_DAYS} days. "
                         "One return can be a mistake; two is a pattern.")

    age = days_between(account["opened"], as_of)
    if age < NEW_ACCOUNT_DAYS and category in ("unauthorized", "bad_account"):
        d.human_review = True
        d.raise_to("high")
        d.reasons.append(f"Account is only {age} days old, a common profile for new-account fraud.")

    return d
