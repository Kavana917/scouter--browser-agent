# Scouter API

FastAPI backend for research runs, registered sources, SSE updates, and optional Groq synthesis.

## Start locally

From this directory, create a virtual environment, install `requirements.txt`, install Chromium for the installed Playwright version, copy `.env.example` to `.env`, and set `GROQ_API_KEY`. Then run:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
# Add GROQ_API_KEY to .env.
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API docs are at `http://127.0.0.1:8000/docs`; the health route is `/health`.

Run state is currently held in memory and is cleared when the process restarts. Browser searches use isolated Playwright Chromium contexts for DuckDuckGo, YouTube, and Bing Images. Wikipedia and Crossref use their direct public APIs. Groq is optional: without a key, runs still retrieve and display source results, while the synthesis is marked unavailable.

`/health` reports whether the browser runtime started. **Open a page** accepts public HTTP or HTTPS pages. Its isolated browser rejects local/private network addresses, non-web schemes, unusual ports, and redirects to a different host.
