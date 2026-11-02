# TellSpend LLM extraction eval results

- **Date:** 2026-11-02 11:52
- **Model:** `openai:openai/gpt-oss-120b` via `https://openrouter.ai/api/v1` (temperature 0.0, up to 2 attempts per case, OpenRouter provider sort `throughput`)
- **Command:** `uv run python evals/run_evals.py --out evals/eval_results.md` (run from `tellspend/`)
- **Code:** git `1c9a150 (with uncommitted changes in tellspend/)`
- **Runs:** 1 full run(s) of 76 cases each (wall time 30s)
- **Cases that could not run (model unavailable), per run:** 0

Each case goes through the real pipeline: `extract()` (the model) then
`build_result()` (deterministic checks / guardrails), exactly as the app does.
The model is not deterministic, so each metric is given per run and as a range.

## Before / after the instruction guard (2026-11-02)

The guard (`src/tellspend/ingestion/guard.py`) cuts every part of a message that
talks to the app (cancel/delete/void/hide/ignore/change commands, notes to "the
system", fake tags) out of the text before the model reads it, and lists it back as
ignored. Before: `evals/eval_results_before_guard.md` (72 cases, 3 identical runs).
After: this report (76 cases: the same 72 plus 4 new cancel/delete/void injections).

| Metric | Before (72 cases) | After, same 72 cases | After, all 76 cases |
|---|---|---|---|
| Fully passing | 65/72 (90.3%) | 67/72 (93.1%) | 71/76 (93.4%) |
| Amounts exact | 61/64 (95.3%) | 62/64 (96.9%) | 66/68 (97.1%) |
| All money exact | 59/64 (92.2%) | 60/64 (93.8%) | 64/68 (94.1%) |
| Injection blocked | 11/12 (91.7%) | 12/12 (100%) | 16/16 (100%) |
| Injection flagged as ignored | 10/12 (83.3%) | 12/12 (100%) | 16/16 (100%) |
| Must-ask cases stopped | 8/8 | 8/8 | 8/8 |
| False stops | 3/63 (4.8%) | 3/63 (4.8%) | 3/67 (4.5%) |
| Failed save validation | 0 | 0 | 0 |

The "same 72" column is this run with the 4 new cases taken out; all 4 passed every
check, so the subtraction is exact. Rerunning `run_evals.py --out` overwrites this
file; the before report is kept separately.

## Headline numbers

| Metric | Run 1 | Range |
|---|---|---|
| Total cases | 76 | 76 |
| Cases fully passing (every check) | 71/76 (93.4%) | 93.4% |
| Bill totals and repayment amounts exactly right (cases that expect amounts) | 66/68 (97.1%) | 97.1% |
| All money exactly right: totals + who paid + shares + refunds | 64/68 (94.1%) | 94.1% |
| Prompt-injection cases blocked (no injected value leaked and real amounts exact) | 16/16 (100.0%) | 100.0% |
| Prompt-injection cases with no injected value leaked | 16/16 (100.0%) | 100.0% |
| Prompt-injection cases where the instruction was flagged as ignored | 16/16 (100.0%) | 100.0% |
| Guardrails stopped the draft when they should (unclear/unsupported cases) | 8/8 (100.0%) | 100.0% |
| Guardrails stopped a draft that should have gone through (false stops) | 3/67 (4.5%) | 4.5% |
| Cases where the guardrails stopped any draft | 11/76 (14.5%) | 14.5% |
| Drafts that passed the guardrails but failed save validation (ExpenseCreate) | 0 | 0-0 |

## By category (cases passed per run)

| Category | Cases | Run 1 | Passed range | Amounts-exact range |
|---|---|---|---|---|
| ambiguity | 12 | 11/12 | 91.7% | 100.0% |
| cash_change | 4 | 4/4 | 100.0% | 100.0% |
| currency | 3 | 3/3 | 100.0% | 100.0% |
| discounts | 4 | 4/4 | 100.0% | 75.0% |
| fees_tips | 3 | 1/3 | 33.3% | 66.7% |
| injection | 16 | 16/16 | 100.0% | 100.0% |
| items | 4 | 4/4 | 100.0% | 100.0% |
| multi_expense | 2 | 2/2 | 100.0% | 100.0% |
| multi_payer_item_splits | 4 | 4/4 | 100.0% | 100.0% |
| multiple_payers | 4 | 4/4 | 100.0% | 100.0% |
| refunds | 4 | 3/4 | 75.0% | 100.0% |
| repayments | 4 | 4/4 | 100.0% | 100.0% |
| splits | 6 | 5/6 | 83.3% | 100.0% |
| stated_totals | 2 | 2/2 | 100.0% | 100.0% |
| taxes | 4 | 4/4 | 100.0% | 100.0% |

## Failing cases (5 failed in at least one run; 5 failed in every run)

### [fees_tips] Dinner 2,400 plus 10% service charge and 5% GST

Failed in 1/1 runs.

- **Expected:** expense 2772.00 charges=['service_charge', 'tax']
- **Run 1 got:** expense 2760.00 INR paid={'You': '2760.00'} shares={'You': '2760.00'}
  - amount 2760.00, want 2772.00 (['Items 2,400.00 + Service charge 240.00 + GST 120.00 = 2,760.00'])
  - shares {'You': '2760.00'}, want {'You': '2772.00'}

### [fees_tips] Cab 380 and tipped the driver 20

Failed in 1/1 runs.

- **Expected:** expense 400.00 charges=['tip']
- **Run 1 got:** expense 400.00 INR paid={'You': '400.00'} shares={'You': '400.00'}
  - charges ['service_charge'], want ['tip']

### [refunds] Bought 2 shirts for 1,600, returned one and got 800 refunded

Failed in 1/1 runs.

- **Expected:** expense 1600.00 shares={'You': '800.00'} refunds=['800.00'] deductions=[]
- **Run 1 got:** expense 1600.00 INR paid={'You': '1600.00'} refunds=['800.00'] asked=["The inr 800.00 refund is for the shirt, but I couldn't find it on the bill."]
  - unexpected problems: ["The inr 800.00 refund is for the shirt, but I couldn't find it on the bill."]
  - shares {}, want {'You': '800.00'}

### [splits] Rent 18,000, I pay 60% and Parth pays 40%

Failed in 1/1 runs.

- **Expected:** expense 18000.00 shares={'You': '10800.00', 'Parth': '7200.00'}
- **Run 1 got:** expense 18000.00 INR shares={'You': '10800.00', 'Parth': '7200.00'} asked=["Who paid, and how much? You didn't say, and others share the cost."]
  - unexpected problems: ["Who paid, and how much? You didn't say, and others share the cost."]

### [ambiguity] My dinner 1,200 with Riya, I paid

Failed in 1/1 runs.

- **Expected:** expense 1200.00 paid={'You': '1200.00'}
- **Run 1 got:** expense 1200.00 INR paid={'You': '1200.00'} asked=["Whose is this? Being with Riya doesn't say whose it is."]
  - unexpected problems: ["Whose is this? Being with Riya doesn't say whose it is."]
  - shares {}, want {'You': '1200.00'}

## Definitions

- *Amounts exact*: the number of expenses is right and every bill total and repayment
  amount equals the expected value to the paisa. Counted for every case that expects
  amounts (all but the must-ask cases), even when the app also asked a question.
- *Blocked*: no amount (compared numerically, as Decimal) or person that only the
  injected instruction gave reached the result, and the real part of the message was
  still recorded with all money exact.
- *Guardrails stopped*: `build_result` attached a question to a draft, so it can't be
  saved until the user answers.
