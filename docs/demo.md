# Three-minute demonstration

Before the interview, install Node 22 and uv, run `make setup`, then `make demo`.
Open http://127.0.0.1:8765. No API key is required for the scripted demonstration.

## 0:00 to 0:30: Explain the boundary

Say: "This local workbench supports three small repair categories. The model proposes
HTML/CSS edits. Independent browser tests decide whether a candidate is accepted.
This demonstration uses scripted responses; it is not evidence of model repair quality."

Select `07-form-control`, `Scripted demo (no key)`, and `Verify and revise`.
Click **Scan and repair**. The initial state reports inspection in progress.

## 0:30 to 1:30: Inspect feedback and revision

When accepted, open **Candidate 1: rejected**. Its native button lacks `type="button"`.
The click listener still runs, but the form submits unexpectedly. Enter and Space
also cause unintended submission. Show the actual behavior and keyboard failures.
The original and rejected screenshots are available, and the diff is retained.

Open **Candidate 2: accepted**. The revised button includes `type="button"`, preserving
the ID, class, data attribute, listener, input names and form submission payload.
Both keyboard activation keys and the independent form/click assertions pass.
The application, rather than the model, records the acceptance decision.

## 1:30 to 2:15: Show another repair and an abstention

Run `01-newsletter`: the original has adjacent email text without an associated label.
The accepted patch creates an explicit label association. The independent form payload
still contains the expected email field and value. Read the before/after findings.

Run `16-ambiguous`: two inputs share one vague text block. The result is unsupported,
with the missing labels still visible in findings. There is no guessed patch.

## 2:15 to 3:00: Explain evidence and limits

Expand **Decision and tool trace** and download a manifest. Show the base hash,
rejected attempt, checks, resource limits and lock hashes. The trace contains concise
decisions and observations, not hidden reasoning.

State the measured scripted result from `reports/scripted.json`. Live evaluation is
pending when `OPENAI_API_KEY` is unavailable. Do not describe scripted success as AI
quality or claim automated WCAG compliance. For a live demonstration, configure an API
key locally, restart the application, select Live OpenAI, or run `make smoke-live` first.
