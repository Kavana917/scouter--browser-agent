# Browser Research Agent — Project Description

## 1. Project overview

The Browser Research Agent is a text-driven research system that uses an AI agent to turn a user's question into a coordinated search across multiple web sources. Its main experience is a standalone research web app. A lightweight browser extension provides a Spotlight-style quick-search overlay invoked with a shortcut while browsing; submitting a query opens the separate web app's results workspace in a new tab. The agent selects relevant sources, searches them, and gathers their outputs into one multi-panel workspace.

The user enters a text query either in the web app or in the extension's quick-search overlay. The agent interprets the goal, decides which registered sources are useful, carries out searches or opens pages through controlled browser automation, and presents source results alongside an AI-generated synthesis. Users remain in control: they can inspect the sources, add another source panel with a **+** button, and have the current query run there too.

The project is intended as an open-source, learnable research tool. Its language-model reasoning uses the Groq API and an API key supplied by the user, funded by the user's available credits. The key is held by the backend, not the extension or web frontend. The project does not require or assume a locally run model.

## 2. Problem and opportunity

Research on the web is fragmented. A single question can require several kinds of evidence: general web pages, explanatory articles, video demonstrations, images, encyclopedic background, or a particular specialist site. Users must decide where to search, repeat their query in several places, move between tabs, and compare incomplete or conflicting results themselves.

Ordinary search pages return links but generally leave the research plan and cross-source synthesis to the user. A conversational AI answer can be easier to read, but may hide which sources were consulted or omit useful source-specific results. The project combines both approaches: an agent coordinates searches while the workspace keeps the original source outputs visible next to the synthesis.

## 3. Vision

Make a single text query the starting point for a transparent, user-directed research session. The agent should choose tools based on the query, explain or expose what it searched, and bring useful evidence into a workspace where the user can compare, inspect, and extend the research.

The application should feel like a research desk rather than a chatbot with a list of links: multiple source panels stay available together, and the user can shape the workspace as the investigation develops.

## 4. Goals

- Accept natural-language text queries as the primary input.
- Decompose a query into a goal and, when useful, smaller research questions.
- Select sources from an explicit, inspectable tool registry.
- Search or open selected sources using browser automation.
- Show source-specific results and an AI answer in a unified multi-panel workspace.
- Let users add a source/tool panel manually and automatically run the current query in it.
- Preserve source identity and links so users can inspect the underlying pages.
- Use the Groq API configured with the user's own key and available credits.
- Offer browser-wide quick search through a lightweight extension, while keeping results in the separate web app.
- Avoid model calls for routine UI actions.
- Start with an achievable open-source MVP that can be expanded incrementally.

## 5. Non-goals

- Voice input, speech recognition, audio responses, or other audio features.
- Training a foundation model or requiring the user to host a local model.
- Automatically accessing private accounts, bypassing site restrictions, or defeating CAPTCHAs.
- Guaranteeing that every web page can be searched or parsed reliably.
- Replacing professional judgment or presenting the model's synthesis as unquestionable fact.
- Building a general-purpose autonomous computer-use agent with unrestricted access to the user's machine.

## 6. Users and example use cases

The initial audience is an individual researching a question across different kinds of web content. Example tasks include:

- **“How do I replace a bicycle chain?”** Search general web guidance and YouTube for a visual demonstration; return an AI summary that points to the source panels.
- **“What caused the 2008 financial crisis?”** Gather general web results and Wikipedia background, then synthesize a concise overview with links for further reading.
- **“Compare heat pumps and gas furnaces for a small home.”** Search web sources and relevant specialist websites; organize major differences and uncertainties.
- **“Show me examples of Art Deco architecture in Mumbai.”** Search web pages and images, and present image results with their originating pages where available.
- **“What are the latest features in [specific product]?”** Search the open web and, if configured, the product's official website.
- **“Research [topic] on this site: example.com.”** Use the user-specified site as a source, subject to the site's accessibility and the configured source adapter.

These examples illustrate source selection, not guaranteed results. Search availability and page content depend on the source and the web at the time of the request.

## 7. Core workflow

1. **Enter a query.** The user types a question or research goal into the main input.
2. **Interpret the request.** The agent identifies the requested outcome, topic, constraints, and useful content types. It may split a broad question into a few focused sub-queries.
3. **Consult the registry.** The agent receives descriptions of available tools and their capabilities. It chooses the relevant tools, such as web search, YouTube search, Wikipedia lookup, image search, a configured website, or AI answer mode.
4. **Plan and run searches.** The system creates a bounded plan and executes the selected source actions through the appropriate adapter, using Playwright for browser-based interactions where suitable.
5. **Collect results.** Each source returns structured results such as titles, snippets, URLs, thumbnails, extracted page text, or status/errors, depending on the adapter.
6. **Synthesize.** The LLM uses the query and collected evidence to produce a useful answer, with source links or references tied to the results when possible.
7. **Display the workspace.** The user sees the AI answer and individual source panels together. Panels can be inspected, resized, rearranged, or closed as the interface supports them.
8. **Extend the research.** The user selects **+**, chooses a source/tool, and the application adds a panel and automatically runs the current query in that source. The user can also update the query and start a new research run.

## 8. Agent behavior and reasoning

The agent is a planner and coordinator operating within an explicit set of capabilities. It should not invent tools or assume every website has a working integration. Each available tool is described in the registry by its name, purpose, supported inputs, output shape, and any operational limitations.

For each query, the agent should:

- Classify the task at a practical level: general explanation, current information, video demonstration, visual examples, reference lookup, or site-specific research.
- Choose a small, relevant set of sources rather than launching every tool for every query.
- Create focused search terms or sub-questions where that improves coverage.
- Prefer source actions that can return inspectable evidence and links.
- Clearly distinguish retrieved source content from its own synthesis.
- Report unavailable or failed sources without pretending they succeeded.
- Avoid unnecessary model calls: ordinary UI interactions, panel rearrangement, and routine formatting should not invoke the LLM. The LLM is primarily used for query interpretation, tool selection when needed, and evidence synthesis.
- Keep each run bounded with configurable timeouts, result limits, and a cap on planned source actions to control latency and API-credit usage.

The system should make the research path visible, for example by listing selected sources and their status. A future iteration may include a fuller strategy explanation, but the initial implementation can expose the plan in a concise “Research plan” area.

## 9. Tool and source registry

The registry is the contract between the planner and the application's capabilities. It makes available sources explicit, allows capabilities to be enabled or disabled, and provides a place to document source limitations.

Potential registry entries include:

| Tool/source | Purpose | Typical output |
| --- | --- | --- |
| Google web search | General web discovery through a browser-accessible search interface or an approved search integration | Result titles, snippets, URLs |
| YouTube search | Find relevant videos and demonstrations | Video titles, channels, thumbnails, URLs, descriptions |
| Wikipedia | Fast encyclopedic orientation and topic lookup | Article title, summary, URL, extracted sections |
| Image search | Find visual examples relevant to the query | Image thumbnails, captions, source pages, image URLs where available |
| Specific website | Search or browse a configured or user-requested domain | Page titles, excerpts, URLs, extracted text |
| Open page | Visit a URL supplied by the planner or user | Page metadata and readable page content |
| AI answer mode | Synthesize the query and collected evidence | Structured answer, key points, citations/links to retrieved sources |

An entry should define a stable tool identifier, user-facing label, description, input schema, output schema, execution adapter, availability status, and limits. A source may use Playwright-driven browser interaction or a direct API where one is available and appropriate. Search providers and websites can change their page structure or access policies, so adapters should fail clearly and be replaceable.

The **+** action uses this same registry. It presents available sources to the user; choosing one creates a panel and submits the active query to that tool. This gives the user a direct way to broaden or steer the agent's source selection.

## 10. UI and workspace concept

The main screen is organized around a text query and a collection of result panels:

- **Query bar:** Text field, submit action, and indication of the active query or research run.
- **Research plan/status:** A compact view of selected tools, progress, completion, or errors.
- **AI answer panel:** Synthesis with links back to the evidence used when available.
- **Source panels:** Separate results for web search, YouTube, Wikipedia, images, or configured sites.
- **Add source (+):** Opens the registry picker, adds the chosen panel, and runs the current query there automatically.
- **Panel controls:** Basic close and layout controls; later versions may add pinning, resizing, sorting, and per-panel query edits.

The workspace should keep source identity clear. Search results belong to their source panel, while the AI answer is labeled as a synthesis. Links should open the original source in a browser context that the user can inspect. The layout should work on a typical desktop screen first; responsive layouts can adapt the panels for narrower screens later.

## 11. Proposed architecture

### Web frontend and browser extension

A React web application manages the full research workspace: query input, run state, source panels, AI synthesis, and manual source picker. A small browser extension handles the cross-tab keyboard shortcut and Spotlight-style overlay, then opens the web app's results workspace in a new tab after submission. Both clients communicate with the backend through a small API; the extension does not run Playwright or call Groq.

### Backend and orchestration

A backend service receives research requests, validates them, invokes the planner, executes selected tools, normalizes results, and requests synthesis. Python is a reasonable initial backend choice because it works well with Playwright and has a straightforward ecosystem for API services and asynchronous orchestration. The interface should be kept clean enough that another backend could replace it later.

### Browser automation

Playwright controls a dedicated browser context for source interactions that require a browser. It can navigate to search pages, enter queries, open results, and extract readable page data. Browser automation should be isolated from the user's personal browser profile and should observe site access requirements. When a stable direct API or simpler adapter is appropriate, the registry can use that instead of browser automation.

### LLM provider

The LLM client connects to Groq using a key configured by the user. Groq request details should be isolated in a backend client module. The secret must be kept out of source control and browser-visible code, and sent only from the backend to Groq. The application should make model use deliberate to help the user manage their credits.

### Data flow

`Extension shortcut and overlay or web-app query → backend API → planner and registry → selected source adapters / Playwright → normalized evidence → Groq synthesis → web-app workspace panels`

Each adapter returns a common result envelope containing source/tool identity, query used, status, results, timestamps, and any actionable error. The front end can display results as soon as they arrive, while synthesis runs once sufficient evidence is available.

### Suggested open-source stack

- **Web frontend:** React, with a standard build tool and a component library or custom CSS as needed.
- **Quick-search entry point:** Lightweight browser extension for the cross-tab shortcut, Spotlight-style overlay, and new-tab handoff.
- **Browser automation:** Playwright.
- **Backend:** Python with a lightweight web framework and asynchronous request handling.
- **LLM:** Groq API called by the backend with the user's own API key/credits.
- **Persistence for MVP:** Minimal or none beyond transient session state; later versions may add saved research sessions and settings.
- **Development and packaging:** Open-source dependencies, environment-based configuration, and clear setup documentation.

This is a proposed starting stack rather than a fixed requirement. Provider terms, search access, and dependency choices should be checked when implementation begins.

## 12. Constraints and design considerations

- **API credits and cost:** LLM usage is not necessarily free or unlimited. The application should minimize calls, bound prompts and result counts, and make provider configuration clear.
- **Search access:** Browser-visible search pages can change, throttle traffic, require consent, or restrict automation. A source adapter may need maintenance or replacement.
- **Reliability:** Page layouts vary. Extraction should tolerate missing fields and return partial results or clear errors.
- **Source quality and freshness:** Results can be incomplete, outdated, promotional, or contradictory. The UI should retain links and make it easy to compare sources.
- **Attribution:** The synthesis should link claims to retrieved sources where the available evidence permits. The system should not fabricate citations.
- **Privacy:** Queries and retrieved page excerpts may be sent to the configured LLM provider for planning or synthesis. The product should explain this and avoid collecting unnecessary personal data.
- **Security:** Treat web page text and search results as untrusted input. Do not let page content override application instructions or trigger arbitrary code or unrestricted actions. Restrict navigation and tool inputs appropriately.
- **Browser isolation:** Use a managed browser context rather than the user's personal profile, and do not store session credentials in the MVP.
- **Latency:** Parallel searches can improve speed, but should be bounded to avoid unnecessary load and unpredictable costs.
- **Accessibility:** Provide keyboard-accessible query and panel controls, meaningful labels, and readable status/error messages.

## 13. MVP scope

The first usable version should prove the end-to-end research loop without trying to support every website.

### Include

- A text-only query field and a way to submit a research run.
- A backend planner that chooses from a small explicit tool registry.
- A limited set of working source adapters, initially general web search, Wikipedia, YouTube, and AI synthesis; image search and specific websites can be included if reliable adapters are available in the chosen environment.
- Playwright-based browser automation for the source flows that need it.
- A normalized result format and visible loading, success, empty, and error states.
- A desktop-oriented multi-panel workspace showing the synthesis and individual sources.
- A **+** source picker that adds a panel and automatically runs the current query in the selected source.
- Backend-only Groq API-key configuration, with no local-model requirement.
- Lightweight browser extension for the shortcut, Spotlight-style overlay, and handoff to the web app's results tab.
- Basic limits on source count, result count, timeouts, and LLM request size.
- Setup instructions, provider configuration guidance, and a short explanation of privacy and source limitations.

### Defer

- Account systems, synchronization, collaboration, and cloud-hosted user workspaces.
- Long-term storage, search history management, exports, and shareable research reports.
- A large plugin marketplace or arbitrary user-authored tools.
- Sophisticated browser memory, multi-step autonomous browsing, and unattended background research.
- Advanced citations, claim-level evidence verification, confidence scoring, and contradiction analysis.
- Personalization, saved research plans, scheduled monitoring, or notifications.
- Highly customized panel layouts and extensive mobile support.

## 14. Later enhancements

Once the MVP is reliable, possible extensions include:

- More providers and source adapters, including user-configured websites.
- A visible, editable research plan before or during execution.
- Better source-grounded citations and claim-to-evidence links.
- Follow-up queries that reuse gathered context without repeating every search.
- Saved sessions, notes, bookmarks, and export to Markdown or PDF.
- Search and extraction quality monitoring, adapter health checks, and retry policies.
- User preferences for default sources, source limits, and model selection.
- More flexible panel layouts, keyboard shortcuts, and accessible responsive behavior.
- Optional direct search APIs when their terms and costs are suitable.

## 15. Success criteria

The MVP will be successful when a user can invoke the extension from a browser tab, enter a text question in the Spotlight-style overlay, and land in a web-app workspace where selected sources, source-specific results, and a useful synthesis are visible and verifiable. The user should also be able to add a source through **+** and see the current query run in that new panel without re-entering it.

More specific measures can be set during implementation. Useful indicators include:

- The proportion of supported queries that produce at least one useful source result.
- Whether the selected sources match the query's content needs.
- Whether source panels preserve working links and clear provenance.
- Time from submission to first visible result and to completed synthesis.
- Number of failed or partial source runs and whether the errors are understandable.
- LLM calls and approximate credit use per research run.
- Whether users can extend a run using the manual source picker without losing the current workspace.

## 16. Connected planning documents

These companion plans describe the main system parts using the same architecture and terminology:

- [frontend_description.md](frontend_description.md): React research workspace and browser extension quick-search overlay.
- [backend_description.md](backend_description.md): API, run orchestration, source registry, progress updates, and Groq integration.
- [browser_automation_description.md](browser_automation_description.md): Playwright worker, source adapters, browser isolation, and extraction.

The backend is the coordination boundary between clients and automation. The extension provides quick query entry; it does not run Playwright. Browser automation returns evidence to the backend, which streams it to the web app and sends bounded evidence to Groq for synthesis.

## 17. Summary

The project is an AI-assisted, text-only browser research system with a lightweight extension for quick entry and a separate React web app for the full workspace. Its agent plans research using a visible registry of tools, searches relevant web sources through Playwright or suitable adapters, and presents source results beside a Groq-backed synthesis. A manual **+** action lets users add a source panel and run the active query there. The backend calls Groq using the user's key and credits; the project does not depend on local models or include voice/audio features.
