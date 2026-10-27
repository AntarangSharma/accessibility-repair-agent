# Sources and fixture provenance

The fixture markup, scripts, wording and contracts were written for this repository.
The examples are small conceptual adaptations of publicly documented test patterns,
not copies of either demonstration site. No external pages or assets are downloaded
by the application.

- [W3C WAI Before and After Demonstration](https://www.w3.org/WAI/demos/bad/): informed
  paired inaccessible/accessible examples, unassociated form text and contrast failures.
  The full demonstration has functionality that does not work as a plain local static page.
  This project implements its own tiny local form and click behavior instead.
- [GDS accessibility tool audit test cases](https://alphagov.github.io/accessibility-tool-audit/test-cases.html):
  informed separated label, contrast and keyboard cases and the distinction between
  tool detection and usable behavior. The source repository's [MIT license](https://github.com/alphagov/accessibility-tool-audit/blob/gh-pages/LICENSE)
  was inspected. Copyright (c) 2017 Crown Copyright (Government Digital Service).
- [Playwright accessibility testing](https://playwright.dev/docs/accessibility-testing):
  informed the `AxeBuilder` integration and the warning that automated checks are limited.
  The runner combines axe with separately authored behavior assertions.

W3C's [Software and Document License](https://www.w3.org/copyright/software-license-2023/)
permits redistribution with its notice and disclaimers when material is copied or derived.
No W3C source code, images or document passages are redistributed here. Attribution is
retained above for the conceptual patterns. GDS source code is not redistributed either.
Dependencies retain their own licenses in their packages; this project's MIT license
applies to first-party source only.

## API and runtime references checked during implementation

- [Official OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)
- [GPT-6 Luna model and rates](https://developers.openai.com/api/docs/models/gpt-6-luna)
- [LangGraph Python Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [Playwright installation and supported systems](https://playwright.dev/docs/intro)
- [Node release support](https://nodejs.org/en/about/previous-releases)

Python 3.12.13 and Node 22.22.2 were used locally. Node 22 is an LTS release.
The registry reported Playwright 1.64.1 (Node >=20) and axe Playwright 4.14.0
(Node >=22.12). These exact packages are locked. Python dependencies were resolved
under Python 3.12, including FastAPI 0.162.0, Pydantic 2.14.1, LangGraph 1.2.18
and the official OpenAI SDK 3.39.0. SDK parameters and strict response parsing are
exercised in `tests/test_model.py`; that test does not call the live API.
