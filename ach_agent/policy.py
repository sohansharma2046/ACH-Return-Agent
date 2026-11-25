"""Deterministic triage rules for returned ACH deposits.

These rules are the guardrail: the AI agent must call this policy and may not
override it. The AI explains the decision and drafts communications; it does not
make compliance calls on its own.

Every rule here is a business choice. See DECISIONS.md for the reasoning.
"""

from dataclasses import dataclass, field, asdict

MAX_REPRESENTMENTS = 2  # Nacha limit for R01/R09 within 180 days
REPEAT_RETURN_WINDOW_DAYS = 90


@dataclass
class Decision:
    action: str                      # what happens next
    retry: bool = False              # re-present the ACH debit?
    restrict_buying_power: bool = False
    freeze_account: bool = False
    human_review_required: bool = False
    severity: str = "low"            # low / medium / high
    reasons: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def _days_between(d1: str, d2: str) -> int:
    from datetime import date
    a, b = date.fromisoformat(d1), date.fromisoformat(d2)
    return abs((b - a).days)


def decide(ret: dict, code_info: dict | None, account: dict | None) -> Decision:
    """Return the binding decision for one returned ACH entry.

    ret: one row of the returns batch (return_code, amount, return_date, ...)
    code_info: the entry from return_codes.json, or None if the code is unknown
    account: the account record, or None if it can't be found
    """
    code = ret["return_code"]

    # Guardrail 1: anything we can't look up goes to a person.
    if account is None:
        return Decision("escalate_to_operations", human_review_required=True, severity="high",
                        reasons=["Account not found; cannot assess exposure."])
    if code_info is None:
        return Decision("escalate_to_operations", restrict_buying_power=True,
                        human_review_required=True, severity="medium",
                        reasons=[f"Unrecognized return code {code}; a person must classify it."])

    category = code_info["category"]
    used_unsettled = account.get("instant_buying_power_used", 0) > 0
    recent_returns = [r for r in account.get("prior_returns", [])
                      if _days_between(r["date"], ret["return_date"]) <= REPEAT_RETURN_WINDOW_DAYS]

    # Base decision by category
    if category == "unauthorized":
        d = Decision("freeze_and_escalate_to_fraud", freeze_account=True, restrict_buying_power=True,
                     human_review_required=True, severity="high",
                     reasons=[f"{code} means the customer says the debit was not authorized: possible fraud or account takeover.",
                              "Unauthorized returns count toward Nacha's 0.5% threshold."])
    elif category == "nsf":
        prior_attempts = max([r.get("represent_attempts", 0) for r in recent_returns
                              if r["code"] in ("R01", "R09")], default=0)
        if prior_attempts >= MAX_REPRESENTMENTS:
            d = Decision("stop_retries_and_contact_customer", restrict_buying_power=True,
                         human_review_required=True, severity="medium",
                         reasons=[f"Already re-presented {prior_attempts} times; Nacha allows at most {MAX_REPRESENTMENTS}."])
        else:
            d = Decision("represent_once", retry=True, severity="low",
                         reasons=["Insufficient or uncollected funds can be re-presented (up to 2 times in 180 days)."])
    elif category == "revoked":
        d = Decision("stop_debits_and_contact_customer", restrict_buying_power=True, severity="medium",
                     reasons=[f"{code}: the customer revoked or stopped the payment. Never re-debit without new authorization."])
    elif category == "frozen":
        d = Decision("escalate_to_compliance", restrict_buying_power=True, human_review_required=True,
                     severity="high", reasons=["Receiving account is frozen; may be OFAC-related. Compliance must review."])
    else:  # administrative: closed / wrong / invalid account
        d = Decision("request_new_bank_link", restrict_buying_power=True, severity="low",
                     reasons=[f"{code}: the bank details don't work. The customer must link a valid account."])

    # Modifiers that raise the stakes
    if used_unsettled:
        d.restrict_buying_power = True
        d.reasons.append(f"Customer already used ${account['instant_buying_power_used']:,.2f} of instant buying power "
                         "before the deposit settled, so the broker is exposed to a loss.")
        if d.severity == "low":
            d.severity = "medium"

    if recent_returns and category != "nsf":
        d.human_review_required = True
        d.severity = "high"
        d.reasons.append(f"Second return on this account within {REPEAT_RETURN_WINDOW_DAYS} days: pattern risk.")

    if account.get("account_age_days", 999) < 30 and category in ("unauthorized", "administrative"):
        d.human_review_required = True
        d.severity = "high"
        d.reasons.append("Account is under 30 days old: new-account fraud risk.")

    return d
