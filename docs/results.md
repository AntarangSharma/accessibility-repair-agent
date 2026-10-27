# Recorded evaluation

These are **scripted pipeline results**, not measured live model quality. The raw
report is `reports/scripted.json`: 36 real browser runs, one pair of approaches per
page, with actual axe, keyboard, accessible-name and functional results. Each run
starts with a clean copy and uses the same deterministic acceptance function.

| Split | Approach | Verified repairs | Attempts | Accepted behavior regressions | Rejected behavior regressions | Unnecessary edits | Correct abstentions | Total latency (s) | Median/page (s) | Tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Development | Single-shot | 6/8 | 8 | 0 | 1 | 0/2 | 2/2 | 46.533 | 3.385 | 0 |
| Development | Agent | 8/8 | 10 | 0 | 1 | 0/2 | 2/2 | 53.685 | 3.402 | 0 |
| Reserved families | Single-shot | 4/4 | 4 | 0 | 0 | 0/1 | 1/1 | 25.855 | 3.551 | 0 |
| Reserved families | Agent | 4/4 | 4 | 0 | 0 | 0/1 | 1/1 | 26.001 | 3.595 | 0 |

Single-shot verifies 10/12 supported pages in 12 attempts. The bounded agent verifies
12/12 in 14 attempts. All 22 accepted candidates across the two approaches preserve
specified behavior. Each approach leaves all three correct pages unchanged and
abstains on all three unsupported pages. No API tokens were used; estimated API
spend is $0. The measured times are host-dependent and include inspection and
verification subprocesses, not just model latency.

Scripted development responses deliberately include a form-submit regression and
an incomplete mixed repair. A revised response is issued after actual rejection.
This constructs a useful control-flow test; it does not establish that a generative
model is more accurate when allowed to revise. The six reserved families were
selected before repair implementation, but scripted answers for them are still
known pipeline inputs, so these are not AI generalization results.

Both `make smoke-live` and `make eval-live` were executed. They wrote explicit
pending status reports and returned exit code 2 because `OPENAI_API_KEY` was absent.
There were **zero live calls**. The target of 10/12 live repairs remains unmeasured.
Neither a failed target nor a successful live rate is inferred from scripted results.

Local `make test` passed 41 tests plus the actual UI journey. A clean temporary
checkout installed its own dependencies and Chromium, then passed `make check` and
`make test`. `make docker-smoke` built the image and passed the same 41 tests and a
real UI journey within the container. See `reports/verification.json` for the
command-level record and the repository's Actions tab for CI outcomes.
