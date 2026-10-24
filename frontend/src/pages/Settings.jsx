import React, { useEffect, useState } from 'react';
import { Check, CircleHelp, Cpu, Crosshair, HardDrive, Info, KeyRound, Layers, LockKeyhole, RefreshCw, Save, ScanLine, Settings2, ShieldCheck, SlidersHorizontal, TriangleAlert, X } from 'lucide-react';
import { api } from '../api';
import { useTraffic } from '../store';
import { bytes } from '../utils';
import { ErrorBox, Notice, PageHeader, SectionTitle, Spinner, Status, Tag } from '../components/ui';

const CLASSES = ['Bike', 'Car', 'Jeep', 'Van', 'Helmet', 'No-Helmet', 'Seatbelt', 'No-Seatbelt'];
const decisionFields = [
  ['confidence', 'Detection confidence', 0.05, 0.95, 0.01, 'Minimum displayed box and tracked-vehicle confidence.'],
  ['violation_confidence', 'Safety evidence confidence', 0.1, 0.99, 0.01, 'Minimum Helmet/Seatbelt box score considered for a decision.'],
  ['vote_window', 'Voting window (frames)', 3, 60, 1, 'Last N processed observations for each vehicle identity.'],
  ['min_votes', 'Minimum supporting votes', 2, 60, 1, 'Must not exceed the voting window.'],
  ['vote_ratio', 'Required vote ratio', 0.5, 1, 0.01, 'Supporting votes divided by all observations in the window.'],
  ['min_evidence_seconds', 'Minimum evidence span (s)', 0.1, 10, 0.05, 'Evidence maturity across qualifying vote windows; resets when count/ratio fails.'],
  ['association_overlap', 'Object-overlap threshold', 0.1, 1, 0.01, 'Safety-box intersection / safety-box area within a vehicle region.'],
  ['ambiguity_margin', 'Ambiguity margin', 0.01, 0.5, 0.01, 'Reject near-tied vehicle associations and conflicting safety labels.'],
  ['bike_top_margin', 'Motorcycle head-region expansion', 0, 1.5, 0.05, 'Expand above the motorcycle box by this fraction of its height.'],
  ['min_vehicle_pixels', 'Minimum vehicle side (px)', 8, 256, 1, 'Do not make safety decisions for very small vehicle boxes.'],
  ['duplicate_iou', 'Fragment duplicate IoU', 0.5, 0.99, 0.01, 'Suppress near-identical overlapping new-ID violation alerts.'],
  ['duplicate_seconds', 'Fragment suppression span (s)', 0, 30, 0.5, 'Short video-time interval for spatial duplicate suppression.'],
];
const trackerFields = [
  ['track_high_thresh', 'High-score match threshold', 0.05, 0.95, 0.01],
  ['track_low_thresh', 'Low-score recovery threshold', 0.01, 0.9, 0.01],
  ['new_track_thresh', 'New-track threshold', 0.05, 0.99, 0.01],
  ['track_buffer', 'Lost-track buffer (processed frames)', 1, 300, 1],
  ['match_thresh', 'Association cost threshold', 0.1, 0.99, 0.01],
];

export function Settings() {
  const { config, system, act, busy, refresh, toast } = useTraffic();
  const [form, setForm] = useState(null);
  const [zones, setZones] = useState('');
  const [line, setLine] = useState('');
  const [validation, setValidation] = useState(null);
  useEffect(() => {
    if (config && !form) { setForm(structuredClone(config)); setZones(JSON.stringify(config.zones, null, 2)); setLine(JSON.stringify(config.count_line)); }
  }, [config, form]);
  if (!form) return <div className="loading-panel"><Spinner label="Loading workspace configuration…"/></div>;
  const update = (name, value) => setForm(old => ({ ...old, [name]: value }));
  const save = async event => {
    event?.preventDefault();
    const value = await act('save-config', async () => {
      let parsedZones, parsedLine;
      try { parsedZones = JSON.parse(zones); parsedLine = JSON.parse(line); } catch { throw new Error('Zones and counting line must contain valid JSON.'); }
      return api('/config', { method: 'PUT', body: JSON.stringify({ ...form, zones: parsedZones, count_line: parsedLine }) });
    });
    if (value) { setForm(value); setValidation(null); toast('Configuration saved. Existing jobs keep their original settings.'); refresh(); }
  };
  const validate = async () => {
    const result = await act('validate-model', () => api('/model/validate', { method: 'POST' }));
    if (result) { setValidation(result); toast(result.message, result.ready ? 'success' : 'info'); refresh(); }
  };
  const model = validation || system?.model || {};
  const present = new Set(Object.values(model.mapping || {}));
  const numeric = ([key, title, min, max, step, hint]) => <label key={key} className="setting-field"><span>{title}</span><input type="number" aria-label={title} min={min} max={max} step={step} value={form[key]} onChange={e => update(key, Number(e.target.value))} required/>{hint && <small>{hint}</small>}</label>;
  return <><PageHeader eyebrow="CONFIGURE / CALIBRATE / VERIFY" title="A system tuned to your road" description="Validated, persistent settings. Every new job stores an immutable configuration snapshot." actions={<button className="btn primary" onClick={save} disabled={!!busy}><Save aria-hidden="true" size={15}/>{busy === 'save-config' ? 'Saving…' : 'Save configuration'}</button>}/><div className="settings-layout"><nav className="settings-nav" aria-label="Settings sections">{[['model', Cpu, 'Model & inference'], ['decisions', ShieldCheck, 'Evidence decisions'], ['tracking', Layers, 'Tracking'], ['zones', Crosshair, 'Zones & counting'], ['security', LockKeyhole, 'Storage & security']].map(([id, Icon, title]) => <button key={id} onClick={() => document.getElementById(`settings-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}><Icon aria-hidden="true" size={16}/>{title}</button>)}<div className="settings-note"><Info aria-hidden="true" size={16}/><p>Safety decisions depend on your training data, viewpoint and calibration. Defaults are starting points, not certified thresholds.</p></div></nav><form className="settings-sections" onSubmit={save}>
  <section className="panel settings-panel" id="settings-model"><SectionTitle title="Model & inference" subtitle="Trusted, locally stored Ultralytics YOLO26 detection weights" action={<Status value={model.state}/>}/><div className="settings-inner"><div className="two-column"><label className="setting-field"><span>Custom model filename</span><input aria-label="Custom model filename" value={form.model_file} onChange={e => update('model_file', e.target.value)} pattern="[A-Za-z0-9][A-Za-z0-9_.\-]*\.pt" required/><small>Relative to models/. No uploads, URLs or path separators are accepted.</small></label><label className="setting-field"><span>Compute device</span><select value={form.device} onChange={e => update('device', e.target.value)} aria-label="Compute device"><option value="auto">Auto · CUDA when available</option><option value="cpu">CPU</option><option value="cuda:0">CUDA GPU 0</option><option value="mps">Apple MPS</option>{!['auto', 'cpu', 'cuda:0', 'mps'].includes(form.device) && <option>{form.device}</option>}</select><small>Unavailable GPU/MPS devices fall back to CPU.</small></label>{numeric(['imgsz', 'Inference image size', 320, 1536, 32, 'Square letterbox size; must be a multiple of 32.'])}{numeric(['frame_stride', 'Frame stride', 1, 10, 1, '1 analyzes every frame. Skipping may miss short events and destabilize identities.'])}{numeric(['iou', 'Detector IoU parameter', 0.1, 0.95, 0.01, 'Used by compatible prediction modes; end-to-end heads may not need NMS.'])}</div><div className="model-class-box"><div className="row-between"><h3>Required class schema</h3><Tag>{present.size} / 8 MAPPED</Tag></div><div className="class-chips">{CLASSES.map(name => <span className={present.has(name) ? 'present' : ''} key={name}>{present.has(name) ? <Check aria-hidden="true" size={13}/> : <span className="class-placeholder"/>}{name}</span>)}</div><p>{model.message || 'Validate the local model to inspect its class names.'}</p><button type="button" className="btn" onClick={validate} disabled={!!busy}><ScanLine aria-hidden="true" size={15}/>{busy === 'validate-model' ? 'Inspecting weights…' : 'Validate saved model'}</button><small className="block muted">Save filename/device changes first. Schema validation is not an accuracy evaluation.</small></div><Notice tone="amber">Generic COCO weights do not contain helmet, no-helmet, seatbelt, no-seatbelt, Jeep and Van labels. They cannot unlock this violation pipeline. Load only trusted .pt files: PyTorch checkpoints can execute code.</Notice></div></section>
  <section className="panel settings-panel" id="settings-decisions"><SectionTitle title="Evidence decisions" subtitle="Spatial matching, temporal voting and duplicate suppression"/><div className="settings-inner"><div className="two-column">{decisionFields.map(numeric)}</div><Notice tone="neutral">Unknown or conflicting evidence does not become a violation. Confidence is a model score, not a calibrated probability of guilt. Overlapping riders/passengers cannot always be associated correctly.</Notice></div></section>
  <section className="panel settings-panel" id="settings-tracking"><SectionTitle title="Vehicle tracking" subtitle="BoT-SORT · separate tracker per real-inference job" action={<Tag>ReID OFF</Tag>}/><div className="settings-inner"><div className="two-column">{trackerFields.map(numeric)}<label className="setting-field"><span>Camera motion compensation</span><select value={form.gmc_method} onChange={e => update('gmc_method', e.target.value)}><option value="sparseOptFlow">Sparse optical flow</option><option value="none">None · fixed-camera option</option></select><small>Lost-track recovery is supported; appearance ReID is not enabled in this release.</small></label></div><Notice tone="neutral">Scripted demo jobs use a transparent IoU/velocity fixture tracker, not BoT-SORT. Real jobs use Ultralytics BoT-SORT with the values above. IDs are scoped to one job.</Notice></div></section>
  <section className="panel settings-panel" id="settings-zones"><SectionTitle title="Zones & directional counts" subtitle="Normalized coordinates from the top-left; x and y must stay within [0, 1]"/><div className="settings-inner"><label className="setting-field"><span>Analysis zones (JSON)</span><textarea aria-label="Analysis zones JSON" rows={12} className="mono code-input" value={zones} onChange={e => setZones(e.target.value)} spellCheck={false}/><small>Named non-self-intersecting polygons. First matching zone wins. Outside tracks are retained, but safety decisions and crossings are ignored.</small></label><div className="two-column"><label className="setting-field"><span>Finite counting line (JSON)</span><textarea aria-label="Counting line JSON" className="mono code-input" rows={2} value={line} onChange={e => setLine(e.target.value)} spellCheck={false}/></label><label className="setting-field"><span>Negative → positive side means</span><select value={form.positive_direction} onChange={e => update('positive_direction', e.target.value)}><option>IN</option><option>OUT</option></select><small>For a left-to-right horizontal line, positive is below the line.</small></label>{numeric(['line_hysteresis', 'Line hysteresis', 0.001, 0.1, 0.001, 'Normalized distance deadband to reduce jitter counts.'])}</div><Notice tone="neutral">Default: the full frame is in scope, with a horizontal counting line at 55% of the frame height. Each tracker ID counts at most once per direction per job.</Notice></div></section>
  <section className="panel settings-panel" id="settings-security"><SectionTitle title="Storage & access" subtitle="SQLite + local files · no Docker or PostgreSQL required"/><div className="settings-inner"><div className="security-grid"><div><HardDrive aria-hidden="true" size={20}/><strong>{bytes(system?.storage_bytes || 0)}</strong><small>Workspace storage used</small></div><div><LockKeyhole aria-hidden="true" size={20}/><strong>Authenticated</strong><small>Uploads, results, evidence and CSV</small></div><div><KeyRound aria-hidden="true" size={20}/><strong>12 hours</strong><small>HttpOnly signed session lifetime</small></div></div><Notice tone="neutral">The generated access key is in <code>data/access.key</code>. Never commit or share it. On Windows, restrict the data folder to your account. Set TE_SECURE_COOKIE=true behind HTTPS. This is a single-operator application; multi-tenant roles and internet deployment are outside this release.</Notice><p className="small-text muted">Delete old jobs in Video workspace to remove their uploads, previews, records and evidence. Back up data/ with the backend stopped for a consistent snapshot.</p></div></section>
  <div className="settings-save"><span>New and retried jobs use the saved settings.</span><div><button type="button" className="btn" disabled={!!busy} onClick={() => { setForm(structuredClone(config)); setZones(JSON.stringify(config.zones, null, 2)); setLine(JSON.stringify(config.count_line)); toast('Unsaved changes discarded.', 'info'); }}>Discard changes</button><button className="btn primary" type="submit" disabled={!!busy}><Save aria-hidden="true" size={15}/>Save configuration</button></div></div></form></div></>;
}
