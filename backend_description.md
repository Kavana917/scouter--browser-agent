# Backend Description — Browser Research Agent

## 1. Purpose

The backend is the trusted orchestration layer connecting the React research workspace, the lightweight browser extension, the agent planner, source adapters, Playwright automation, and the Groq API. It accepts research requests, decides which registered sources to use, gathers and normalizes their results, requests a source-grounded synthesis from Groq, and provides run updates to the clients.

This document defines the backend's responsibilities and a proposed MVP contract. It is a design plan, not implementation code. Exact names can be adjusted when implementation begins, but the frontend and browser automation plans should use one shared contract.

## 2. Architecture context and related documents

- [project_description.md](project_description.md) describes the full product and system flow.
- [frontend_description.md](frontend_description.md) describes the web app workspace and the extension's Spotlight-style quick-search interaction.
- [browser_automation_description.md](browser_automation_description.md) details Playwright lifecycle, source adapters, extraction, and browser isolation.

The product has two clients:

1. A standalone React web app that renders the query screen and multi-panel research workspace.
2. A lightweight browser extension that invokes the quick-search overlay from browser tabs and submits a query to the backend.

Both clients are untrusted API clients. The backend does not trust tool IDs, URLs, result payloads, or query instructions simply because they came from an interface.

## 3. Backend goals

- Provide a stable API for the web app and the browser extension.
- Create and track research runs with per-source status and partial results.
- Use an explicit source/tool registry as the allowlist of agent capabilities.
- Coordinate query interpretation, source selection, browser automation, and synthesis.
- Keep the Groq API key exclusively on the backend.
- Bound latency, source count, result size, and model-token usage to manage credits and prevent runaway work.
- Return normalized evidence that can be rendered consistently by the frontend.
- Surface partial success and understandable errors instead of failing an entire run when one source fails.
- Treat fetched page content as untrusted data.

## 4. Responsibilities and boundaries

### The backend owns

- API authentication/configuration appropriate to the deployment model.
- Input validation, rate/size limits, and request IDs.
- Research-run creation and status tracking.
- Planner prompting and tool selection using the registry.
- Dispatching source actions to registered adapters.
- Playwright worker coordination where a source requires browser interaction.
- Result normalization, deduplication, truncation, and provenance metadata.
- Groq API calls for planning and synthesis.
- Progress events and error mapping.
- Safe configuration and handling of secrets.

### The backend does not own

- Rendering the workspace, overlay, or panels.
- Registering the browser keyboard shortcut or drawing an overlay over the current tab; those belong to the extension.
- Embedding an API key in frontend or extension code.
- Unrestricted browsing, arbitrary shell execution, or arbitrary code execution requested by a webpage or LLM output.

## 5. Proposed backend stack

- **Language/framework:** Python with a lightweight asynchronous API framework such as FastAPI.
- **Browser automation:** Playwright, usually executed in managed worker/context boundaries as described in the browser automation plan.
- **LLM provider:** Groq API via a server-side client module, configured with an environment variable such as `GROQ_API_KEY` and an explicitly chosen model identifier.
- **Progress transport:** Server-sent events (SSE) for one-way run updates in the MVP; WebSocket is unnecessary unless bidirectional live interaction becomes a requirement.
- **MVP storage:** In-memory or lightweight local persistence may be used for active runs during early local development. A persistent store should be introduced before multi-user or restart-resilient deployment.
- **Configuration:** Environment variables or a local ignored `.env` file for secrets and operational limits. Commit only a `.env.example` with placeholder values.

Provider-specific code should be isolated in a Groq client/service module. The planner and synthesis logic should depend on an internal LLM interface so that provider details do not leak across the application, while Groq remains the selected provider for this project.

## 6. High-level request flow

1. A client submits a query to create a research run.
2. The API validates and normalizes the request and creates a run ID.
3. The planner reads the registry and query, then selects an allowed, bounded set of source tools and search terms.
4. The orchestration layer starts source tasks, preferably in parallel within configured concurrency and timeout limits.
5. Source adapters return normalized result envelopes. Browser-based adapters delegate work to the Playwright layer.
6. As source statuses and results change, the backend emits run events.
7. When sufficient results are available (or all selected sources have completed), the synthesis service calls Groq with the query and bounded evidence.
8. The backend emits the final answer and run-completed event. Successful source results remain available even if another source or synthesis call failed.

For a manual **+** action, the web app submits the active run ID and a registered tool ID. The backend validates the tool, starts that source for the run's current query, and emits a new source-panel event. The frontend does not need to retransmit the query unless the backend contract explicitly asks for it.

## 7. API surface (proposed MVP)

All paths below are illustrative, versioned under `/api/v1`, and should be finalized together with the frontend description.

### 7.1 Create a research run

`POST /api/v1/research-runs`

Request fields:

- `query` (required string): user's text query, with a documented maximum length.
- `client_source` (optional enum): `web_app` or `browser_extension`, for diagnostics only; it must not grant additional authority.
- Optional presentation preferences, if needed; do not accept client-provided model prompts, tool definitions, raw Groq settings, or unrestricted execution instructions.

Response fields:

- `run_id`: opaque run identifier.
- `query`: normalized or stored query (clearly specify whether this is the exact user text).
- `status`: initial run status.
- `workspace_url`: URL for the web app's results route, based on the run ID and containing no API secrets.
- `sources`: selected tool IDs, labels, and initial statuses when available.
- `events_url`: URL used by the web app to subscribe to updates.

The extension should open `workspace_url` in a new tab in response to the user's submit action. The API should respond quickly with the run accepted; source work can continue asynchronously.

### 7.2 Get a run snapshot

`GET /api/v1/research-runs/{run_id}`

Returns the current run status, original query, source panels and their current results, and any synthesized answer. This supports initial page load, refresh, and recovery if the event stream disconnects.

### 7.3 Subscribe to run events

`GET /api/v1/research-runs/{run_id}/events`

SSE emits typed events such as:

- `run.status`: queued, planning, searching, synthesizing, completed, partial, failed, or cancelled.
- `source.added`: panel/source identity, source/tool ID, label, and initial status.
- `source.status`: source execution status and safe user-facing details.
- `source.results`: normalized result items or a bounded result batch.
- `answer.updated`: answer text/structured sections and references.
- `run.error`: safe run-level error code and message.
- `run.completed`: final status and summary metadata.

Events should include `run_id`, stable source execution/panel ID where applicable, and event sequence or event ID. SSE reconnect behavior should support replay or client recovery from the snapshot endpoint. Never include secrets or raw internal prompts in events.

### 7.4 List source capabilities

`GET /api/v1/tools`

Returns the frontend-safe registry view: stable `tool_id`, display label, short description, supported query mode, and enabled/disabled availability. It must not return credentials, private adapter configuration, internal system prompts, or sensitive diagnostics.

### 7.5 Add a source to an existing run

`POST /api/v1/research-runs/{run_id}/sources`

Request: a registered `tool_id`, and only any additional validated input that the tool explicitly supports. The backend retrieves the query from the run record, validates that the tool is enabled and permitted, creates a source execution, and emits `source.added` and subsequent status/result events.

This endpoint is how the **+** picker automatically runs the current query in the newly selected source. Duplicate requests should be handled predictably; the API may reject an identical active source request or allow an explicitly identified rerun.

### 7.6 Optional cancellation and retry

- `POST /api/v1/research-runs/{run_id}/cancel`
- `POST /api/v1/research-runs/{run_id}/sources/{source_execution_id}/retry`

Include these only if they can be supported reliably. The frontend should not display controls that the backend does not implement.

## 8. Data contracts

### Research run

A run record should include:

- Opaque `run_id`.
- User query and creation/update timestamps.
- Overall status and, if relevant, bounded plan metadata.
- Selected tool IDs and source execution records.
- Final/partial synthesis and evidence references.
- Safe error information and cancellation state.
- An expiration/retention policy for transient results.

### Source execution

Each panel execution should contain:

- `source_execution_id` (stable unique ID).
- `tool_id` and display label.
- Query or derived search terms used.
- Status such as `queued`, `running`, `completed`, `empty`, `unavailable`, `failed`, or `cancelled`.
- Normalized evidence items.
- Start/finish timestamps and safe error information.

### Evidence item

Common fields should include:

- `evidence_id`.
- `title` and canonical `url` when available.
- `snippet` or bounded extracted text.
- `tool_id` / source identity.
- Optional thumbnail/image URL and source-specific metadata.
- Retrieval timestamp.

The backend should preserve provenance from adapter to synthesis. It should not invent URLs or assign evidence references that do not exist.

### Answer

The answer may be plain text for the simplest MVP, but should support structured sections and references. References should map to evidence IDs or source execution IDs, allowing the frontend to link claims to visible panels. If evidence is insufficient, the answer should say so or remain unavailable rather than imply unsupported certainty.

## 9. Agent planner and tool registry

The planner receives the user's query, a compact description of enabled registry entries, and bounded planning instructions. It returns a structured plan, not executable code. A plan can include:

- A short interpretation of the research goal.
- A small set of selected `tool_id` values.
- Optional focused search queries per tool.
- A short rationale/status for display if exposed to the UI.

The backend must validate the planner output against the registry and schemas. Unknown tool IDs, malformed requests, excessive source counts, invalid domains, or prohibited URLs are rejected or safely dropped. Tool adapters receive only validated arguments.

The registry is authoritative and should define tool ID, label, description, input schema, output schema, execution adapter, enabled state, timeout, result limit, and limitations. Candidate sources include general web search, YouTube, Wikipedia, images, configured websites, and page opening. Each integration may be direct API-based or Playwright-based according to its adapter design.

Manual source actions use the same registry validation as planner-selected sources. A frontend or extension cannot introduce a new tool by passing an arbitrary tool definition.

## 10. Groq integration

Groq is the selected LLM API for this project. The backend should:

- Read `GROQ_API_KEY` from server-side configuration; never send it to either client.
- Read the intended model name from configuration so it can be changed without editing planner logic.
- Keep Groq request construction, response parsing, timeouts, retries, and provider error mapping in a dedicated module.
- Use structured output or strict schema validation for the planner response when supported by the chosen model/API mode.
- Bound input size, output tokens, retries, and requests per run to manage the user's credits.
- Avoid an LLM call for every UI action. A typical run may require one planning call and one synthesis call; implementation can reduce calls if planning can be handled deterministically for simple cases.
- Avoid retrying quota/authentication errors as if they were transient network failures.
- Return a clear safe status when Groq is unavailable or credits/rate limits prevent completion. Source results should still be displayed.
- Never log the full API key, authorization header, or unnecessarily large/private query payloads.

The application should document that using a Groq API key consumes the user's provider credits according to their Groq account and model terms. No local model is planned.

## 11. Source orchestration and Playwright handoff

The backend delegates browser-dependent work to source adapters and the Playwright service/worker. The browser automation description should specify the exact worker API and browser lifecycle. The backend contract with that layer should include:

- A registered tool identifier and validated input.
- A run ID and source execution ID for correlation.
- Timeout and result-count bounds.
- A normalized result envelope or an adapter-specific payload that the backend normalizes.
- Safe failure categories such as timeout, navigation error, blocked/unavailable, extraction error, and empty results.

The backend is responsible for updating run state and delivering normalized results to clients. The extension itself never attaches to, controls, or reads the user's current browser page unless a future feature explicitly requires and designs that permission. The current quick-search extension only collects the text query and starts a run.

## 12. Security, privacy, and operational limits

- Store Groq credentials only in backend environment/configuration; use secret management for deployed environments.
- Validate all request bodies, query lengths, tool IDs, URLs, and optional site inputs.
- Apply request-size, concurrency, timeout, source-count, result-count, and token limits.
- Protect browser automation against SSRF and unsafe navigation: validate protocols/domains, block local/private network destinations where appropriate, and define redirect handling in the browser automation plan.
- Treat model output and page text as untrusted. Model-generated plans are data that must be schema-checked, never code to execute.
- Treat website text as evidence, not instructions. Prompt construction should clearly delimit untrusted source content.
- Avoid logging secrets and limit retention of query/result data. Define deletion/expiration for transient runs.
- For local single-user development, simple access may be acceptable; any network-exposed deployment needs authentication or an equivalent access boundary and origin/CORS protections.
- Configure CORS only for the web app origin and extension origin/extension identity that are actually used. Validate extension messages and never treat extension origin as proof that the request is safe.
- Consider abuse protection and rate limiting before exposing a public endpoint, since requests can spend the user's Groq credits and trigger browser automation.

## 13. Error handling and partial success

Use stable internal error codes and safe client messages. Examples include:

- `INVALID_QUERY`
- `RUN_NOT_FOUND`
- `UNKNOWN_TOOL`
- `TOOL_DISABLED`
- `SOURCE_TIMEOUT`
- `SOURCE_UNAVAILABLE`
- `SOURCE_EXTRACTION_FAILED`
- `GROQ_AUTH_ERROR`
- `GROQ_RATE_LIMITED`
- `GROQ_UNAVAILABLE`
- `RUN_LIMIT_REACHED`

Source errors should be attached to the relevant source execution. A single source error should not erase successful results from other sources. If Groq synthesis fails after sources complete, return those source results and mark the answer as unavailable. Internal stack traces and secrets remain server-side.

## 14. MVP scope

### Include

- API service for run creation, run snapshots, tool listing, manual source addition, and SSE updates.
- A validated registry with a small set of initial source adapters.
- Query planning, source orchestration, normalization, and answer synthesis.
- Server-side Groq integration using a user-provided key.
- Playwright worker/adapter integration for browser-dependent sources.
- Run/source status tracking and partial-result behavior.
- Practical limits, safe errors, and environment-based configuration.
- New-tab workflow support: create a run and return a web-app workspace URL the extension can open.

### Defer

- Multi-user account management and cloud persistence.
- Cross-device saved history and long-term run storage.
- Complex autonomous browsing loops or arbitrary tool/plugin installation.
- Advanced evidence verification, scoring, and contradiction resolution.
- Distributed job queues and horizontal scaling until usage requires them.
- Usage billing, quota purchase, or management of the user's Groq account.

## 15. Backend success criteria

- Both the extension and web app can create runs without exposing Groq credentials.
- A run returns quickly with an opaque ID and workspace URL while source work proceeds.
- The web app can load the run snapshot after a new-tab open or refresh.
- Status and partial results arrive with stable run/source identifiers.
- Agent tool choices are restricted to registered, validated tools.
- The **+** action runs the active run's query in a validated selected source.
- Groq failures do not discard successful source results.
- API limits keep research runs bounded in time, source count, response size, and credit use.
- Web content and planner output cannot trigger actions outside registered capabilities.

## 16. Open decisions for implementation

- Whether the first local version persists runs in memory, SQLite, or another lightweight store.
- Exact initial source adapters and whether each uses a direct API or Playwright.
- Exact Groq model ID and output mode, to be verified when implementation starts.
- Extension and web-app local origins, development CORS settings, and production deployment origin.
- Whether request authentication is needed for the intended local-only MVP.
- Final event schema, retry rules, and run expiration period.

## 17. Summary

The backend is the trusted API and orchestration layer for both the React web app and quick-search extension. It validates requests, plans against an explicit registry, delegates searches to source adapters and Playwright, normalizes evidence, calls Groq using the user's server-side API key, and streams progress and results to the workspace. It returns a run URL for the extension to open in a new tab and supports the workspace's **+** action through the same validated registry. API keys, planner authority, and browser automation remain on the backend.
