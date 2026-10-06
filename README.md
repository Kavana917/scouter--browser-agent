# Scouter

Scouter is a research workspace with a React frontend and a FastAPI backend. The frontend creates live research runs against the local API. Source adapters use isolated Playwright contexts for DuckDuckGo, YouTube, and Bing Images, plus direct APIs for Wikipedia and Crossref. Groq generates the synthesis when a server-side API key is configured.

## Run the app locally

Start the API in one terminal:

```powershell
cd backend
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
# Add GROQ_API_KEY to backend/.env when you have it.
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the web app in a second terminal from the repository root:

```powershell
npm install
npm run dev
```

Open `http://localhost:5173`. The API health check is at `http://localhost:8000/health`, and interactive API documentation is at `http://localhost:8000/docs`.

Run data is held in memory and disappears when the backend restarts. `backend/.env` is ignored by Git. **Open a page** reads public HTTP and HTTPS pages in an isolated browser, with private/local addresses and cross-host redirects blocked.
