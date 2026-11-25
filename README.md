# ACH Return Triage Agent

An AI agent that helps a brokerage operations team handle **returned ACH deposits**: the bank transfers that bounce days after a customer has already started investing.

> **About this project** *(Sohan: write 3–4 sentences here in your own words: why you picked this problem, what you learned from treasury management, and what surprised you while building it.)*

## The problem

When someone funds an investing app by ACH, the money takes days to settle, but many apps let customers trade right away. If the deposit is later returned (insufficient funds, closed account, "I never authorized this"), the broker is exposed to a loss and has to act fast. The right action depends on the return code, Nacha rules, and the customer's history. Getting it wrong means either losing money or freezing an innocent customer.

Today an analyst works through these one by one. This agent does the investigation and paperwork, and a person approves each action.

## How it works

```
returned deposit
     │
     ▼
 Claude agent ──► lookup_return_code   (what does R10 mean? can it be retried?)
     │       ──► get_account          (new account? already traded? prior returns?)
     │       ──► get_policy_decision  (BINDING rules engine decides the action)
     │       ──► save_partner_notice  (drafts a note to the partner app)
     ▼
 guardrail check: did the agent call the policy, and does its answer match?
     │
     ▼
 human reviewer approves / rejects ──► triage report (worst cases first)
```

**Key design choice:** the AI never makes the compliance decision. A plain, tested rules engine (`ach_agent/policy.py`) does that, and code checks that the agent followed it. The AI investigates, explains and writes. See [DECISIONS.md](DECISIONS.md) for every rule and the reason behind it.

Other choices:
- **One conversation per return,** so one confusing case can't contaminate the next.
- **Human in the loop:** every action needs approval, and high-severity cases are listed first.
- **Offline mode:** the whole pipeline runs without an API key, with templates in place of AI-written text, so anyone can try it.
- **Step limit:** the agent gets at most 10 tool calls per return.

## Run it

```bash
pip install -r requirements.txt

python run.py --offline                 # no API key needed
export ANTHROPIC_API_KEY=your_key
python run.py                           # full agent with Claude
python run.py --auto-approve            # skip the approval prompts

python -m pytest                        # 8 tests, including one where the AI ignores the policy
```

The report is written to `reports/triage_report.md`. A sample is included.

## Sample data

`data/` has a fictional batch of 8 returned deposits that covers each path: a first-time R01, an R01 already retried twice, an R10 on a 6-day-old account that already traded $1,000, a revoked authorization, a repeat bad-account return, a frozen account, and a made-up code (R77) to test the "unknown" path. All names and partners are invented.

## What I'd add next

- A daily dashboard of return rates by partner, with alerts as a partner nears Nacha's 0.5% unauthorized threshold
- Real return files (Nacha format) as input in place of CSV
- Comparing a single agent with a multi-agent setup (an investigator plus a separate notice writer) for accuracy and cost

## Built with

Python, the Anthropic API (Claude tool use), pytest. Built with help from Claude.
