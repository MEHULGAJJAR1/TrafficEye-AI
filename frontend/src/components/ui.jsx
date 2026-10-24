import React, { useEffect, useRef, useState } from 'react';
import { Activity, ArrowDownLeft, ArrowUpRight, Check, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, Clock3, Download, Eye, FileVideo, Filter, Loader2, Pause, Play, Plus, Radio, RefreshCw, ScanLine, ShieldAlert, SlidersHorizontal, Square, TriangleAlert, X } from 'lucide-react';
import { api } from '../api';
import { useTraffic } from '../store';
import { duration, localDatetime, number, percent, shortId, time } from '../utils';

export function Logo({ compact = false }) {
  return <div className="brand"><span className="brand-mark"><Eye aria-hidden="true" size={26} strokeWidth={2.1}/><i/></span>{!compact && <div><span>TrafficEye<span className="brand-ai"> AI</span></span><small>TRAFFIC INTELLIGENCE</small></div>}</div>;
}
export function Spinner({ label = 'Loading…' }) { return <span className="inline-loader" role="status"><Loader2 aria-hidden="true" size={16} className="spin"/>{label}</span>; }
export function Empty({ icon: Icon = ScanLine, title = 'Nothing here yet', text, action, small = false }) {
  return <div className={`empty-state ${small ? 'compact' : ''}`}><span className="empty-icon"><Icon aria-hidden="true" size={25}/></span><h3>{title}</h3>{text && <p>{text}</p>}{action}</div>;
}
export function Tag({ children, tone = 'neutral', dot = false }) { return <span className={`tag ${tone}`}>{dot && <i/>}{children}</span>; }
export function Status({ value }) {
  const tone = ['completed', 'ready', 'online'].includes(value) ? 'green' : ['running', 'preparing', 'queued'].includes(value) ? 'cyan' : ['failed', 'interrupted', 'missing', 'error'].includes(value) ? 'red' : ['paused', 'cancelled', 'unconfirmed'].includes(value) ? 'amber' : 'neutral';
  return <Tag tone={tone} dot>{value?.replaceAll('_', ' ') || 'unknown'}</Tag>;
}
export function SourceTag({ mode }) { return mode === 'demo' ? <Tag tone="amber">SCRIPTED DEMO</Tag> : mode === 'real' ? <Tag tone="green">AI INFERENCE</Tag> : <Tag>NOT PROCESSED</Tag>; }
export function SectionTitle({ title, subtitle, action, icon: Icon }) { return <div className="section-heading"><div><h2>{Icon && <Icon aria-hidden="true" size={17}/>} {title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>; }
export function ErrorBox({ children, retry }) { return <div className="error-box" role="alert"><TriangleAlert aria-hidden="true" size={19}/><span>{children}</span>{retry && <button className="btn small" onClick={retry}><RefreshCw aria-hidden="true" size={14}/>Retry</button>}</div>; }
export function Notice({ children, tone = 'amber', icon: Icon = CircleHelp }) { return <div className={`notice ${tone}`}><Icon aria-hidden="true" size={17}/><div>{children}</div></div>; }
export function PageHeader({ title, eyebrow, description, actions }) { return <div className="page-header"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h1>{title}</h1><p>{description}</p></div><div className="page-actions">{actions}</div></div>; }
export function StatCard({ title, value, icon: Icon, color = 'teal', detail, foot, loading }) {
  return <article className={`stat-card ${color}`}><div className="stat-top"><span>{title}</span><span className="stat-icon"><Icon aria-hidden="true" size={19}/></span></div><div className={`stat-value ${loading ? 'skeleton-text' : ''}`}>{loading ? '—' : value}</div><div className="stat-bottom"><span>{detail}</span>{foot && <small>{foot}</small>}</div></article>;
}
export function Pager({ total, page, setPage, limit }) {
  return <div className="pager"><span>{total ? `${page * limit + 1}–${Math.min(total, (page + 1) * limit)} of ${number(total)}` : '0 records'}</span><div><button aria-label="Previous page" className="icon-btn" disabled={!page} onClick={() => setPage(page - 1)}><ChevronLeft aria-hidden="true" size={16}/></button><span>Page {page + 1} / {Math.max(1, Math.ceil(total / limit))}</span><button aria-label="Next page" className="icon-btn" disabled={(page + 1) * limit >= total} onClick={() => setPage(page + 1)}><ChevronRight aria-hidden="true" size={16}/></button></div></div>;
}

export function Modal({ title, children, onClose, wide = false }) {
  const root = useRef(null);
  useEffect(() => {
    const active = document.activeElement;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    root.current?.focus();
    const key = event => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab') {
        const nodes = [...root.current.querySelectorAll('button:not([disabled]),a[href],input,select,textarea,[tabindex="0"]')];
        if (!nodes.length) return;
        const first = nodes[0], last = nodes.at(-1);
        if (event.shiftKey && (document.activeElement === first || document.activeElement === root.current)) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', key);
    return () => { document.body.style.overflow = previous; document.removeEventListener('keydown', key); active?.focus(); };
  }, [onClose]);
  return <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}><section ref={root} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} className={`modal ${wide ? 'wide' : ''}`}><header><h2>{title}</h2><button className="icon-btn" aria-label="Close dialog" onClick={onClose}><X aria-hidden="true" size={20}/></button></header>{children}</section></div>;
}

export function EvidenceModal({ item, onClose }) {
  return <Modal title="Violation evidence" onClose={onClose} wide><img className="evidence-large" src={item.evidence_url} alt={`${item.violation_type} evidence for ${item.vehicle_class} ${item.track_id}`}/><div className="modal-body"><div className="row-between"><div><SourceTag mode={item.mode}/><h3>{item.violation_type} · {item.vehicle_class} #{item.track_id}</h3></div><a className="btn" href={`${item.evidence_url}?download=true`} download><Download aria-hidden="true" size={15}/>Save image</a></div><dl className="detail-grid"><div><dt>Video timestamp</dt><dd>{duration(item.video_time)} ({item.video_time.toFixed(2)}s)</dd></div><div><dt>Evidence confidence</dt><dd>{percent(item.confidence * 100)}</dd></div><div><dt>Consistent votes</dt><dd>{item.votes} sampled frames</dd></div><div><dt>Zone</dt><dd>{item.zone}</dd></div><div><dt>Reference UTC time</dt><dd>{item.occurred_at}</dd></div><div><dt>Job</dt><dd className="mono">{shortId(item.job_id)}</dd></div></dl><Notice tone="amber">{item.mode === 'demo' ? 'This image and its confidence are scripted demo evidence, not an AI prediction. ' : ''}Human review is required. Camera viewpoint, occlusion and image quality can make helmet/seatbelt classification unreliable.</Notice></div></Modal>;
}

export function FilterBar({ compact = false }) {
  const { jobs, selectedId, selectJob, filters, setFilters } = useTraffic();
  const [advanced, setAdvanced] = useState(false);
  const update = (name, value) => setFilters(old => ({ ...old, [name]: value }));
  const active = Object.entries(filters).some(([k, v]) => k === 'source' ? v !== 'all' : Boolean(v));
  return <div className="filter-wrap"><div className="filter-bar"><div className="filter-label"><SlidersHorizontal aria-hidden="true" size={15}/><span>View</span></div><select aria-label="Video scope" value={selectedId || 'all-job'} onChange={e => selectJob(e.target.value)} className="video-scope"><option value="all-job">All uploaded videos</option>{jobs.map(job => <option key={job.id} value={job.id}>{job.filename} · {shortId(job.id)}</option>)}</select><span className="filter-divider"/><select aria-label="Vehicle class filter" value={filters.vehicle_class} onChange={e => update('vehicle_class', e.target.value)}><option value="">All vehicles</option>{['Bike', 'Car', 'Jeep', 'Van'].map(c => <option key={c}>{c}</option>)}</select><select aria-label="Violation type filter" value={filters.violation_type} onChange={e => update('violation_type', e.target.value)}><option value="">All violations</option><option>No-Helmet</option><option>No-Seatbelt</option></select>{!compact && <select aria-label="Data source filter" value={filters.source} onChange={e => update('source', e.target.value)}><option value="all">All sources</option><option value="real">Real inference only</option><option value="demo">Scripted demo only</option></select>}<button className={`btn small subtle ${advanced ? 'selected' : ''}`} onClick={() => setAdvanced(!advanced)} aria-expanded={advanced}><Filter aria-hidden="true" size={14}/>Filters{active && <span className="active-dot"/>}</button></div>{advanced && <div className="advanced-filters"><label>From (local time)<input aria-label="From date" type="datetime-local" value={localDatetime(filters.date_from)} onChange={e => update('date_from', e.target.value ? new Date(e.target.value).toISOString() : '')}/></label><label>To (local time)<input aria-label="To date" type="datetime-local" value={localDatetime(filters.date_to)} onChange={e => update('date_to', e.target.value ? new Date(e.target.value).toISOString() : '')}/></label><label>Minimum confidence<input aria-label="Minimum confidence filter" type="number" min="0" max="100" value={Math.round(filters.min_confidence * 100)} onChange={e => update('min_confidence', Math.min(1, Math.max(0, Number(e.target.value) / 100)))}/></label>{compact && <label>Source<select value={filters.source} onChange={e => update('source', e.target.value)}><option value="all">All sources</option><option value="real">AI inference</option><option value="demo">Demo</option></select></label>}<button className="text-btn" onClick={() => { setFilters({ vehicle_class: '', violation_type: '', source: 'all', min_confidence: 0, date_from: '', date_to: '' }); setAdvanced(false); }}>Reset filters</button></div>}</div>;
}

export function JobControls({ compact = false }) {
  const { selectedJob: job, act, busy, toast, refresh } = useTraffic();
  const [mode, setMode] = useState('real');
  const [full, setFull] = useState(false);
  const [recorded, setRecorded] = useState('');
  useEffect(() => { setMode(job?.options?.mode || (job?.is_demo_source ? 'demo' : 'real')); setFull(job?.options?.max_seconds === null); setRecorded(localDatetime(job?.options?.recorded_at)); }, [job?.id]);
  if (!job) return null;
  const active = ['running', 'paused', 'queued'].includes(job.status);
  const run = async (action) => {
    const value = await act(action, () => api(`/jobs/${job.id}/${action}`, { method: 'POST', ...(['start', 'retry'].includes(action) ? { body: JSON.stringify({ mode, max_seconds: full ? null : 60, ...(recorded ? { recorded_at: new Date(recorded).toISOString() } : {}) }) } : {}) }));
    if (value) { toast(action === 'cancel' ? 'Cancellation requested; partial results are retained.' : `Processing ${action} requested.`); refresh(); }
  };
  return <div className={`job-controls ${compact ? 'compact' : ''}`}>{!active && !compact && <div className="processing-options"><label>Analysis mode<select aria-label="Analysis mode" value={mode} onChange={e => setMode(e.target.value)}>{job.is_demo_source && <option value="demo">Scripted demo · not AI</option>}<option value="real">Custom YOLO26 inference</option></select></label><label>Video span<select aria-label="Video span" value={full ? 'full' : '60'} onChange={e => setFull(e.target.value === 'full')}><option value="60">First 60 seconds (default)</option><option value="full">Full video ({duration(job.duration)})</option></select></label><label>Recording start (optional)<input aria-label="Recording start time" type="datetime-local" value={recorded} onChange={e => setRecorded(e.target.value)}/></label></div>}<div className="control-buttons">{job.status === 'uploaded' && <button className="btn primary" disabled={!!busy} onClick={() => run('start')}><Play aria-hidden="true" size={15}/>{busy === 'start' ? 'Starting…' : 'Start processing'}</button>}{['completed', 'cancelled', 'failed', 'interrupted'].includes(job.status) && <button className="btn" disabled={!!busy} onClick={() => run('retry')}><RefreshCw aria-hidden="true" size={15}/>{busy === 'retry' ? 'Retrying…' : 'Reprocess video'}</button>}{job.status === 'running' && <button className="btn" disabled={!!busy} onClick={() => run('pause')}><Pause aria-hidden="true" size={15}/>Pause</button>}{job.status === 'paused' && <button className="btn primary" disabled={!!busy} onClick={() => run('resume')}><Play aria-hidden="true" size={15}/>Resume</button>}{active && <button className="btn danger" disabled={!!busy} onClick={() => run('cancel')}><Square aria-hidden="true" size={13}/>Cancel</button>}<Status value={job.status}/><span className="control-caption">{active ? 'Controls apply after the current frame.' : mode === 'demo' ? 'Scripted data — no model inference.' : 'Requires trusted custom-trained weights.'}</span></div>{job.error && <ErrorBox>{job.error}</ErrorBox>}</div>;
}

export function SourceScopeNotice() {
  const { stats } = useTraffic();
  if (!stats?.source_modes?.includes('demo')) return null;
  return <div className="source-notice"><span><span className="amber-dot"/><b>{stats.source_modes.includes('real') ? 'Mixed source scope' : 'Scripted demo scope'}</b> · These aggregates include synthetic scripted data, not just AI predictions.</span><Tag tone="amber">INCLUDES DEMO</Tag></div>;
}

export function ProgressPanel({ job }) {
  if (!job || job.status === 'uploaded') return null;
  return <div className="progress-panel"><div className="row-between"><div className="progress-caption"><span className={job.status === 'running' ? 'pulse-dot' : 'quiet-dot'}/><strong>{job.status === 'running' ? 'Processing video' : job.status === 'completed' ? 'Processing complete' : `Processing ${job.status}`}</strong><SourceTag mode={job.mode}/></div><strong className="mono">{percent(job.progress * 100)}</strong></div><div className="progress-track" role="progressbar" aria-label="Processing progress" aria-valuenow={Math.round(job.progress * 100)} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${job.progress * 100}%` }}/></div><div className="progress-metrics"><span><ScanLine aria-hidden="true" size={13}/><b>{number(job.processed_frames)}</b> sampled frames</span><span><Clock3 aria-hidden="true" size={13}/>{duration(job.elapsed)} active time</span><span><Activity aria-hidden="true" size={13}/><b>{job.processing_fps}</b> pipeline FPS</span><span>Video {duration(job.video_time)} / {duration(Math.min(job.duration, job.options?.max_seconds || job.duration))}</span></div></div>;
}

export function EventList({ items, small = false }) {
  const { jobs } = useTraffic();
  if (!items.length) return <Empty small title="Activity will appear here" text="Uploads, processing changes and confirmed events are recorded automatically." icon={Activity}/>;
  return <div className={`event-list ${small ? 'small' : ''}`}>{items.map(event => <div className={`event-item ${event.level}`} key={event.id}><span className="event-icon">{event.kind === 'violation' ? <ShieldAlert aria-hidden="true" size={15}/> : event.kind === 'crossing' ? <ArrowUpRight aria-hidden="true" size={15}/> : event.kind === 'uploaded' ? <FileVideo aria-hidden="true" size={15}/> : <Activity aria-hidden="true" size={15}/>}</span><div><p>{event.message}</p><small><span>{event.kind.replaceAll('_', ' ')}</span>{event.job_id && <span className="mono">{shortId(event.job_id)}</span>}{(event.payload?.mode || jobs.find(j => j.id === event.job_id)?.mode) === 'demo' && <span className="event-demo">DEMO · NOT AI</span>}</small></div><time title={event.created_at}>{time(event.created_at)}</time></div>)}</div>;
}
