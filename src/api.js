const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      message = payload.detail?.message || payload.detail || message;
    } catch { /* use the status message */ }
    throw new Error(message);
  }
  return response.json();
}

export const api = {
  createRun: (query) => request('/api/v1/research-runs', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, client_source: 'web_app' }),
  }),
  getRun: (runId) => request(`/api/v1/research-runs/${encodeURIComponent(runId)}`),
  getTools: () => request('/api/v1/tools'),
  addSource: (runId, toolId, url) => request(`/api/v1/research-runs/${encodeURIComponent(runId)}/sources`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool_id: toolId, ...(url ? { url } : {}) }),
  }),
  eventsUrl: (runId, after = 0) => `${API_BASE}/api/v1/research-runs/${encodeURIComponent(runId)}/events?after=${after}`,
};

export function sourcePresentation(toolId) {
  const known = {
    web: { name: 'Web search', icon: 'web', color: 'blue' },
    wikipedia: { name: 'Wikipedia', icon: 'wikipedia', color: 'ink' },
    papers: { name: 'Research papers', icon: 'papers', color: 'green' },
    youtube: { name: 'YouTube', icon: 'youtube', color: 'red' },
    images: { name: 'Images', icon: 'images', color: 'violet' },
  };
  return known[toolId] || { name: toolId, icon: 'web', color: 'blue' };
}
