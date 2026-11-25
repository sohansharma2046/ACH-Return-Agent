# Triage decisions: why each rule exists

These are business rules, not AI output. The agent must follow them.

| Return code | What it means | Action | Retry? | Restrict buying power? | Human review? |
|---|---|---|---|---|---|
| R01, R09 | Insufficient / uncollected funds | Re-present once | Yes (Nacha allows up to 2 in 180 days) | Only if the customer already traded with the deposit | No |
| R01, R09 after 2 re-presentments | Still no funds | Stop retries, contact customer | No | Yes | Yes |
| R02, R03, R04, R20 | Bank account closed, wrong, or the wrong type | Ask the customer to link a new bank account | No | Yes | Only if the account is new or this is a repeat |
| R07, R08 | Customer revoked authorization or stopped the payment | Stop debits, contact customer | **Never**: needs new authorization | Yes | No |
| R05, R10, R11, R29 | Customer says the debit wasn't authorized | Freeze the account, escalate to fraud | Never | Yes | **Always** |
| R16 | Receiving account frozen (may be OFAC) | Escalate to compliance | No | Yes | Always |
| Unknown code | Can't classify | Escalate to operations | No | Yes | Always |

## Modifiers that raise severity

- **Instant buying power already used.** Many apps let customers trade before an ACH deposit settles. If the deposit then bounces, the broker is short the money, so buying power is always restricted.
- **Second return within 90 days.** One return can be a mistake. Two is a pattern, so a person reviews it.
- **Account under 30 days old,** combined with an unauthorized or bad-account return. That's the classic new-account fraud profile.

## Why the AI doesn't make these calls

Return handling has hard regulatory limits. Examples: never re-debit after R07, at most two re-presentments for R01, and a 0.5% unauthorized return rate threshold. A model can misread a code or be talked into an exception, so these rules live in plain code that's tested (`tests/test_agent.py`). The AI's job is the parts that need judgment and language: investigating, explaining the decision, and writing the partner notice. Code then checks that the AI followed the policy before a person sees the result.
