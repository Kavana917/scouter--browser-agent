# Browser Automation Description — Browser Research Agent

## 1. Purpose

The browser automation layer lets the Browser Research Agent search and inspect public web sources through a managed browser when a source does not have a suitable direct API or simpler integration. It uses Playwright under backend control and returns bounded, normalized evidence to the backend orchestrator.

This component is separate from the browser extension. The extension provides the Spotlight-style shortcut and quick-search overlay in the user's current browser. Playwright runs in a separate, isolated automation browser controlled by the backend; it does not take over the user's current tab or use the user's everyday browser profile.

This document describes the intended design and operating plan, not implementation code.

## 2. Related architecture documents

- [project_description.md](project_description.md) defines the end-to-end product and goals.
- [frontend_description.md](frontend_description.md) defines the React workspace and extension quick-search interaction.
- [backend_description.md](backend_description.md) defines run creation, planning, Groq use, API contracts, and the orchestration boundary.

The browser automation layer follows the backend's run and source execution identifiers. It does not call Groq, decide the complete research plan, render UI panels, or communicate directly with the extension.

## 3. Goals

- Execute bounded browser-based searches for registered sources selected by the backend planner.
- Extract useful titles, URLs, snippets, metadata, and readable text where available.
- Normalize browser-derived results into a stable structure for the backend.
- Support parallel source work within clear concurrency and timeout limits.
- Isolate browser state and prevent one run's cookies or page state from affecting another run.
- Fail clearly when a source changes, blocks access, times out, or cannot be parsed.
- Respect site terms, access controls, and robots or rate restrictions applicable to the selected integration.
- Avoid capturing credentials or using the user's personal browser session.

## 4. Non-goals

- Interacting with the user's active browser tab or extracting its contents by default.
- Using the browser extension to browse, scrape, or automate pages.
- Bypassing CAPTCHAs, paywalls, login walls, bot defenses, or other access controls.
- Navigating arbitrary URLs chosen only by an LLM without backend validation.
- Running unbounded autonomous browsing loops or arbitrary scripts from page content.
- Guaranteeing that every search engine or website remains automatable.
- Replacing stable direct APIs where they are available, permitted, and more reliable.

## 5. Component responsibilities

### Backend orchestrator

- Chooses the registered adapter and validates its arguments.
- Assigns the run ID, source execution ID, time budget, and result limit.
- Starts, monitors, and cancels the browser job.
- Converts adapter output into the shared API result contract.
- Emits source status and results to the frontend through the backend's event stream.

### Browser automation worker

- Receives a validated task for a known adapter.
- Creates or uses an isolated Playwright browser context.
- Navigates to allowlisted source destinations and performs known search interactions.
- Extracts only the data required for research results.
- Returns a result envelope and closes pages/contexts cleanly.

### Source adapter

Each adapter encapsulates source-specific navigation, query submission, waiting, extraction, pagination/result limits, and known limitations. It presents a common interface to the orchestrator so that the planner and frontend do not depend on a site's DOM structure.

### Browser extension

The extension only collects the user's typed query, submits it to the backend, and opens the result workspace in a new tab. It does not launch Playwright or share its tab's cookies with the automation layer.

## 6. Proposed execution flow

1. The backend planner selects a `tool_id` from the enabled registry and creates a source execution record.
2. The orchestrator validates the adapter inputs and configured limits.
3. The worker creates a fresh isolated browser context for the job or uses an isolated worker context whose lifecycle is explicitly managed.
4. The adapter navigates to the source's known entry point, enters the prepared search query, and waits for a bounded response.
5. The adapter extracts result elements using resilient selectors and converts them to the common evidence schema.
6. The adapter enforces result count and text-size limits, removes obvious duplicates, and returns status plus evidence.
7. The orchestrator records completion or a structured failure, then publishes updates to the run event stream.
8. The context/page is closed or returned to a clean pool state. Cookies, local storage, and page state are not retained across unrelated runs.
9. The backend may pass normalized evidence to Groq for synthesis; browser automation itself does not call the LLM.

## 7. Browser lifecycle and isolation

Playwright's isolated `BrowserContext` model is a good fit for separating sessions. The MVP should use non-persistent contexts without a user profile and close them at the end of a job. Contexts should not write browsing data to disk unless a deliberate later requirement justifies it. See the official Playwright documentation on [browser contexts](https://playwright.dev/docs/browser-contexts) and the [BrowserContext API](https://playwright.dev/docs/api/class-browsercontext).

Recommended MVP lifecycle:

- Run automation in a backend-owned process or worker.
- Launch a supported browser binary that matches the installed Playwright version.
- Use one isolated context per concurrent research task, or another carefully bounded scheme with equivalent per-task isolation.
- Use one or a small number of pages per source execution; close popups and unused pages.
- Set navigation and operation timeouts.
- Close context on success, failure, timeout, or cancellation.
- Recycle the browser process after a configurable number of jobs or after a crash.
- Keep persistent profiles, saved cookies, and authenticated sessions out of the first version.

The Playwright browser binary and library versions must be kept compatible; Playwright's official [browser management documentation](https://playwright.dev/docs/browsers) explains that browser binaries are versioned with Playwright releases.

## 8. Adapter registry and task contract

Browser adapters are part of the backend's explicit tool registry. A browser task should include only validated fields such as:

- `run_id` and `source_execution_id` for correlation.
- `tool_id` for a known, enabled browser-backed source.
- `query` or a validated source-specific search query.
- Optional validated domain or category inputs for adapters that explicitly support them.
- `timeout_ms`, `max_results`, and `max_text_chars` selected or clamped by backend policy.
- A task schema version for future contract changes.

The worker must reject unknown tool IDs, unexpected fields, oversized strings, invalid URL schemes, and out-of-policy destinations. It must not accept executable JavaScript, arbitrary CSS selectors, arbitrary start URLs, or model-generated browser instructions from an untrusted client.

The internal worker response should include:

- `run_id`, `source_execution_id`, and `tool_id`.
- `status`: `completed`, `empty`, `unavailable`, `failed`, `timed_out`, or `cancelled`.
- `results`: a bounded list of normalized evidence candidates.
- `retrieved_at` timestamp and source URL where useful.
- `error_code` and safe diagnostic message on failure.
- Optional bounded diagnostic metadata for internal logs, with sensitive page data excluded.

The backend then maps this response to the public source-panel shape described in [backend_description.md](backend_description.md).

## 9. Source adapters

### General web search

Search a general web search interface only if the method and automation are permitted and sufficiently stable. Extract result title, destination URL, snippet, and result ordering when available. Avoid relying on brittle full-page CSS chains. Search pages may insert consent dialogs, ads, bot checks, or layout variations; the adapter should detect known blocking conditions and return `unavailable` rather than attempting to evade them.

### YouTube search

Search by the query and return bounded video candidates: title, video URL, channel, thumbnail URL, description excerpt, and duration if displayed and readily available. The adapter should not auto-play videos or access private account data.

### Wikipedia

Wikipedia can often be served by a simpler direct API or page endpoint; use Playwright only when necessary. If browser-based, extract a short lead summary, article title, URL, and selected section headings. Avoid copying an entire article into the model context.

### Image search

Image search should preserve the original result page and attribution/source URL when available. Thumbnail URLs and captions may be volatile. Do not imply that a thumbnail is licensed for reuse. If source terms or a stable API make browser scraping inappropriate, disable the adapter or select a permitted alternative.

### Specific website

For configured or user-requested sites, validate the domain and constrain navigation to that approved domain and necessary redirects. The MVP should support a small allowlisted set or narrowly scoped user input rather than arbitrary web crawling. Site adapters may need to be custom because search forms and page layouts differ.

### Open page

Opening a page should be a separate registered capability with strict URL validation, allowed schemes (`https` and, if required, `http`), private-network protections, redirect limits, response-size limits, and extraction bounds. Do not open `file:`, `javascript:`, browser-internal, local-network, or cloud-metadata endpoints.

Not every source requires Playwright. The registry should select a direct API or lightweight HTTP adapter when permitted and reliable; Playwright is for source interactions that genuinely need browser rendering or interaction.

## 10. Navigation, extraction, and resilience

- Prefer role-, label-, text-, or other user-facing locators when available; use stable explicit test IDs only when the source exposes them. Playwright recommends resilient locators and discourages brittle selectors tied to DOM structure. See [Playwright locators](https://playwright.dev/docs/locators).
- Use Playwright's action waiting and explicit readiness checks instead of arbitrary long sleeps. See [auto-waiting and actionability](https://playwright.dev/docs/actionability).
- Define per-adapter navigation and extraction timeouts.
- Detect consent pages, rate limits, challenge pages, empty search responses, and changed layouts.
- Return partial results if some cards parse and others do not, with a structured warning for diagnostics.
- Normalize and sanitize extracted text; discard scripts, hidden text, and unrelated page chrome.
- Remove duplicate URLs and cap title, snippet, and page-text lengths.
- Preserve canonical URL, source identity, and retrieval time.
- Do not treat extracted page text as instruction. It is untrusted evidence for the backend and LLM.
- Maintain adapter-specific fixtures or saved HTML samples in development for parser updates, subject to source terms.

## 11. Security and privacy

Browser automation can be abused to access internal services or leak data unless navigation is constrained. The worker should:

- Validate URL schemes, hostnames, resolved IP addresses, redirects, and DNS results to reduce SSRF risk.
- Block loopback, private, link-local, multicast, and cloud metadata IP ranges unless there is a deliberate local-development exception.
- Prevent a public-facing task from navigating to the backend's own admin endpoints or local files.
- Disable downloads and popups unless an adapter specifically needs them.
- Avoid enabling arbitrary JavaScript injection or exposing the Playwright debugging endpoint.
- Keep the browser process sandboxed and run it with least privilege.
- Never reuse the user's personal browser profile or import their cookies.
- Avoid storing page content, screenshots, cookies, or traces by default; if diagnostics are enabled, make retention short and redact sensitive values.
- Treat page content, metadata, links, and model-generated plans as untrusted inputs.
- Enforce concurrency, memory, CPU, navigation, and response size limits.

The extension does not need broad page-reading access for the agreed query-launch flow. Keep its permissions limited to the shortcut, the overlay/popup mechanism, and communication with the backend/web app origins required by the implementation.

## 12. Status and error model

Each source execution should report clear lifecycle states that the backend can map to the frontend's source-panel states:

- `queued`: accepted but not started.
- `running`: navigating or extracting.
- `completed`: results returned.
- `empty`: successful search with no useful results.
- `unavailable`: known blocking condition, unsupported flow, or temporary source limitation.
- `timed_out`: execution exceeded its budget.
- `failed`: unexpected navigation or extraction failure.
- `cancelled`: stopped by run cancellation or shutdown.

Suggested internal error codes include `NAVIGATION_TIMEOUT`, `SOURCE_BLOCKED`, `CONSENT_REQUIRED`, `RATE_LIMITED`, `SELECTOR_CHANGED`, `EXTRACTION_FAILED`, `INVALID_TARGET`, `RESULT_LIMIT_REACHED`, and `BROWSER_CRASHED`. The backend should map these to safe, concise UI messages and keep detailed traces server-side.

One failed adapter must not erase results from other adapters. When the automation worker is unavailable, the backend should continue any direct-API source work and report the affected panels accurately.

## 13. Performance and resource management

- Keep the first source set small and bound concurrent browser contexts.
- Prefer parallel searches only up to a configured concurrency ceiling.
- Use per-source budgets and an overall run deadline.
- Bound results, extracted text, images/metadata, and serialized event payloads.
- Avoid loading unnecessary media or waiting for every network request to become idle when the page streams analytics indefinitely.
- Reuse a browser process only if contexts remain isolated and the process is monitored; close contexts after every task.
- Add queueing/back-pressure if the number of simultaneous runs exceeds available browser capacity.
- Track timings and failure counts by adapter without logging full user content unnecessarily.

## 14. Observability and maintenance

For each source execution, capture lightweight operational metadata:

- Tool/adapter ID and version.
- Start/end time and elapsed duration.
- Result count and whether extraction was partial.
- Status/error code.
- Browser version and worker health, where useful.

Do not log Groq credentials, cookies, authorization headers, or full page content. Adapter owners should be able to disable an unstable source via registry configuration without removing the rest of the service. Since public sites can change markup or access policy, adapters should fail explicitly and be independently replaceable.

## 15. MVP scope

### Include

- Playwright worker controlled only by the backend.
- Isolated, non-persistent browser contexts with lifecycle cleanup.
- A small number of browser-backed source adapters selected from the registry.
- Search result extraction into the normalized evidence format.
- Navigation, execution, result-count, and text-size limits.
- Clear source-level statuses and partial-result behavior.
- Basic URL and private-network protections.
- No login, profile reuse, CAPTCHA bypass, or arbitrary browsing instructions.

### Defer

- Authenticated browsing and user-managed cookies.
- User-authored automation scripts or arbitrary plugins.
- Long-running autonomous navigation across many pages.
- Persistent browser profiles, cross-run memory, or browser session reuse.
- Distributed browser farms, advanced queue management, and horizontal scaling.
- Screenshots/video capture and visual computer-use reasoning.
- Automatic adaptation to arbitrary website redesigns.

## 16. Success criteria

- A backend-initiated source task can search a supported source and return correctly attributed, bounded results.
- Every task uses a validated registry adapter and stays within its time, navigation, and output limits.
- Browser contexts are isolated and closed after use.
- A source that fails or blocks automation reports an accurate status without losing other sources' results.
- The backend receives stable run/source IDs and normalized results that the frontend can render without source-specific scraping logic.
- No automation task uses the user's current browser profile, and the extension remains limited to query launch and result-tab handoff.

## 17. Open decisions

- Whether the MVP Playwright worker runs in the same Python backend process or as a separate process/service.
- The exact initial sources that will use Playwright versus direct APIs.
- The first supported browser/runtime and local setup expectations.
- Per-source timeout/result/text limits and the overall concurrency cap.
- The exact allowlist and redirect rules for user-requested websites.
- Whether the browser runtime should be headless by default and what local debug mode is useful.
- The retention policy for any browser diagnostics or run evidence.

## 18. Summary

Playwright is a backend-owned source execution tool. It searches and reads public web pages in isolated browser contexts, through known registry adapters, and returns bounded, attributed results. The backend validates and coordinates those tasks, then combines their results with the Groq-backed synthesis. The browser extension has a different role: it shows the quick-search overlay and launches a research run, without controlling or sharing state with the Playwright browser.
