# Step-by-Step Implementation Plan — Browser Research Agent

## 1. Purpose

This plan turns the system design into an ordered implementation path. It is intended to guide the project from agreed planning documents through a working MVP, while keeping the React workspace, browser extension, backend, source registry, Playwright automation, and Groq integration consistent.

Use this plan together with:

- [project_description.md](project_description.md)
- [frontend_description.md](frontend_description.md)
- [backend_description.md](backend_description.md)
- [browser_automation_description.md](browser_automation_description.md)
- [overall_architecture_working.md](overall_architecture_working.md)

The system has two user-facing parts: a lightweight browser extension for the Spotlight-style shortcut and quick query, and a separate web app for the full research workspace. The backend owns agent orchestration and credentials. Playwright runs separately from the user's active browser.

## 2. Implementation principles

- Agree on interfaces before building components that depend on them.
- Build a thin end-to-end path early, then add sources and capabilities incrementally.
- Keep the extension focused on query entry and handoff; keep research panels in the web app.
- Keep source selection bounded by the backend registry.
- Keep the Groq API key exclusively on the backend.
- Use normalized source results so the UI does not need source-specific scraping logic.
- Preserve successful source results when another source or Groq fails.
- Start with the simplest workable local setup and defer multi-user/cloud features.
- Treat the documents as plans; update all affected documents together when a contract decision changes.

## 3. Phase 0 — Confirm implementation decisions

Before coding dependent parts, agree on the following:

1. **Target browser(s):** choose the first browser for the extension MVP and confirm its extension APIs and shortcut behavior.
2. **Shortcut:** choose the key combination, with a toolbar action available as a fallback.
3. **Overlay presentation:** choose how the extension displays the Spotlight-style bar over the current browser page within supported extension APIs and permissions.
4. **Origins:** choose local development ports/origins for the React app and backend, plus the expected production origin if known.
5. **Run storage:** choose in-memory storage for the earliest single-user prototype or SQLite for local persistence; record the tradeoff and retention policy.
6. **Initial sources:** choose a small set that can be implemented reliably and lawfully. Identify which use Playwright and which use a direct API/HTTP adapter.
7. **Groq settings:** choose the initial model ID and practical request/token limits when implementation begins.
8. **Worker boundary:** decide whether Playwright initially runs in the backend process or a separate local worker process.

**Completion condition:** decisions are written into the shared API/architecture notes so frontend, backend, and extension implementation use the same assumptions.

## 4. Phase 1 — Freeze shared contracts

Define these shared items before connecting the UI to real services:

- API endpoint names and request/response schemas.
- Research `run_id`, source `tool_id`, and `source_execution_id` formats.
- Run and source status vocabulary.
- Evidence/result envelope and answer-reference format.
- SSE event names, event IDs/reconnect behavior, and snapshot behavior.
- Tool registry entry schema and disabled/unavailable representation.
- Error codes and safe UI messages.
- URL validation policy and run/result size limits.

Use the proposed contracts in [backend_description.md](backend_description.md) and [overall_architecture_working.md](overall_architecture_working.md) as the starting point. Update the component documents when names or behavior change.

**Completion condition:** the web app, extension, backend, and worker can be built against one agreed contract without inventing separate names or payload shapes.

## 5. Phase 2 — Create the project repository and workspace

1. Create the project repository and initial directory structure.
2. Add a concise README describing the project, planned components, and local setup approach.
3. Separate the web frontend, browser extension, and backend in a way that supports independent development while sharing documentation and contract definitions.
4. Add environment examples with placeholders only; exclude local secret files and generated browser data from Git.
5. Decide how shared types/schemas are represented so clients and backend do not drift.
6. Commit the agreed planning documents or their repository copies so later agents can reference them.

**Completion condition:** a clean checkout explains where each component lives and contains no real API keys or local browser profiles.

## 6. Phase 3 — Build the backend skeleton

1. Create the Python API service and a health/status endpoint.
2. Add server-side configuration for allowed origins, run limits, timeouts, storage, and Groq settings. The Groq key is optional during this phase.
3. Define the shared request, run, source execution, evidence, answer, event, and error schemas.
4. Implement the in-memory or SQLite run store selected in Phase 0.
5. Implement `POST /api/v1/research-runs` so it validates a query, creates a run, and returns a run ID and workspace URL.
6. Implement `GET /api/v1/research-runs/{run_id}` for a current snapshot.
7. Implement `GET /api/v1/tools` backed by a small explicit registry.
8. Implement SSE for run events, with status updates and a documented reconnect/snapshot approach.
9. Implement safe errors, request-size limits, and CORS for the actual local web and extension origins.

At this point the backend can return mocked plan/source events; it should not claim to have searched anything until an adapter is connected.

**Completion condition:** the API can create and return a coherent run snapshot and event stream using placeholder source executions, with no Groq or Playwright dependency yet.

## 7. Phase 4 — Design and build the React frontend

1. Use the frontend description to design the home query screen, responsive research workspace, answer panel, source panels, status states, and **+** source picker.
2. Keep the standalone web app visually separate from the extension overlay; the extension's Spotlight-like design is a distinct small surface.
3. Include loading, empty, partial-result, error, and connection-lost states in the design.
4. Add the frontend source code to the project repository using the intended Git workflow.
5. Review the generated React structure: routes, reusable components, accessibility, responsive layout, and central API client.
6. Remove or isolate mock data so it cannot be confused with live research results.
7. Add a run workspace route that can be opened by `run_id` and load a snapshot from the backend.
8. Add the API client for create-run, snapshot, tool-list, add-source, and SSE updates.
9. Wire the direct web-app query flow to the real backend.

**Completion condition:** a user can submit a query from the web app and see backend run statuses/results in the workspace, even if the source data is still mocked in this phase.

## 8. Phase 5 — Build the first thin vertical source flow

1. Pick one source with a sufficiently stable and permitted access path.
2. Add its registry entry, schema, result limit, and timeout.
3. Implement one source adapter and return normalized evidence.
4. Connect the adapter to the run orchestrator and source execution IDs.
5. Emit source-added, status, result, and completion events.
6. Render its result cards and source links in the React workspace.
7. Handle no-results, unavailable, timeout, and partial extraction outcomes.

Start with one reliable source so the complete lifecycle is proven before multiplying adapters.

**Completion condition:** a real web-app query creates a run, searches one source, and displays attributed results from the backend.

## 9. Phase 6 — Implement Playwright automation

1. Install/configure the Playwright library and compatible browser binaries according to the chosen backend/runtime setup.
2. Add the worker interface with run ID, source execution ID, registered tool ID, validated query, time budget, and result limits.
3. Create isolated, non-persistent browser contexts; do not reuse the user's browser profile or cookies.
4. Add URL scheme, destination, redirect, and private-network validation before navigation.
5. Implement one browser-backed adapter using resilient locators and bounded waits.
6. Normalize extracted fields to the shared evidence schema and cap text/result sizes.
7. Close pages and contexts on success, error, timeout, cancellation, and worker shutdown.
8. Return structured statuses for empty, blocked/unavailable, timeout, extraction failure, and success.
9. Add a second browser-backed source only after the first adapter's boundaries are clear.
10. Keep direct API/HTTP adapters in the registry where they are more appropriate than browser automation.

**Completion condition:** the backend can dispatch a registered browser task, receive bounded attributed results, and preserve run behavior when the browser task fails.

## 10. Phase 7 — Implement the browser extension quick search

1. Create the extension project for the target browser and its required manifest/configuration.
2. Register the selected shortcut through supported browser extension settings and provide a toolbar action fallback.
3. Build the Spotlight-style search bar with search icon, focused input, translucent/dimmed background, and optional blur matching the supplied reference.
4. Keep permissions minimal; the initial flow needs query entry and communication, not page-reading access.
5. On submit, send the query to the same backend create-run endpoint used by the web app.
6. Open the returned web-app workspace URL in a new tab promptly; handle blocked/failed tab opening with a visible fallback.
7. Add loading, network-error, and empty-query behavior.
8. Verify the extension never includes or stores the Groq key and never controls the Playwright browser.

**Completion condition:** from another browser tab, the user can invoke the shortcut or toolbar action, submit a query, and reach that run's web-app workspace in a new tab.

## 11. Phase 8 — Add Groq planning and synthesis

1. Add the backend-only `GROQ_API_KEY` configuration and ensure local secret files are ignored by Git.
2. Add a Groq client module with request timeout, selected model configuration, bounded retries, and safe provider errors.
3. Implement structured planner output containing an interpretation, selected registry tool IDs, and optional per-tool queries.
4. Validate every planner field and reject unknown tools, invalid inputs, and plans exceeding configured source limits.
5. Implement a deterministic fallback for simple cases or unavailable planning when appropriate.
6. Pass bounded normalized evidence to the synthesis call, with evidence IDs and source attribution.
7. Validate that answer references point to evidence that actually exists.
8. Emit answer updates and final run status to the workspace.
9. Handle Groq authentication, quota/rate-limit, timeout, and unavailable cases without erasing source results.
10. Document that queries and selected evidence may be sent to Groq and that use consumes the user's API credits.

**Completion condition:** a run can choose sources through the registry and produce an evidence-linked synthesis without exposing credentials or losing source results when Groq fails.

## 12. Phase 9 — Implement the manual **+** source workflow

1. Populate the picker from `GET /api/v1/tools` rather than hardcoding execution options in the UI.
2. Show enabled, disabled, and unavailable source states clearly.
3. On selection, add a pending panel immediately and call the add-source endpoint with run ID and tool ID.
4. Have the backend reuse the query stored in the run and validate the tool through the same registry path used by the planner.
5. Stream the new source execution's progress/results and update only its panel.
6. Define behavior for duplicate additions, repeated searches, failed starts, and a run that has already completed.

**Completion condition:** the user can add a source after the original plan and see the existing query run there without retyping it.

## 13. Phase 10 — Complete MVP behavior and operational boundaries

1. Implement partial run completion, source-level retries if supported, and cancellation if included.
2. Define run retention/expiration and behavior after backend restart for the selected storage model.
3. Set and enforce query length, source count, concurrency, navigation timeout, extracted text, result count, and model token limits.
4. Add safe handling for invalid URLs, redirects, internal/private addresses, and unsupported schemes.
5. Ensure source text is treated as untrusted evidence, not instructions.
6. Add user-facing privacy and API credit information.
7. Ensure the workspace reconnects by loading a snapshot and resubscribing to events.
8. Confirm extension/API CORS and deployment origins are narrowly configured.
9. Add concise operational logs that omit secrets, cookies, raw prompt internals, and full page contents.

**Completion condition:** failure, latency, and resource use are bounded and visible, and no core behavior depends on unsafe or undocumented access.

## 14. Phase 11 — Prepare the repository for continued agent development

1. Keep a clear top-level README and per-component setup notes.
2. Document how to run the web app, backend, extension, and Playwright browser locally.
3. Document how to configure the Groq key securely with a placeholder example.
4. Document the API contract and source adapter extension pattern.
5. Keep architectural decisions current in the companion documents when interfaces change.
6. Keep commits focused by component or milestone so later contributors can review and continue work.
7. Record deferred features separately instead of mixing them into the MVP implementation.

**Completion condition:** a new contributor can identify each component, configure a local environment, and understand the shared contract without relying on undocumented chat context.

## 15. Milestones and dependencies

| Milestone | Depends on | Deliverable |
| --- | --- | --- |
| M0: Decisions and contracts agreed | Existing planning documents | Final initial browser, shortcut, source list, storage, and API schemas |
| M1: Backend skeleton | M0 | Run creation, snapshot, registry, and event stream |
| M2: React workspace connected | M1 | Web query flow and run workspace driven by API events |
| M3: First real source | M1, M2 | End-to-end source result displayed with provenance |
| M4: Playwright adapter | M3 | Isolated browser-backed source execution |
| M5: Extension handoff | M1, M2 | Shortcut overlay submits a run and opens its workspace tab |
| M6: Groq planning/synthesis | M1, M3 | Validated source selection and evidence-grounded answer |
| M7: Manual source addition | M2, M3 | **+** picker launches source for current query |
| M8: MVP hardening | M4–M7 | Limits, errors, recovery, privacy, and setup documentation |

The extension can be built in parallel with the web workspace after M0, but should integrate only after the backend create-run contract is stable. Groq planning should be connected after the registry and at least one source adapter exist, so its output can be validated against real tool contracts.

## 16. MVP completion checklist

- [ ] Browser extension opens the Spotlight-style quick-search surface from a browser tab.
- [ ] The user can submit a text query from the extension or web app.
- [ ] Extension submission opens the matching research run in a separate web-app tab.
- [ ] Backend run IDs, snapshots, status events, and source IDs follow the shared contract.
- [ ] The agent can only select registered tools and stays within limits.
- [ ] At least one direct or browser-automated source returns useful normalized results.
- [ ] Playwright is isolated from the user's personal browser state and closes contexts after jobs.
- [ ] Groq planning/synthesis uses a backend-only key and bounded requests.
- [ ] The workspace shows source provenance, partial progress, failures, and synthesis distinctly.
- [ ] **+** adds a source and runs the current query without re-entry.
- [ ] Successful results survive unrelated source or Groq failures.
- [ ] Local setup, extension loading, environment configuration, and privacy limits are documented.

## 17. Future work after the MVP

Potential later phases include saved and searchable research sessions, export, more source adapters, richer citations, contradiction comparison, user-configured sites, customizable panel layouts, collaborative sessions, deployment for multiple users, and improved adapter health monitoring. These should be planned after the initial end-to-end flow is stable.

## 18. Summary

Implement the shared contract first, then build the backend run path and React workspace, connect one source end to end, add isolated Playwright adapters, build the browser extension quick-search handoff, and integrate Groq planning and synthesis. Finish with the **+** flow, security and resource limits, reconnect behavior, and setup documentation. The extension launches queries, the web app hosts results, the backend coordinates work, Playwright gathers browser-based evidence in isolation, and Groq is called only by the backend.
