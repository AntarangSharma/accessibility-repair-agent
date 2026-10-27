# Browser contract v1

Python launches exactly `node <repository>/browser/runner.mjs`, without a shell.
The only input is one UTF-8 JSON object on stdin (maximum 32 KiB). The model cannot
choose subprocess arguments or supply this object directly.

```json
{
  "version": 1,
  "fixture": "01-newsletter",
  "root": "/absolute/run/candidate-1",
  "screenshot": "/absolute/run/candidate-1.png"
}
```

`fixture` must identify a bundled fixture. `root` is chosen by the coordinator and
contains the validated copy. The runner reads only index.html, style.css and trusted.js
there. It realpaths every served file and rejects escapes. The trusted.js bytes must
match the bundled original. Immutable contract.json is read directly from the repository,
never from candidate input. `screenshot` is a coordinator-chosen output path, never a
model path. This CLI is a trusted local boundary, not a public path-handling API.

Successful stdout is one JSON object, checked by `BrowserResult` in schema.py:

| Field | Meaning |
| --- | --- |
| version | Exactly 1. |
| axe.violations | Full scoped WCAG A/AA-tagged scan results. |
| axe.incomplete | Full scoped findings needing manual review. |
| axe.targeted | Label and color-contrast rule violations. |
| axe.targetedIncomplete | Incomplete results from those two rules. |
| controls | Observed IDs, names, tags, types, visibility, disabled state and boxes. |
| text | Observed visible leaf text and computed solid colors. |
| unsupported | Observed ambiguous labels, non-solid backgrounds or complex widgets. |
| labels | Immutable accessible-name assertion results. |
| behavior | Immutable pointer click and form payload assertion results. |
| keyboard | Tab reachability and separate Enter/Space activation results. |
| blocked | Unexpected requests blocked by origin/path restrictions. |
| browser | Actual Chromium version. |

Each check contains `id`, `pass` and a concise `observation`. Each axe finding retains
rule ID, impact, description, help URL and affected targets/HTML/failure summaries.
Screenshots are written before tests mutate the page. Checks use fresh pages within that
invocation's new context. Origin and port never persist into the next invocation.

Nonzero exit, missing fields, an invalid version, a parse error or timeout fails
verification. Stderr is bounded and sanitized before display. The Python coordinator
kills the entire subprocess group on timeout. The Node watchdog exits after 55 seconds;
the coordinator limit is no more than 60 seconds and also obeys the run deadline.
Only application code reads this result to decide acceptance. No result is interpreted
as an instruction to run code or disable a check.
