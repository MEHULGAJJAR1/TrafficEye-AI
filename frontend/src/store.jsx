import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { api, downloadReport } from './api';
import { params } from './utils';

const Context = createContext(null);
export const useTraffic = () => useContext(Context);
const initialFilters = { vehicle_class: '', violation_type: '', source: 'all', min_confidence: 0, date_from: '', date_to: '' };

export function TrafficProvider({ children }) {
  const [auth, setAuth] = useState(null);
  const [page, setPageState] = useState(() => location.hash.slice(1) || 'overview');
  const [jobs, setJobs] = useState([]);
  const [selectedId, setSelectedId] = useState(() => localStorage.getItem('te-selected') || '');
  const [filters, setFilters] = useState(initialFilters);
  const [system, setSystem] = useState(null);
  const [config, setConfig] = useState(null);
  const [stats, setStats] = useState(null);
  const [tracks, setTracks] = useState({ items: [], total: 0 });
  const [violations, setViolations] = useState({ items: [], total: 0 });
  const [events, setEvents] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [toasts, setToasts] = useState([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [stream, setStream] = useState('idle');
  const [revision, setRevision] = useState(0);
  const mounted = useRef(true);
  const toast = useCallback((message, type = 'success') => {
    const id = Date.now() + Math.random();
    setToasts(t => [...t.slice(-3), { id, message, type }]);
    setTimeout(() => { if (mounted.current) setToasts(t => t.filter(v => v.id !== id)); }, 6000);
  }, []);
  const refresh = useCallback(() => setRefreshKey(k => k + 1), []);
  const navigate = useCallback((next) => { setPageState(next); location.hash = next; window.scrollTo({ top: 0, behavior: 'smooth' }); }, []);
  const selectJob = useCallback((id) => { setSelectedId(id); localStorage.setItem('te-selected', id); }, []);
  const queryFilters = useMemo(() => ({ ...filters, job_id: selectedId && selectedId !== 'all-job' ? selectedId : undefined }), [filters, selectedId]);
  const query = useMemo(() => params(queryFilters), [queryFilters]);
  const selectedJob = jobs.find(j => j.id === selectedId) || null;

  useEffect(() => {
    mounted.current = true;
    const expired = () => { setAuth(false); setStats(null); setJobs([]); toast('Your session expired. Unlock the workspace again.', 'error'); };
    const hash = () => setPageState(location.hash.slice(1) || 'overview');
    window.addEventListener('session-expired', expired);
    window.addEventListener('hashchange', hash);
    api('/auth/status').then(data => setAuth(data.authenticated)).catch(err => { setAuth(false); setError(err.message); });
    return () => { mounted.current = false; window.removeEventListener('session-expired', expired); window.removeEventListener('hashchange', hash); };
  }, [toast]);

  useEffect(() => {
    if (!auth) return;
    let cancelled = false;
    let running = false;
    const controller = new AbortController();
    async function load() {
      if (running) return;
      running = true;
      try {
        const [j, s, c] = await Promise.all([api('/jobs', { signal: controller.signal }), api('/system', { signal: controller.signal }), api('/config', { signal: controller.signal })]);
        if (cancelled) return;
        setJobs(j.items); setSystem(s); setConfig(c);
        setSelectedId(current => {
          const next = current === 'all-job' || j.items.some(v => v.id === current) ? current : (j.items[0]?.id || '');
          localStorage.setItem('te-selected', next);
          return next;
        });
      } catch (err) { if (!cancelled && err.name !== 'AbortError') setError(err.message); }
      finally { running = false; }
    }
    load();
    const interval = setInterval(load, 5000);
    return () => { cancelled = true; controller.abort(); clearInterval(interval); };
  }, [auth, refreshKey]);

  useEffect(() => {
    if (!auth) return;
    let cancelled = false;
    let running = false;
    const controller = new AbortController();
    setLoading(true);
    async function load() {
      if (running) return;
      running = true;
      try {
        const eventQuery = params({ job_id: queryFilters.job_id, limit: 12 });
        const [a, t, v, e] = await Promise.all([api(`/analytics?${query}`, { signal: controller.signal }), api(`/tracks?${query}&limit=8`, { signal: controller.signal }), api(`/violations?${query}&limit=8`, { signal: controller.signal }), api(`/events?${eventQuery}`, { signal: controller.signal })]);
        if (cancelled) return;
        setStats(a); setTracks(t); setViolations(v); setEvents(e.items); setError(''); setLoading(false); setRevision(k => k + 1);
      } catch (err) { if (!cancelled && err.name !== 'AbortError') { setError(err.message); setLoading(false); } }
      finally { running = false; }
    }
    load();
    const interval = setInterval(load, 2500);
    return () => { cancelled = true; controller.abort(); clearInterval(interval); };
  }, [auth, query, queryFilters.job_id, refreshKey]);

  useEffect(() => {
    if (!auth || !selectedId || selectedId === 'all-job') { setStream('idle'); return; }
    let disposed = false, reconnectTimer, fallbackTimer, failures = 0;
    let socket;
    const updateJob = job => setJobs(values => values.some(v => v.id === job.id) ? values.map(v => v.id === job.id ? job : v) : [job, ...values]);
    const poll = async () => {
      try { const job = await api(`/jobs/${selectedId}`); if (!disposed) updateJob(job); } catch { /* main polling surface reports errors */ }
    };
    function connect() {
      if (disposed) return;
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      socket = new WebSocket(`${protocol}//${location.host}/api/ws/jobs/${selectedId}`);
      socket.onopen = () => { if (!disposed) { setStream('websocket'); failures = 0; clearInterval(fallbackTimer); } };
      socket.onmessage = event => {
        if (disposed) return;
        try { const data = JSON.parse(event.data); if (data.type === 'job_update') updateJob(data.job); } catch { /* ignore malformed transport packet; polling remains authoritative */ }
      };
      socket.onerror = () => socket.close();
      socket.onclose = () => {
        if (disposed) return;
        setStream('polling');
        clearInterval(fallbackTimer);
        fallbackTimer = setInterval(poll, 1200);
        reconnectTimer = setTimeout(connect, Math.min(15000, 2000 * 2 ** failures++));
      };
    }
    connect();
    return () => { disposed = true; clearInterval(fallbackTimer); clearTimeout(reconnectTimer); socket?.close(); };
  }, [auth, selectedId]);

  const act = useCallback(async (name, task) => {
    setBusy(name);
    try { const value = await task(); refresh(); return value; }
    catch (err) { toast(err.message, 'error'); return null; }
    finally { if (mounted.current) setBusy(''); }
  }, [refresh, toast]);
  const exportCSV = useCallback((kind = 'violations') => act(`export-${kind}`, async () => {
    await downloadReport(params(queryFilters, { kind }), `trafficeye_${kind}.csv`);
    toast('CSV report downloaded. Source mode and timestamp basis are included.');
    return true;
  }), [queryFilters, act, toast]);
  const logout = async () => { await api('/auth/logout', { method: 'POST' }); setAuth(false); setJobs([]); setStats(null); setTracks({ items: [], total: 0 }); setViolations({ items: [], total: 0 }); setEvents([]); };

  const value = { auth, setAuth, page, navigate, jobs, selectedId, selectJob, selectedJob, filters, setFilters, queryFilters, query, system, config, stats, tracks, violations, events, error, setError, loading, busy, act, toast, toasts, setToasts, refresh, refreshKey, stream, revision, exportCSV, logout };
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function usePaged(endpoint, limit = 12, extra = {}) {
  const { queryFilters, refreshKey, revision, auth } = useTraffic();
  const [page, setPage] = useState(0);
  const [data, setData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const scope = params(queryFilters, extra);
  useEffect(() => { setPage(0); }, [scope]);
  useEffect(() => {
    if (!auth) return;
    const controller = new AbortController();
    const url = `${endpoint}?${scope}&limit=${limit}&offset=${page * limit}`;
    api(url, { signal: controller.signal }).then(value => { setData(value); setLoading(false); setError(''); }).catch(err => { if (err.name !== 'AbortError') { setError(err.message); setLoading(false); } });
    return () => controller.abort();
  }, [endpoint, scope, limit, page, revision, refreshKey, auth]);
  return { ...data, page, setPage, loading, error, limit };
}
