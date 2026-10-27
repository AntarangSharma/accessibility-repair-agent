# Engineering notes

## Execution and patch scope

`RepairAgent` builds one LangGraph with `choose` and `execute` nodes. The model returns
one strict Pydantic `Action`: inspect_page, read_source, propose_patch, or
verify_candidate. A null proposal means abstention. The coordinator performs an initial
browser scan so correct and unsupported pages require no model call. A model-requested
inspection returns that cached, actual observation. Read-source returns only pristine
HTML/CSS and their aggregate SHA-256. Page text is explicitly untrusted in the system
prompt, including the misleading text in fixture 08.

The live adapter is a single official SDK call to `responses.parse`. It uses GPT-6 Luna
with low reasoning effort by default, a strict schema, `store=False`, standard service,
zero automatic retries and a maximum 35-second request timeout. Model and price settings
are configurable through local environment variables. The returned provider model is
recorded after a completed call. The scripted adapter reads only the test response file;
that file, contracts, catalog outcomes and test code never enter live model input.

Each patch has a base-content hash and at most 12 exact replacements. Only `index.html`
and `style.css` are editable. Every old string must match once in the evolving file,
with a combined old/new UTF-8 budget of 12,000 bytes. All replacements and structural
checks finish in memory before writes. Files and their directory are flushed before
verification. Path traversal, absolute paths, symlinks, stale hashes and noneditable
files fail closed. Scripts and the document head must be identical. Visible wording,
IDs, form field names, classes, data attributes and form attributes are preserved.
Native controls retain their keyboard roles and tabindex. Script handlers, inline
styles, hidden/inert/disabled attributes and executable URLs are prohibited.

CSS is parsed with tinycss2. Selectors, rule order, properties and declaration count
must remain unchanged. Only existing color/background declarations may change, and
only to solid hex values. There is no general CSS or JavaScript execution tool.

Hard ceilings are three candidates, 12 model calls, 2,200 output tokens per call,
24,000 input bytes per call, 180 seconds per run and $0.30 estimated spend per run.
A candidate verification is at most 60 seconds; the runner also has a 55-second watchdog.
A failed API request retains its pre-call spend reservation. Missing usage, invalid
output, refusals and exhausted limits fail closed. A process-group kill cleans up the
Node runner and its Chromium descendants on coordinator timeout.

Prices are estimates, not a billing guarantee. The default input allowance is a
conservative $0.25 per million tokens to allow for cache-write pricing, and output is
$0.50 per million tokens. Input reservations use UTF-8 bytes plus a framing allowance as
an upper bound. Cached-input discounts are not assumed. Changing models requires both
price settings; nonpositive, infinite and NaN prices are rejected. The evaluation CLI
also caps aggregate estimated spend (default $3, maximum $10).

## Independent verification

Each browser invocation starts a new Chromium context with no carried cookies, storage
or service workers. A separate HTTP server binds to an ephemeral localhost port and
serves exactly three allowlisted files. Only the hash-checked bundled trusted script
executes. Network routing and CSP confine requests to that fixture origin and bundled
assets. The browser process does not inherit API keys. The UI never serves fixture HTML
or embeds it in an iframe. It receives screenshots and escaped text only. Its mutation
endpoint requires a per-process CSRF token, the exact Origin, JSON validation and an
allowed localhost Host. Fixture scripts cannot operate application controls.

The Node runner reads immutable behavior contracts itself from the repository. It does
not accept test code or assertions from the model. It records a full scoped WCAG-tagged
axe scan and a separate label/color-contrast scan, including incomplete results. Explicit
Tab, Enter and Space tests check action activation exactly once without accidental form
submission. Pointer clicks independently check the listener effect. Action tests fill the form first
and assert that pointer, Enter and Space activation preserve its entered values,
rejecting accidental reset semantics as well as accidental submission. Forms are filled
and submitted against an exact expected payload written independently of candidate HTML.
Accessible-name assertions compare against the independently authored contract.

Acceptance requires all supported targeted failures to resolve, a strict improvement,
no new violations or incomplete findings in the scoped scan, and every functional,
keyboard and name assertion to pass. Relevant controls must remain visible/enabled,
preserve identity and have dimensions within max(12px, 20%) of the baseline. Visible leaf
text and its visibility must remain unchanged. This is a conservative fixture acceptance
policy, not a general layout equivalence proof. Screenshots remain review evidence.

The regression integration test fixes the email label while changing the submit button
to a non-submit button. Axe improves to zero targeted failures, but the independent form
payload test fails, so acceptance is rejected. No model acts as the judge.

## Durability, rollback and restart

SQLite with WAL and synchronous FULL is the authoritative state journal. `run.json` is
an fsynced, atomically replaced portable mirror. Intent is committed before copying a
fixture, applying a proposal, contacting the API or invoking verification. Each attempt
has its own pristine copy. Rejected files, results and diffs remain available for review;
only `accepted_path` identifies the active repair. A rejection never changes that pointer.
The original remains pristine. Failed or unverified work has no active repair.

The application takes an exclusive state-directory lock before recovery. Startup marks
unfinished runs interrupted, rejects pending decisions and clears active pointers. It
does not infer acceptance from a patched file or screenshot. An interrupted verification
must be rerun as a fresh run. This intentionally avoids automatic API retries or ambiguous
resumption. LangGraph manages the in-process loop; SQLite journals application transitions
rather than serializing LangGraph internals. The CLI evaluation uses a separate state tree
and should not be launched twice against that same tree concurrently.

## Fixture and evaluation design

Eighteen independent pages are catalogued with explicit contracts and outcomes. Twelve
are supported, three already correct and three unsupported. Families 09, 10, 11, 12, 15
and 18 were reserved before repair logic was built. Development and held-out summaries
remain separate. There has been no live model tuning or live held-out evaluation.
Scripted responses intentionally exercise bad first candidates on development fixtures
07 and 08. Scripted responses for reserved pages are pipeline cases, not withheld model
answers, so their success cannot establish generalization.

Both approaches use the same adapter/model, fixtures, preflight, pristine copies,
validators and acceptance function. Single-shot gets inspection and source and one
proposal call; the app then verifies it. The bounded agent chooses tools and may react
to the returned rejection, but cannot alter the oracles. Each candidate starts from the
original, so the next patch must include all intended changes rather than accumulating
an unverified partial repair. Reports count verified supported pages, accepted and
candidate behavior regressions, unnecessary correct-page proposals, correct abstentions,
attempts, latency, tokens and estimated spend. Manifests include dependency lock hashes,
fixture/contract hashes, implementation hashes, browser version, Python version and UTC
timestamps. Timestamps describe execution, not a claimed publication history.

## Five interview questions

1. **Where is the generative AI?** `LiveAdapter` asks the OpenAI model for a typed tool
   action and HTML/CSS replacements. The live path is implemented and its SDK contract is
   tested. Without API credentials, generative repair quality remains unmeasured.
2. **What makes this an agent?** The LangGraph loop returns tool observations and rejected
   verification results to the same decision-maker. The model chooses the next allowed
   tool and can revise up to three times. The scripted demo proves control flow only.
3. **Why not trust a cleaner axe report?** A native button can fix keyboard semantics yet
   submit a form accidentally. Independent click and payload tests catch that. The explicit
   axe-improves/form-breaks integration test checks the acceptance boundary.
4. **What happens if it crashes?** A pending verification has no accepted pointer. Restart
   recovery marks it interrupted and retains evidence, with the original still intact.
   Only a completed deterministic acceptance may activate a candidate.
5. **What would version two need?** More independently authored holdout families, measured
   live runs and manual assistive-technology assessment come first. Supporting complex
   widgets, arbitrary sites or frameworks would require a much broader security and test
   model. This fixture laboratory deliberately does not provide those interfaces.

## Limitations

Only Chromium and bundled static pages are exercised. Contract checks are finite; they
cannot prove every behavior or accessibility property. Forms use a trusted local static
submission handler rather than a production backend. Layout checks use a dimension
tolerance, not pixel equivalence. A page with any detected unsupported condition is
abstained as a whole. Full WCAG compliance, screen-reader usability, mobile behavior,
complex widgets, ambiguous text, gradients/images and framework applications are outside
v1. Live results require credentials and model availability. The project is AI-assisted;
its claims are limited to the recorded tests and measured runs.
