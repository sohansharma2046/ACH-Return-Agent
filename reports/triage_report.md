# ACH return triage report

Generated 2026-11-25 14:17 · mode: offline (rules only) · 8 returns

| Return | Account | Amount | Code | Severity | Action | Human review | Decision |
|---|---|---:|---|---|---|---|---|
| RET-003 | ACC-1003 | $1,000.00 | R10 | high | freeze_and_escalate_to_fraud | required | auto-approved |
| RET-006 | ACC-1006 | $200.00 | R03 | high | request_new_bank_link | required | auto-approved |
| RET-007 | ACC-1007 | $75.00 | R16 | high | escalate_to_compliance | required | auto-approved |
| RET-002 | ACC-1002 | $500.00 | R01 | medium | stop_retries_and_contact_customer | required | auto-approved |
| RET-005 | ACC-1005 | $250.00 | R07 | medium | stop_debits_and_contact_customer | - | auto-approved |
| RET-008 | ACC-1001 | $40.00 | R77 | medium | escalate_to_operations | required | auto-approved |
| RET-001 | ACC-1001 | $100.00 | R01 | low | represent_once | - | auto-approved |
| RET-004 | ACC-1004 | $250.00 | R02 | low | request_new_bank_link | - | auto-approved |

## RET-003: R10, $1,000.00

**Action:** freeze_and_escalate_to_fraud  
**Why:** R10 means the customer says the debit was not authorized: possible fraud or account takeover. Unauthorized returns count toward Nacha's 0.5% threshold. Customer already used $1,000.00 of instant buying power before the deposit settled, so the broker is exposed to a loss. Account is under 30 days old: new-account fraud risk.

**Summary:** R10 means the customer says the debit was not authorized: possible fraud or account takeover.

**Partner notice:** Deposit of $1,000.00 for account ACC-1003 was returned (R10: Customer Advises Originator Not Known / Not Authorized). Action: freeze and escalate to fraud. Buying power is restricted until resolved.

**Agent checks:** called_policy ✓, action_matches_policy ✓, notice_drafted ✓
**Tools called:** lookup_return_code → get_account → get_policy_decision

## RET-006: R03, $200.00

**Action:** request_new_bank_link  
**Why:** R03: the bank details don't work. The customer must link a valid account. Customer already used $200.00 of instant buying power before the deposit settled, so the broker is exposed to a loss. Second return on this account within 90 days: pattern risk.

**Summary:** R03: the bank details don't work. The customer must link a valid account.

**Partner notice:** Deposit of $200.00 for account ACC-1006 was returned (R03: No Account / Unable to Locate Account). Action: request new bank link. Buying power is restricted until resolved.

**Agent checks:** called_policy ✓, action_matches_policy ✓, notice_drafted ✓
**Tools called:** lookup_return_code → get_account → get_policy_decision

## RET-007: R16, $75.00

**Action:** escalate_to_compliance  
**Why:** Receiving account is frozen; may be OFAC-related. Compliance must review.

**Summary:** Receiving account is frozen; may be OFAC-related. Compliance must review.

**Partner notice:** Deposit of $75.00 for account ACC-1007 was returned (R16: Account Frozen / Entry Returned per OFAC Instruction). Action: escalate to compliance. Buying power is restricted until resolved.

**Agent checks:** called_policy ✓, action_matches_policy ✓, notice_drafted ✓
**Tools called:** lookup_return_code → get_account → get_policy_decision

## RET-002: R01, $500.00

**Action:** stop_retries_and_contact_customer  
**Why:** Already re-presented 2 times; Nacha allows at most 2. Customer already used $480.00 of instant buying power before the deposit settled, so the broker is exposed to a loss.

**Summary:** Already re-presented 2 times; Nacha allows at most 2.

**Partner notice:** Deposit of $500.00 for account ACC-1002 was returned (R01: Insufficient Funds). Action: stop retries and contact customer. Buying power is restricted until resolved.

**Agent checks:** called_policy ✓, action_matches_policy ✓, notice_drafted ✓
**Tools called:** lookup_return_code → get_account → get_policy_decision

## RET-005: R07, $250.00

**Action:** stop_debits_and_contact_customer  
**Why:** R07: the customer revoked or stopped the payment. Never re-debit without new authorization. Customer already used $250.00 of instant buying power before the deposit settled, so the broker is exposed to a loss.

**Summary:** R07: the customer revoked or stopped the payment. Never re-debit without new authorization.

**Partner notice:** Deposit of $250.00 for account ACC-1005 was returned (R07: Authorization Revoked by Customer). Action: stop debits and contact customer. Buying power is restricted until resolved.

**Agent checks:** called_policy ✓, action_matches_policy ✓, notice_drafted ✓
**Tools called:** lookup_return_code → get_account → get_policy_decision

## RET-008: R77, $40.00

**Action:** escalate_to_operations  
**Why:** Unrecognized return code R77; a person must classify it.

**Summary:** Unrecognized return code R77; a person must classify it.

**Partner notice:** Deposit of $40.00 for account ACC-1001 was returned (R77: unrecognized code). Action: escalate to operations. Buying power is restricted until resolved.

**Agent checks:** called_policy ✓, action_matches_policy ✓, notice_drafted ✓
**Tools called:** lookup_return_code → get_account → get_policy_decision

## RET-001: R01, $100.00

**Action:** represent_once  
**Why:** Insufficient or uncollected funds can be re-presented (up to 2 times in 180 days).

**Summary:** Insufficient or uncollected funds can be re-presented (up to 2 times in 180 days).

**Partner notice:** Deposit of $100.00 for account ACC-1001 was returned (R01: Insufficient Funds). Action: represent once.

**Agent checks:** called_policy ✓, action_matches_policy ✓, notice_drafted ✓
**Tools called:** lookup_return_code → get_account → get_policy_decision

## RET-004: R02, $250.00

**Action:** request_new_bank_link  
**Why:** R02: the bank details don't work. The customer must link a valid account.

**Summary:** R02: the bank details don't work. The customer must link a valid account.

**Partner notice:** Deposit of $250.00 for account ACC-1004 was returned (R02: Account Closed). Action: request new bank link. Buying power is restricted until resolved.

**Agent checks:** called_policy ✓, action_matches_policy ✓, notice_drafted ✓
**Tools called:** lookup_return_code → get_account → get_policy_decision
