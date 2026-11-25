# ACH returns handbook

The firm's rules for returned ACH deposits. People read this file, and the agent searches it (the `search_policy_handbook` tool) to cite the rules. The binding version of every rule is in code: `ach_agent/policy.py`.

| Return code | What it means | Action | Re-present? | Person needed? |
|---|---|---|---|---|
| R01, R09 | Not enough money in the bank account | Re-present once | Yes, up to 2 times in 180 days | Only if risk factors apply |
| R01, R09 after 2 re-presentments | Still no money | Stop retries, contact customer | No | Yes |
| R02, R03, R04, R20 | Bank account closed, wrong, or wrong type | Ask the customer to link a new bank account | No | Only if risk factors apply |
| R07, R08 | Customer revoked or stopped the payment | Stop debits, contact customer | Never without new authorization | Only if risk factors apply |
| R05, R10, R11, R29 | Account holder says the debit wasn't authorized | Freeze the account, escalate to fraud | Never | Always |
| R16 | Bank account frozen, possibly under OFAC sanctions rules | Escalate to compliance | No | Always |
| Unknown code | Can't be classified | Escalate to operations | No | Always |

## Core principle: the AI can add caution, never remove it

Return handling has hard limits: never re-debit after R07, at most two re-presentments after R01, and Nacha return-rate limits. A language model can misread a code or be talked into an exception, so the rules engine makes every binding decision in tested code. The agent investigates, connects cases, writes notices and briefs the team. It may ask for extra human review, but it can never change an action, allow a retry, or skip a review the rules require. Code checks this after every run, and a person approves every action.

## Insufficient funds (R01, R09)

The customer's bank account didn't have the money. Nacha allows re-presenting the debit up to two times within 180 days of the original settlement date. Re-present once. After two re-presentments, stop retrying, restrict buying power and contact the customer.

## Bad bank details (R02, R03, R04, R20)

The bank account is closed (R02), doesn't exist (R03), has an invalid number (R04) or can't take ACH debits (R20). Retrying can't work. Ask the customer to link a valid account. R02, R03 and R04 count toward Nacha's 3% administrative return rate limit.

## Revoked or stopped payments (R07, R08)

The customer told their bank to stop or revoke the payment. Never debit again without new authorization. R07 counts toward Nacha's 0.5% unauthorized return rate limit, the strictest one.

## Unauthorized debits (R05, R10, R11, R29)

The account holder says they never authorized the debit. This is the signature of fraud and account takeover. Freeze the account, escalate to the fraud team, never re-present. These count toward the 0.5% unauthorized limit.

## Frozen accounts (R16)

The receiving bank froze the account, sometimes because of OFAC sanctions screening. Compliance must review before anything else happens.

## Unknown codes

If a code isn't recognized, restrict buying power and send it to operations. Never guess.

## Money at risk: when the customer already traded

Many apps give instant buying power: customers can buy stock before an ACH deposit settles. If the deposit is returned, the firm has to take back money the customer may have already spent. The engine measures three numbers for every return:

- **Deficit:** how far the account goes below zero when the deposit is reversed.
- **Covered by positions:** how much of that the customer's investments could cover if sold.
- **Unsecured shortfall:** what's left, which is a likely loss.

Reversals on the same account stack: two small returns can overdraw an account that could cover either one alone. Any deficit restricts buying power. An unsecured shortfall of $100 or more needs a person.

## Shared bank accounts

When several customer accounts are funded from the same bank account, review them together. If any of them has an unauthorized return, hold every return on the others for fraud review and don't re-present them. A routine-looking insufficient-funds return is not routine when its bank account just funded a fraud report: re-presenting it would likely create another unauthorized return. Bank accounts are compared by one-way fingerprint, so no one sees the account numbers.

## Repeat returns and new accounts

One return can be a mistake; two is a pattern. A second non-insufficient-funds return on the same account within 90 days (including two in today's batch) needs a person. Accounts under 30 days old with an unauthorized or bad-account return also need a person, because that is the common profile of new-account fraud.

## Partner return-rate limits (Nacha)

Nacha limits the share of ACH debits that come back, measured over 60 days: 0.5% unauthorized, 3% administrative, 15% overall. Going over can bring Nacha inquiries and fines and can put the ability to pull ACH at risk. The engine tracks every partner program against each limit and flags it at 80% (watch) and 100% (over), so the team can tighten funding controls before a partner crosses a line.

## Partner notices

Every return gets a short notice for the partner app's operations team: the amount, the return code and the next step. Notices are factual: no accusations ("fraudster"), no promises ("guarantee"). Code blocks any notice that states a different action than the rules engine, or that fails these checks.

## Privacy

The agent never sees names, Social Security numbers or bank account numbers. Accounts are IDs, and bank accounts are one-way fingerprints.
