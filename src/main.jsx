import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity, ArrowDown, ArrowLeft, ArrowRight, ArrowUpRight, BookOpen,
  Check, CheckCheck, ChevronDown, Clock3, Command, Compass, ExternalLink,
  FileText, Globe2, Image, Layers2, Lightbulb, Link2, LoaderCircle,
  Plus, Search, Settings2, Sparkles, Youtube, X
} from 'lucide-react';
import { api, sourcePresentation } from './api';
import './styles.css';
import './browser.css';

const sourceCatalog = [
  { id: 'web', name: 'Web search', desc: 'Find useful pages across the web', icon: Globe2, color: 'blue' },
  { id: 'youtube', name: 'YouTube', desc: 'Videos, explainers, and demos', icon: Youtube, color: 'red' },
  { id: 'wikipedia', name: 'Wikipedia', desc: 'Quick context and background', icon: BookOpen, color: 'ink' },
  { id: 'images', name: 'Images', desc: 'Visual references and examples', icon: Image, color: 'violet' },
];

const seedSources = [
  { id: 'web', name: 'Web search', state: 'complete', count: '8 pages', icon: Globe2, color: 'blue', results: [
    { title: 'The quiet craft of Japanese joinery', domain: 'japanhouse.jp', desc: 'A look at the traditions, tools and principles behind timber joinery, and the way precision makes complex structures possible.', age: '12 min read' },
    { title: 'Japanese woodworking: a guide to joinery', domain: 'woodandshop.com', desc: 'From the mortise and tenon to the interlocking kanawa tsugi, explore the joints that make Japanese timber construction distinctive.', age: '8 min read' },
    { title: 'Joinery in traditional Japanese architecture', domain: 'architectuul.com', desc: 'How Japanese carpenters developed remarkably strong joints without nails, and why the techniques still matter today.', age: '6 min read' },
  ]},
  { id: 'youtube', name: 'YouTube', state: 'complete', count: '4 videos', icon: Youtube, color: 'red', results: [
    { title: 'Why Japanese wood joints are so strong', domain: 'YouTube · 12:48', desc: 'A visual tour through the geometry and craft of traditional timber connections.', age: '12:48' },
    { title: 'Making a Japanese sliding dovetail', domain: 'YouTube · 18:21', desc: 'A hands-on demonstration of a classic woodworking joint, from layout to final fit.', age: '18:21' },
  ]},
  { id: 'wikipedia', name: 'Wikipedia', state: 'complete', count: '1 article', icon: BookOpen, color: 'ink', results: [
    { title: 'Japanese carpentry', domain: 'en.wikipedia.org', desc: 'Japanese carpentry is associated with elaborate wood joints and a long tradition of timber construction. Its techniques are used in temples, shrines and homes.', age: 'Updated recently' },
  ]},
];

const capabilities = [
  { id: 'web', name: 'Web search', desc: 'Search the wider web for useful pages', icon: Globe2, color: 'blue', enabled: true },
  { id: 'youtube', name: 'YouTube', desc: 'Search and watch videos in a mini viewer.', icon: Youtube, color: 'red', enabled: true },
  { id: 'wikipedia', name: 'Wikipedia', desc: 'Get a fast overview of the topic', icon: BookOpen, color: 'ink', enabled: true },
  { id: 'images', name: 'Image search', desc: 'Find visual references with source-page attribution.', icon: Image, color: 'violet', enabled: true },
  { id: 'papers', name: 'Research papers', desc: 'Look for scholarly sources', icon: FileText, color: 'green', enabled: true },
  { id: 'open_page', name: 'Open a page', desc: 'Read a public web page in a private mini viewer.', icon: ExternalLink, color: 'ink', enabled: true },
];

const iconByTool = { web: Globe2, wikipedia: BookOpen, papers: FileText, youtube: Youtube, images: Image, open_page: ExternalLink };
const terminalStates = new Set(['completed', 'partial', 'failed', 'cancelled']);

function presentSource(source) {
  const style = sourcePresentation(source.tool_id || source.id);
  return { ...source, id: source.tool_id || source.id, name: source.label || source.name || style.name,
    icon: iconByTool[style.icon] || Globe2, color: style.color, count: source.count || resultCount(source.results || []),
    results: source.results || [] };
}

function resultCount(results) {
  if (!results.length) return 'No results';
  return `${results.length} ${results.length === 1 ? 'result' : 'results'}`;
}

function App() {
  const [query, setQuery] = useState('');
  const [runId, setRunId] = useState(() => new URLSearchParams(window.location.search).get('run_id'));
  const [activeQuery, setActiveQuery] = useState('');
  const [page, setPage] = useState(() => new URLSearchParams(window.location.search).has('run_id') ? 'workspace' : 'home');
  const [sources, setSources] = useState([]);
  const [answer, setAnswer] = useState({ status: 'pending', text: 'Research is underway.', references: [] });
  const [runStatus, setRunStatus] = useState('queued');
  const [capabilityList, setCapabilityList] = useState(capabilities);
  const [sourceLimit, setSourceLimit] = useState(6);
  const [isStarting, setIsStarting] = useState(false);
  const [streamVersion, setStreamVersion] = useState(0);
  const [openPageUrl, setOpenPageUrl] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('All sources');
  const [toast, setToast] = useState('');

  const flash = (message) => { setToast(message); window.setTimeout(() => setToast(''), 2800); };

  useEffect(() => {
    api.getTools().then(({ tools, max_sources_per_run }) => {
      setSourceLimit(max_sources_per_run || 6);
      setCapabilityList(tools.map((tool) => {
        const style = sourcePresentation(tool.tool_id);
        return { ...tool, id: tool.tool_id, name: tool.label, desc: tool.description, icon: iconByTool[style.icon] || Globe2, color: style.color };
      }));
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!runId) return undefined;
    let disposed = false;
    let events;
    api.getRun(runId).then((snapshot) => {
      if (disposed) return;
      setActiveQuery(snapshot.query);
      setRunStatus(snapshot.status);
      setSources((snapshot.sources || []).map(presentSource));
      setAnswer(snapshot.answer || { status: 'pending', text: '', references: [] });
      if (terminalStates.has(snapshot.status)) return;
      events = new EventSource(api.eventsUrl(runId, snapshot.last_event_id || 0));
      const listen = (type, handler) => events.addEventListener(type, (event) => {
        if (disposed) return;
        try { handler(JSON.parse(event.data)); } catch { /* Ignore malformed stream data. */ }
      });
      listen('run.status', ({ status }) => setRunStatus(status));
      listen('source.added', ({ source }) => setSources((current) => {
        const existing = current.findIndex((item) => item.source_execution_id === source.source_execution_id || (item.id === source.tool_id && item.source_execution_id?.startsWith('pending-') && (!source.url || item.url === source.url)));
        if (existing < 0) return [...current, presentSource(source)];
        return current.map((item, index) => index === existing ? presentSource(source) : item);
      }));
      listen('source.status', ({ source_execution_id, status, error }) => setSources((current) => current.map((item) => item.source_execution_id === source_execution_id ? { ...item, status, error } : item)));
      listen('source.results', ({ source_execution_id, results }) => setSources((current) => current.map((item) => item.source_execution_id === source_execution_id ? { ...item, results, count: resultCount(results) } : item)));
      listen('answer.delta', ({ delta }) => setAnswer((current) => ({ ...current, status: 'streaming', text: `${current.status === 'streaming' ? current.text : ''}${delta}` })));
      listen('answer.updated', ({ answer: updated }) => setAnswer(updated));
      listen('run.completed', ({ status }) => { setRunStatus(status); events?.close(); });
      events.onerror = () => {};
    }).catch((error) => {
      if (!disposed) { setRunStatus('failed'); setAnswer({ status: 'unavailable', text: error.message || 'Could not load this research run.', references: [] }); }
    });
    return () => { disposed = true; events?.close(); };
  }, [runId, streamVersion]);

  async function startResearch(value) {
    const clean = value.trim();
    if (!clean || isStarting) return;
    setIsStarting(true);
    setQuery('');
    try {
      const created = await api.createRun(clean);
      const nextUrl = new URL(window.location.href);
      nextUrl.searchParams.set('run_id', created.run_id);
      window.history.pushState({}, '', nextUrl);
      setRunId(created.run_id);
      setActiveQuery(clean);
      setSources([]);
      setAnswer({ status: 'pending', text: 'Research is underway.', references: [] });
      setRunStatus(created.status);
      setPage('workspace');
      flash('Research started');
    } catch (error) {
      setQuery(clean);
      flash(error.message || 'Could not connect to the Scouter API');
    } finally { setIsStarting(false); }
  }

  function goHome() {
    const nextUrl = new URL(window.location.href);
    nextUrl.searchParams.delete('run_id');
    window.history.replaceState({}, '', nextUrl);
    setRunId(null);
    setPage('home');
  }

  async function addSource(tool, url) {
    if (!tool.enabled) {
      flash(`${tool.name} is not available yet`);
      return;
    }
    if (tool.id !== 'open_page' && sources.some((source) => source.id === tool.id)) {
      flash(`${tool.name} is already in this workspace`);
      return;
    }
    if (sources.length >= sourceLimit) {
      flash(`This run already has ${sourceLimit} sources. Start a new research run to add more.`);
      return;
    }
    const optimistic = presentSource({ tool_id: tool.id, label: tool.name, source_execution_id: `pending-${tool.id}-${Date.now()}`, status: 'running', count: 'Searching', results: [], url });
    setSources((current) => [...current, optimistic]);
    setPickerOpen(false);
    flash(`${tool.name} added · running your query`);
    try {
      if (!runId) throw new Error('Start a research run before adding a source.');
      const { source } = await api.addSource(runId, tool.id, url);
      setSources((current) => current.map((item) => item.source_execution_id === optimistic.source_execution_id ? presentSource(source) : item));
      setStreamVersion((version) => version + 1);
    } catch (error) {
      setSources((current) => current.filter((item) => item.source_execution_id !== optimistic.source_execution_id));
      flash(error.message || 'Could not add this source');
    }
  }

  const shownSources = activeTab === 'All sources' ? sources : sources.filter((source) => source.name === activeTab);
  const sourceLimitReached = sources.length >= sourceLimit;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={goHome} aria-label="Scouter home">
          <span className="brand-mark"><Compass size={18} strokeWidth={2.2} /></span>
          <span className="brand-name">scouter<span className="brand-period">.</span></span>
        </button>
        <div className="sidebar-actions">
          <button className="new-research" onClick={() => { goHome(); setQuery(''); }}><Plus size={16} /> New research <span className="shortcut"><Command size={11} /> K</span></button>
          <button className={`side-link ${page === 'home' ? 'selected' : ''}`} onClick={goHome}><Search size={16} /> Explore</button>
        </div>
        <div className="side-section">
          <div className="section-label">YOUR WORKSPACE <button aria-label="Workspace settings"><Settings2 size={14} /></button></div>
          <button className="history-item active-history" onClick={() => setPage('workspace')}><span className="history-dot live" /> Japanese joinery <span className="history-more">···</span></button>
          <button className="history-item" onClick={() => startResearch('The future of urban gardens')}><span className="history-dot" /> Urban gardens in 2026</button>
          <button className="history-item" onClick={() => startResearch('A practical guide to analog photography')}><span className="history-dot" /> Getting started with film</button>
        </div>
        <div className="sidebar-bottom">
          <div className="usage-card"><div className="usage-top"><span className="usage-icon"><Sparkles size={14} /></span><span>Research credits</span><span className="usage-value">8 / 10</span></div><div className="usage-track"><span /></div><p>Credits reset in 12 days</p></div>
          <button className="profile"><span className="avatar">S</span><span className="profile-copy"><b>Sam Taylor</b><small>Personal workspace</small></span><ChevronDown size={15} /></button>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumbs"><span>My workspace</span><span className="crumb-slash">/</span><b>{page === 'home' ? 'Explore' : 'Research desk'}</b></div>
          <div className="topbar-right"><span className="connection"><span /> All systems ready</span><button className="icon-button" aria-label="Activity"><Activity size={17} /></button><span className="avatar top-avatar">S</span></div>
        </header>

        {page === 'home' ? <HomePage query={query} setQuery={setQuery} startResearch={startResearch} /> : (
          <section className="workspace-page">
            <div className="workspace-heading">
              <div className="back-row"><button className="back-button" onClick={goHome}><ArrowLeft size={15} /> All research</button><span className="demo-label"><span /> LIVE RESEARCH</span></div>
              <div className="heading-line"><div><p className="eyebrow">RESEARCH SESSION <span className="eyebrow-divider">·</span> JUST NOW</p><h1>{activeQuery}</h1></div><button className="share-button" onClick={() => flash('Share links will be available when the backend is connected')}><Link2 size={15} /> Share</button></div>
              <div className="run-meta"><span className="run-status"><Check size={13} /> {runStatus === 'completed' ? 'Research complete' : runStatus === 'failed' ? 'Research needs attention' : runStatus === 'partial' ? 'Research partially complete' : runStatus === 'synthesizing' ? 'Writing your summary' : 'Research in progress'}</span><span className="meta-separator" /><span><Layers2 size={14} /> {sources.length} sources</span><span className="meta-separator" /><span><Clock3 size={14} /> {answer.status === 'completed' ? 'Summary ready' : 'Gathering evidence'}</span></div>
            </div>

            <div className="answer-card">
              <div className="answer-top"><div className="answer-label"><span className="sparkle-badge"><Sparkles size={15} /></span><div><b>Research summary</b><span>AI-generated overview <span className="dot-sep">·</span> Based on {sources.length} sources</span></div></div><button className="answer-menu" onClick={() => flash('Answer actions')} aria-label="Answer actions">···</button></div>
              <div className="answer-body">
                {(answer.text || 'Waiting for retrieved evidence…').split(/\n\s*\n/).map((paragraph, index) => <p key={index}>{paragraph}</p>)}
              </div>
              <div className="answer-footer"><span><Sparkles size={13} /> {answer.status === 'completed' ? 'Synthesized from retrieved sources' : answer.status === 'unavailable' ? 'Synthesis unavailable · source results may still be available' : 'Synthesizing retrieved sources'}</span><button onClick={() => navigator.clipboard?.writeText(answer.text).then(() => flash('Answer copied to clipboard')).catch(() => flash('Could not copy the answer'))}><CheckCheck size={14} /> Copy answer</button></div>
            </div>

            <div className="sources-heading" id="sources"><div><p className="eyebrow">YOUR SOURCES</p><h2>Explore the research</h2></div><button className="add-source-button" onClick={() => setPickerOpen(true)}><Plus size={15} /> Add source</button></div>
            <div className="source-tabs" role="tablist" aria-label="Filter sources">
              {['All sources', ...sources.map((s) => s.name)].map((tab) => <button key={tab} role="tab" aria-selected={activeTab === tab} className={activeTab === tab ? 'active-tab' : ''} onClick={() => setActiveTab(tab)}>{tab}{tab === 'All sources' && <span className="tab-count">{sources.length}</span>}</button>)}
            </div>
            <div className={`source-grid ${shownSources.length === 1 ? 'single-grid' : ''}`}>
              {shownSources.map((source) => <SourceCard key={source.source_execution_id || source.id} source={source} />)}
              <button className="add-card" onClick={() => setPickerOpen(true)}><span className="add-card-icon"><Plus size={17} /></span><b>Bring in another source</b><span>Keep exploring this question from a new angle.</span><span className="add-card-link">Browse sources <ArrowRight size={14} /></span></button>
            </div>
            <div className="workspace-bottom-note"><Lightbulb size={15} /><span>Want a different perspective? Add a source and we’ll search your question there.</span><button onClick={() => setPickerOpen(true)}>Add a source <ArrowRight size={13} /></button></div>
          </section>
        )}
      </main>

      {pickerOpen && <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && setPickerOpen(false)}><div className="source-modal" role="dialog" aria-modal="true" aria-labelledby="picker-title"><div className="modal-header"><div><span className="eyebrow">GROW YOUR RESEARCH</span><h2 id="picker-title">Add a source</h2><p>Choose another place to look. We’ll search the same question there.</p></div><button className="icon-button" aria-label="Close source picker" onClick={() => { setPickerOpen(false); setOpenPageUrl(''); }}><X size={18} /></button></div><div className="capability-list">{capabilityList.map((tool) => { const Icon = tool.icon; const exists = tool.id !== 'open_page' && sources.some((s) => s.id === tool.id); return <button className={`capability ${exists ? 'capability-used' : ''}`} key={tool.tool_id || tool.id} disabled={exists || !tool.enabled || sourceLimitReached} onClick={() => { if (tool.id === 'open_page') setOpenPageUrl('https://'); else addSource(tool); }}><span className={`source-icon ${tool.color}`}><Icon size={18} /></span><span className="cap-copy"><b>{tool.name}</b><small>{tool.desc}</small></span>{exists ? <span className="already-added"><Check size={13} /> Added</span> : sourceLimitReached ? <span className="already-added">Run limit reached</span> : tool.enabled ? <ArrowRight size={16} className="cap-arrow" /> : <span className="already-added">Unavailable</span>}</button>; })}</div>{sourceLimitReached && <p className="source-limit-note">This run has reached {sourceLimit} sources. Start a new research run to add more.</p>}{openPageUrl && <form className="open-page-form" onSubmit={(event) => { event.preventDefault(); const tool = capabilityList.find((item) => item.id === 'open_page'); if (tool) addSource(tool, openPageUrl.trim()); setOpenPageUrl(''); }}><label htmlFor="open-page-url">Page URL</label><div><input id="open-page-url" type="url" required value={openPageUrl} onChange={(event) => setOpenPageUrl(event.target.value)} placeholder="https://example.com/page" /><button type="submit" disabled={sourceLimitReached}>Read page <ArrowRight size={14} /></button></div><small>Public HTTP and HTTPS pages are supported.</small></form>}<div className="modal-footnote"><Sparkles size={13} /> Your original question will be used automatically.</div></div></div>}
      {toast && <div className="toast" role="status"><Check size={15} /> {toast}</div>}
    </div>
  );
}

function HomePage({ query, setQuery, startResearch }) {
  const examples = ['How do Japanese wood joints work?', 'What makes a city good for cycling?', 'A beginner’s guide to natural wine'];
  return <section className="home-page"><div className="home-orb orb-one" /><div className="home-orb orb-two" /><div className="home-content"><div className="welcome-label"><span className="welcome-icon"><Compass size={15} /></span> YOUR RESEARCH DESK</div><h1>Good research<br />starts with <em>curiosity.</em></h1><p className="home-intro">One question, thoughtfully explored. Scouter brings the useful sources together so you can focus on what matters.</p><form className="query-composer" onSubmit={(e) => { e.preventDefault(); startResearch(query); }}><textarea aria-label="Your research question" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); startResearch(query); } }} placeholder="What would you like to understand?" rows={2} /><div className="composer-bottom"><span className="composer-hint"><Sparkles size={14} /> Research across trusted sources</span><button disabled={!query.trim()} type="submit">Start researching <ArrowRight size={15} /></button></div></form><div className="example-queries"><span className="examples-label">A LITTLE INSPIRATION</span>{examples.map((example, i) => <button key={example} onClick={() => startResearch(example)}><span className="example-number">0{i + 1}</span>{example}<ArrowUpRight size={14} /></button>)}</div><div className="home-footnote"><span className="green-dot" /> Your research stays in this workspace <span className="footnote-divider">·</span> No search history shared</div></div><div className="home-decoration"><span className="orbit orbit-a" /><span className="orbit orbit-b" /><span className="orbit orbit-c" /><div className="center-mark"><Compass size={30} strokeWidth={1.35} /></div><span className="orbit-label label-a">curiosity</span><span className="orbit-label label-b">context</span><span className="orbit-label label-c">clarity</span><div className="float-note note-a"><span className="note-mark">✳</span><span><b>Start anywhere</b><small>We’ll find a way in</small></span></div><div className="float-note note-b"><span className="note-check"><Check size={13} /></span><span><b>Stay source-grounded</b><small>Every answer, traceable</small></span></div></div></section>;
}

function SourceCard({ source }) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const Icon = source.icon || Globe2;
  const state = source.state || source.status || 'queued';
  const statusLabel = state === 'completed' ? 'Complete' : state === 'running' ? 'Searching' : state === 'empty' ? 'No results found' : state === 'failed' || state === 'unavailable' || state === 'timed_out' ? 'Could not load' : 'Queued';
  const domain = (url) => { try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url || 'Source'; } };
  const selected = source.results[selectedIndex] || source.results[0];
  const videoId = selected?.url?.match(/[?&]v=([^&]+)/)?.[1] || selected?.url?.match(/youtu\.be\/([^?&/]+)/)?.[1];
  const content = selected?.content || selected?.snippet || source.error?.message || 'Choose a result to preview it here.';
  return <article className="source-card" id={`source-${source.id}`}>
    <div className="source-card-header"><div className="source-title"><span className={`source-icon ${source.color}`}><Icon size={16} /></span><div><b>{source.name}</b><small>{source.count || 'Source'}</small></div></div><div className={`source-state ${state}`}><span />{statusLabel}</div></div>
    {state === 'running' || state === 'queued' ? <div className="source-loading"><LoaderCircle size={18} className="spin" /><span>{state === 'queued' ? 'Queued to search…' : 'Searching for useful results…'}</span></div> : source.results.length ? <div className="source-workspace"><div className="result-list">{source.results.map((result, i) => <div className={`result-item ${selectedIndex === i ? 'selected-result' : ''}`} key={`${result.title}-${i}`}>
      {result.thumbnail_url && <a className="image-result" href={result.url} target="_blank" rel="noreferrer"><img src={result.thumbnail_url} loading="lazy" referrerPolicy="no-referrer" alt={result.title} /><span>View source page</span></a>}
      <div className="result-domain"><span className="favicon">{source.id === 'youtube' ? '▶' : domain(result.url || result.domain)?.[0]?.toUpperCase()}</span><span>{domain(result.url || result.domain)}</span><span className="result-age">· {result.age || 'Retrieved just now'}</span></div>
      <button className="result-title" onClick={() => setSelectedIndex(i)}>{result.title}<ArrowRight size={12} /></button><p>{result.snippet || result.desc || ''}</p>
      <a className="result-external" href={result.url || '#'} target="_blank" rel="noreferrer" onClick={(e) => { if (!result.url) e.preventDefault(); }}>Open source <ExternalLink size={11} /></a>
    </div>)}</div><div className="mini-viewer" aria-live="polite"><div className="mini-viewer-top"><span><span className="viewer-live-dot" /> MINI VIEWER</span>{selected?.url && <a href={selected.url} target="_blank" rel="noreferrer">Open full page <ExternalLink size={11} /></a>}</div>{source.id === 'youtube' && videoId ? <iframe className="youtube-player" src={`https://www.youtube-nocookie.com/embed/${encodeURIComponent(videoId)}`} title={selected.title} loading="lazy" referrerPolicy="strict-origin-when-cross-origin" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowFullScreen /> : <div className="mini-viewer-copy"><b>{selected?.title || 'Source preview'}</b><p>{content}</p>{source.id === 'wikipedia' && <span>Wikipedia article preview</span>}</div>}</div></div> : <div className="source-empty"><b>{state === 'empty' ? 'No results came back from this source.' : 'There are no results to show yet.'}</b><span>{source.error?.message || 'Try another source or adjust the search wording.'}</span></div>}
    {source.error && state !== 'running' && <p className="source-error">{source.error.message}</p>}
    {source.results.length > 1 && <div className="result-count-note">{source.results.length} results · select one to preview</div>}
  </article>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
