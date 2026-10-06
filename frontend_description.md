# Frontend Description — Browser Research Agent

## 1. Purpose

The frontend is the user's research workspace for the Browser Research Agent. It accepts text queries, shows the agent's selected research sources and progress, and presents source-specific results beside an AI-generated synthesis. It also provides the quick-search overlay and the controls for extending a research run with additional source panels.

This document describes the frontend's responsibilities and the way it connects to the rest of the system. It is a product and implementation plan, not implementation code.

## 2. Product assumptions

- The product has two user-facing pieces: a standalone React web app for the full research workspace, and a lightweight browser extension for quick search from any browser tab.
- The app is text-first. It has no voice, speech, or audio features.
- A user submits a natural-language query; the agent decides which available registered sources are relevant.
- The planned LLM provider is Groq, called from the backend using a user-configured API key and available credits. The key must not be embedded in frontend code.
- The frontend is expected to be built with React. Its source code should remain understandable and maintainable as it is developed and versioned in Git.
- The frontend communicates with the backend; it does not directly control Playwright or make privileged browser-automation decisions.

## 3. Frontend goals

- Make it easy to start a research run from a normal query bar or a quick-search overlay.
- Keep the query and its research results together in a clear workspace.
- Show which sources the agent chose and whether each source is running, complete, empty, or failed.
- Keep the AI synthesis visually distinct from retrieved source results.
- Preserve source titles, snippets, thumbnails when available, and working links so users can inspect evidence.
- Let users add a source panel with **+** and automatically submit the active query to that source.
- Provide a focused, responsive UI that can be refined as the backend and browser extension are developed.
- Communicate errors and limits clearly without making the interface feel like an engineering dashboard.

## 4. Main user journey

1. The user opens the web app. The home screen provides a prominent text query input and a short indication of what the research workspace does.
2. From any browser tab, the user invokes the configured extension shortcut.
3. The extension presents a Spotlight-style search bar above the current browser view, with a dimmed/translucent background, optional blur, search icon, and focused text field.
4. The user enters a query and submits it. The extension sends the query to the backend API and opens the web app's results workspace in a new browser tab.
5. The web app attaches to the resulting research run and displays its workspace. The web app also has its own query bar and can start runs without using the extension.
6. The workspace immediately shows the query, the plan/status of selected sources, and loading panels. Results can populate as each source completes.
7. The AI answer appears when the backend has gathered enough evidence and completed synthesis. It links to the source results where the backend provides citation references.
8. The user can inspect original links, add another source through **+**, or start a follow-up query.

## 5. Screens and major components

### 5.1 Home / query screen

The home screen is the entry point for research. It should include:

- Product name and a concise description.
- A prominent multiline or expandable text input.
- A submit button and keyboard submission behavior.
- An optional example-query area to help a first-time user understand supported tasks.
- A visible shortcut hint once the shortcut is configured.
- A small settings entry point for frontend preferences and connection state, without exposing secrets.

The input should support ordinary text queries, including requests that name a website or content type. The UI should not require the user to choose sources before submitting; source planning is the agent's responsibility.

### 5.2 Quick-search overlay

The extension quick-search overlay is inspired by the Spotlight search shown in the user's reference image: a compact horizontal search bar appears near the center of the browser viewport above a dimmed/translucent current page. It should have:

- A focused text input with placeholder guidance.
- Submit and dismiss controls, plus clear keyboard behavior.
- A subtle backdrop and accessible contrast; blur is decorative and must not make the input or surrounding controls hard to read.
- A visible indication that submission starts a new research run.
- Optional recent queries only if a later product decision adds local history; do not assume history is required for the initial version.

The cross-tab shortcut and overlay are provided by the browser extension, not by the web page. Browser extensions can register a browser-level shortcut and show a popup or overlay in the current tab, subject to browser APIs, permissions, and platform behavior. The overlay is limited to the browser; it is not an operating-system-wide overlay over unrelated applications. A visible extension action should also open the quick-search UI in case the shortcut is unavailable or changed.

The exact shortcut is intentionally undecided until the user chooses it. It should be configurable through the browser's extension shortcut settings where supported, avoid common browser/OS shortcuts, and be explained in the extension's setup page. The extension should provide a visible toolbar action as an alternative. Browser shortcut limitations and conflicts should be described accurately.

### 5.3 Research workspace

The workspace is the primary results view. It should contain:

- **Query header:** The submitted query and a way to return home or start another run.
- **Research status/plan:** A concise summary of the sources selected by the agent, each with an understandable state such as queued, searching, complete, unavailable, or failed.
- **AI answer panel:** A readable synthesis, distinct from raw search results, with source references/links supplied by the backend.
- **Source panels:** Individual panels for sources such as general web search, YouTube, Wikipedia, image search, and configured websites.
- **Add-source control (+):** Opens the source picker and launches the selected source for the current query.
- **Panel controls:** At minimum, close a panel and open its source links. Resizing and rearranging are desirable but may be staged after the core flow works.
- **Run state:** Loading feedback, partial results, completion state, and clear recovery actions for failed sources.

The UI should not assume that exactly two sources will run. The planner may select one or several registered tools depending on the query and configured limits. The user's manual source addition can increase the number of panels during a run.

### 5.4 Source picker and manual panel addition

Selecting **+** opens a picker populated from the backend's available-source registry (or a frontend-safe capability list delivered by the backend). Each option should show its label and short purpose. Disabled/unavailable sources should be clearly represented if the backend supplies that status.

When the user selects a source:

1. The frontend creates a panel in a pending state.
2. It sends the active query and selected tool identifier to the backend as an explicit user-requested source action.
3. The backend validates that the source is registered and allowed, executes it, and streams or returns its result.
4. The frontend updates the panel with progress, results, empty state, or error.

This action must reuse the current query without asking the user to type it again. If the backend requires a separate endpoint for manual source execution, that endpoint should accept the existing research run ID and tool ID, or the active query plus tool ID when no run ID is available.

## 6. Interaction and accessibility requirements

- Keyboard-accessible query submission, overlay dismissal, source selection, panel controls, and links.
- Clear focus outlines and predictable focus movement into and out of the overlay.
- Escape dismisses the overlay when it is open; Enter submits when appropriate, with Shift+Enter available for a newline in a multiline query field.
- Buttons have accessible names; loading and completion updates are announced appropriately to assistive technology.
- Do not use color alone to communicate source status.
- Respect reduced-motion preferences and avoid requiring blur effects for comprehension.
- Keep text readable and source links identifiable.
- Work well on desktop for the multi-panel workspace; on narrower screens, stack panels or provide a simple panel selector rather than squeezing unreadable columns.

## 7. Frontend state and data model

The frontend should represent at least:

- **Research run:** run ID, original query, creation time, overall status, selected tools, and available answer state.
- **Source panel:** a stable panel ID, tool/source ID, display name, query, status, results, and error details if any.
- **Evidence item:** title, URL, snippet or extracted text, optional thumbnail/metadata, and source identity.
- **Answer:** answer text or structured sections and references that map to evidence items or source panels.
- **Capabilities:** tool IDs and display metadata suitable for the source picker; no provider secret or privileged configuration.

The frontend should be prepared for results to arrive incrementally. It should not assume that all source searches finish together or that the synthesis is available before source results.

## 8. Frontend-to-backend contract

The backend owns orchestration, tool selection, browser automation, source fetching, Groq calls, result normalization, and synthesis. The frontend owns presentation, user input, panel lifecycle requests, and displaying progress/results. This boundary keeps API keys and browser-control logic out of the browser's JavaScript bundle.

Proposed API interactions (names are illustrative and should be finalized in the backend description):

### Start a research run

- Request: text query and optional UI preferences that do not override safety or backend limits.
- Response: run ID, normalized query, initial plan/source list, current status, and a web-app workspace URL.
- Extension behavior: make the request on submit and open the returned workspace URL in a new tab.
- Web frontend behavior: navigate to or create the results workspace and render queued/loading panels.

### Receive run updates

- Use server-sent events, WebSocket, or short polling for status and result updates. Choose one transport in the backend plan; server-sent events are a reasonable MVP choice for one-way progress.
- Events should identify the run and source/tool, and carry status changes, normalized results, answer updates, or errors.
- Frontend behavior: update only the relevant panel and preserve already received results.

### List source capabilities

- Response: available tool IDs, labels, descriptions, and enabled/disabled state.
- Frontend behavior: populate the **+** source picker; do not hardcode source execution logic in React.

### Add a source to a run

- Request: run ID and registered tool ID (plus an optional user-provided site URL only if the product supports it and the backend validates it).
- Response: accepted action and panel/source execution ID.
- Frontend behavior: add the pending panel, then consume its updates.

### Cancel or retry

- Optional MVP endpoint to cancel a run or retry a failed source, subject to backend support.
- The frontend should show these controls only if the corresponding backend operation is implemented.

Errors should use stable machine-readable codes plus safe user-facing messages. The frontend must not receive or display the Groq API key.

## 9. Navigation and new-tab behavior

The product request is for submitting a quick query to take the user to a new tab containing the result workspace. A web page can usually open a new tab only in response to a direct user gesture, and browsers may block popups if navigation is delayed until after asynchronous planning.

To support the desired behavior reliably, the frontend should open a blank/loading workspace synchronously when the user submits from the overlay (within the click/keyboard gesture), then attach the newly created run to that workspace after the backend returns its run ID. A same-tab navigation option should be available if the browser blocks the new tab or the user prefers it. The new workspace URL should identify the run without putting API keys or sensitive query data in the URL. If the app later supports shareable links, use an opaque run identifier with appropriate access controls.

The exact handling of failed popup creation, reloads, and direct workspace links should be tested in the chosen browsers during implementation.

## 10. React implementation direction

React is the proposed frontend framework. A component structure could include:

- `AppShell` for app-level layout and routing.
- `HomePage` and `QueryComposer` for the default query experience.
- `QuickSearchOverlay` for the centered launcher interaction.
- `ResearchWorkspacePage` for one research run.
- `ResearchPlan` or `RunStatus` for selected tools and progress.
- `AnswerPanel` for the synthesis.
- `SourcePanel` and source-specific result renderers for normalized results.
- `SourcePicker` for the **+** flow.
- Shared loading, empty, error, and connection-state components.

The initial UI design should be treated as a starting point. Before connecting it to a real backend, the code should be checked for routing structure, component reuse, keyboard accessibility, responsive behavior, and whether API requests are centralized behind a small client module. Avoid embedding mock-only assumptions that conflict with the backend contract.

## 11. Visual direction

The interface should feel like a calm research workspace: a clear query field, readable source cards/panels, restrained status indicators, and enough separation that the AI synthesis is not confused with source material. The quick-search overlay should be visually focused and launcher-like, but the workspace should prioritize readable evidence over decorative effects.

Suggested visual elements:

- Neutral background and a distinct workspace surface.
- A centered overlay with a translucent/dimmed backdrop and optional blur.
- Source identity labels and favicons/logos only where available and appropriate.
- Consistent result cards with title, snippet, source, and open-link action.
- Responsive grid that can move from multiple columns on wide displays to stacked panels on narrow displays.
- Explicit labels for AI-generated synthesis and retrieved results.

Specific brand colors, typography, and component-library choices can be decided during frontend design.

## 12. Error, loading, and partial-result behavior

- Show an immediate accepted/loading state after a run starts.
- Show source-level progress so one slow source does not make the entire workspace appear frozen.
- Preserve successful source results if another source fails.
- Distinguish no results from a failed request.
- Give a concise message and retry option where supported.
- If the Groq-backed synthesis fails but source panels succeeded, keep those results visible and identify that the synthesis is unavailable.
- If browser navigation or a popup is blocked, offer a direct action to open the run in the current tab.
- Avoid presenting fabricated content to fill a failed or empty panel.

## 13. Security and privacy responsibilities

- Never store the Groq key in frontend source, local storage, session storage, URLs, or browser-visible configuration.
- Do not send the key from the browser; all LLM requests go through the backend.
- Render retrieved page content as text or sanitized content. Do not execute HTML or scripts collected from sources.
- Treat source results as untrusted and avoid interpreting page-provided instructions as application commands.
- Do not collect query history or analytics by default unless the product later makes that behavior explicit.
- Show a suitable notice in product documentation/settings that queries and selected excerpts may be sent to the configured LLM provider for reasoning or synthesis.

## 14. MVP frontend scope

### Required for first usable frontend

- Home screen with text-only query entry.
- Main submit flow to create a backend research run.
- Centered quick-search overlay with backdrop effect and keyboard/button access.
- A lightweight browser extension providing a configurable browser-wide shortcut and Spotlight-style quick-search overlay.
- Results workspace in a new tab when opened from a direct submission gesture, with a same-tab fallback.
- Query header, source plan/status, AI answer panel, and source panels.
- Incremental loading, success, empty, and error states.
- **+** source picker connected to the backend's registry and automatic current-query execution.
- Basic responsive layout and keyboard accessibility.
- Centralized API client and no frontend handling of LLM credentials.

### Out of scope for the MVP

- Operating-system-wide shortcut interception outside the browser; the extension works only within the browser and remains subject to browser limitations.
- Any installed desktop helper.
- Voice or audio input/output.
- User accounts, collaboration, cloud persistence, and cross-device history.
- Rich drag-and-drop panel customization unless it is needed for the initial design.
- Direct browser automation from the frontend.

## 15. Dependencies on other project descriptions

This frontend plan is one part of a coordinated architecture. Its API names and payload details are proposals until the backend contract is agreed.

- **Overall project:** [project_description.md](project_description.md) describes the end-to-end concept, agent behavior, sources, constraints, and MVP. This frontend document elaborates on the user-facing layer.
- **Backend description (to be created):** Must define research-run creation for both clients, source capability listing, manual source execution, progress transport, result/error schemas, cancellation/retry support, and secure Groq API configuration.
- **Browser automation description (to be created):** Must define how Playwright adapters execute source actions and normalize results. The frontend must only receive normalized results through the backend.
- **Shared architecture/interface plan:** Before implementation, align route structure, run IDs, tool IDs, status vocabulary, result envelope, and event transport across all descriptions.

When the backend and browser automation descriptions are written, update this document's API and data sections to use their finalized names and exact contracts rather than maintaining competing proposals.

## 16. Frontend success criteria

The frontend plan is realized when:

- A user can submit a text query from the home screen and reach its results workspace.
- The extension's quick-search overlay can be opened from different browser tabs with the configured shortcut (subject to browser support) and dismissed with clear controls.
- Submission can open a new workspace tab without losing the query; blocked popups have a usable fallback.
- The workspace makes the query, selected sources, source progress, AI synthesis, and individual source results easy to distinguish.
- Adding a source through **+** creates a panel and runs the current query without re-entry.
- Partial results remain visible when another source fails.
- The UI never exposes the Groq API key or calls Groq directly.
- Core interactions work with keyboard navigation and adapt to desktop and narrower screens.

## 17. Summary

The frontend consists of a React standalone web app for the query home screen and multi-panel research workspace, plus a lightweight browser extension for the Spotlight-style quick-search overlay and browser-wide shortcut. The extension submits a query to the backend and opens its results in a new web-app tab. The web app displays incremental source results and the Groq-backed synthesis, and lets users extend a run through the registry-powered **+** picker.
