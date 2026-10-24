import React, { useEffect, useRef, useState } from 'react';
import { ArrowRight, CheckCircle2, ChevronRight, Clapperboard, CloudUpload, FileVideo, FolderOpen, HardDrive, Loader2, Play, Plus, ShieldCheck, Sparkles, Trash2, Upload, X } from 'lucide-react';
import { api } from '../api';
import { useTraffic } from '../store';
import { bytes, duration, getError, shortId, validateVideo } from '../utils';
import { VideoPanel } from '../components/VideoPanel';
import { Empty, ErrorBox, JobControls, Notice, PageHeader, ProgressPanel, SectionTitle, SourceTag, Status, Tag } from '../components/ui';

export function Workspace() {
  const { jobs, selectedJob: job, selectJob, navigate, system, act, busy, toast, refresh } = useTraffic();
  const input = useRef(null);
  const request = useRef(null);
  const [file, setFile] = useState(null);
  const [localUrl, setLocalUrl] = useState('');
  const [error, setError] = useState('');
  const [drag, setDrag] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  useEffect(() => {
    if (!file) { setLocalUrl(''); return; }
    const url = URL.createObjectURL(file); setLocalUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  useEffect(() => () => { if (request.current) { request.current.onload = null; request.current.onerror = null; request.current.onabort = null; request.current.abort(); } }, []);
  const choose = selected => {
    if (uploading) return;
    const message = validateVideo(selected, system?.max_upload_mb || 500);
    if (message) { setError(message); return; }
    setError(''); setFile(selected); setUploadProgress(0);
  };
  const upload = () => {
    if (!file || uploading) return;
    setError(''); setUploading(true);
    const xhr = new XMLHttpRequest(); request.current = xhr;
    xhr.open('POST', '/api/uploads'); xhr.withCredentials = true;
    xhr.upload.onprogress = event => { if (event.lengthComputable) setUploadProgress(Math.round(100 * event.loaded / event.total)); };
    xhr.onerror = () => { setError('Upload failed. Check the API connection and retry.'); setUploading(false); };
    xhr.onabort = () => { setError('Upload cancelled. No processing job was started.'); setUploading(false); setUploadProgress(0); };
    xhr.onload = () => {
      setUploading(false); request.current = null;
      let data;
      try { data = JSON.parse(xhr.responseText); } catch { setError('The backend returned an invalid upload response.'); return; }
      if (xhr.status !== 201) { setError(getError(data.detail)); return; }
      selectJob(data.id); setFile(null); refresh(); toast('Video uploaded and validated. Choose the analysis mode below.');
    };
    const form = new FormData(); form.append('file', file); xhr.send(form);
  };
  const sample = async () => {
    const data = await act('sample', () => api('/samples/demo', { method: 'POST' }));
    if (data) { selectJob(data.id); setFile(null); toast('Synthetic sample imported. Its detections are scripted, not AI.'); }
  };
  const remove = async video => {
    if (!window.confirm(`Delete ${video.filename} and all its results and evidence? This cannot be undone.`)) return;
    const result = await act(`delete-${video.id}`, () => api(`/jobs/${video.id}`, { method: 'DELETE' }));
    if (result) toast('Video, records and evidence removed.');
  };
  return <><PageHeader eyebrow="INPUT SOURCES / VIDEO WORKSPACE" title="Every insight starts with a video" description="Upload footage, choose a processing mode, and follow each frame through the pipeline." actions={<Tag tone="green" dot>LOCAL STORAGE</Tag>}/><div className="workspace-import"><section className="panel upload-panel"><SectionTitle title="Import traffic footage" subtitle={`MP4, AVI or MOV · up to ${system?.max_upload_mb || 500} MB`}/><div role="button" tabIndex={0} aria-label="Choose a traffic video" className={`upload-zone ${drag ? 'dragging' : ''}`} onClick={e => { if (!uploading && e.target !== input.current) input.current?.click(); }} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.current?.click(); } }} onDragOver={e => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={e => { e.preventDefault(); setDrag(false); if (e.dataTransfer.files.length > 1) { setError('Please upload one video at a time.'); return; } choose(e.dataTransfer.files[0]); }}><input ref={input} className="sr-only" type="file" aria-label="Video file" accept=".mp4,.avi,.mov" disabled={uploading} onChange={e => { if (e.target.files[0]) choose(e.target.files[0]); e.target.value = ''; }}/><span className="upload-icon">{file ? <FileVideo aria-hidden="true" size={29}/> : <CloudUpload aria-hidden="true" size={31}/>}</span><h3>{file ? file.name : 'Drop your traffic video here'}</h3><p>{file ? `${bytes(file.size)} · Ready for validation` : <>or <span>browse files</span> on your computer</>}</p><div className="upload-formats"><Tag>MP4</Tag><Tag>AVI</Tag><Tag>MOV</Tag></div></div>{file && <div className="upload-selection"><span><FileVideo aria-hidden="true" size={17}/>{file.name}</span><button className="icon-btn" aria-label="Remove selected file" disabled={uploading} onClick={() => setFile(null)}><X aria-hidden="true" size={17}/></button></div>}{uploading && <div className="upload-progress"><div className="row-between"><span>{uploadProgress === 100 ? 'Validating video and creating job…' : 'Uploading video…'}</span><strong>{uploadProgress}%</strong></div><div className="progress-track"><i style={{ width: `${uploadProgress}%` }}/></div><button className="text-btn" onClick={() => request.current?.abort()}>Cancel upload</button></div>}{error && <ErrorBox>{error}</ErrorBox>}<div className="upload-bottom"><span><ShieldCheck aria-hidden="true" size={14}/>Files stay on your machine</span><button className="btn primary" onClick={upload} disabled={!file || uploading || !!busy}>{uploading ? <Loader2 aria-hidden="true" size={15} className="spin"/> : <Upload aria-hidden="true" size={15}/>}Upload video</button></div></section><div className="workspace-aside"><section className="panel sample-card"><div className="sample-top"><span className="sample-icon"><Clapperboard aria-hidden="true" size={24}/></span><Tag tone="amber">NOT AI FOOTAGE</Tag></div><h2>Take the system for a spin.</h2><p>An original 60-second synthetic road scene, with a known, scripted object scenario. Explore every step without model weights.</p><div className="sample-specs"><span>01:00 duration</span><i/><span>960 × 540</span><i/><span>CC0</span></div><button className="btn" onClick={sample} disabled={!!busy || uploading || system?.sample_available === false}>{busy === 'sample' ? <Loader2 aria-hidden="true" size={15} className="spin"/> : <Play aria-hidden="true" size={15}/>}Import synthetic sample <ArrowRight aria-hidden="true" size={15}/></button>{system?.sample_available === false && <small className="text-amber">Run python scripts/prepare_sample.py to create the sample.</small>}</section><section className="panel model-setup-card"><ScanIcon/><div><h3>Bring your own intelligence</h3><p>Real safety detection requires a custom-trained YOLO26 model with all eight classes.</p><button className="text-btn" onClick={() => navigate('settings')}>Configure model <ArrowRight aria-hidden="true" size={13}/></button></div></section></div></div>
  {localUrl && <div className="local-preview"><VideoPanel localUrl={localUrl} localName={file?.name}/></div>}
  {job && !localUrl && <section className="panel selected-source"><SectionTitle title="Selected source" subtitle={`${job.filename} · ${duration(job.duration)} · ${job.width} × ${job.height} · ${job.fps.toFixed(1)} FPS`} action={<button className="btn small" onClick={() => navigate('monitor')}>Open monitor <ArrowUpRightIcon/></button>}/><JobControls/><ProgressPanel job={job}/>{job.is_demo_source && <Notice tone="amber">This file matches the synthetic sample checksum. Demo mode uses its scripted object positions and scores. Real mode still requires custom weights.</Notice>}{job.config?.frame_stride > 1 && <Notice>Frame skipping is enabled ({job.config.frame_stride}). Short events may be missed and tracking/voting reliability may decrease.</Notice>}</section>}
  <section className="panel source-library"><SectionTitle title="Video library" subtitle={`${jobs.length} videos loaded · results persist across application restarts`} action={<span className="storage-note"><HardDrive aria-hidden="true" size={13}/>{bytes(system?.storage_bytes || 0)} used</span>}/>{jobs.length ? <div className="table-wrap"><table><thead><tr><th>Video source</th><th>Duration / size</th><th>Analysis</th><th>Status</th><th>Preview</th><th>Actions</th></tr></thead><tbody>{jobs.map(video => <tr key={video.id} className={job?.id === video.id ? 'selected-row' : ''}><td><button className="source-file" onClick={() => selectJob(video.id)}><span className="file-icon"><FileVideo aria-hidden="true" size={18}/></span><span><strong>{video.filename}</strong><small className="mono">{shortId(video.id)}</small></span>{job?.id === video.id && <CheckCircle2 aria-hidden="true" size={15} className="text-teal"/>}</button></td><td><span>{duration(video.duration)}</span><small className="block muted">{bytes(video.size_bytes)}</small></td><td><SourceTag mode={video.mode}/></td><td><Status value={video.status}/></td><td><Status value={video.preview_status}/></td><td><div className="table-actions"><button className="icon-btn" title="Select and monitor video" aria-label={`Monitor ${shortId(video.id)}`} onClick={() => { selectJob(video.id); navigate('monitor'); }}><Play aria-hidden="true" size={15}/></button><button className="icon-btn danger-text" title="Delete video and results" aria-label={`Delete ${shortId(video.id)}`} disabled={!!busy || ['running', 'queued', 'paused'].includes(video.status) || video.preview_status === 'preparing'} onClick={() => remove(video)}><Trash2 aria-hidden="true" size={15}/></button></div></td></tr>)}</tbody></table></div> : <Empty icon={FolderOpen} title="A fresh workspace" text="Upload a video or import the synthetic sample to begin. No results have been seeded."/>}</section><div className="workflow-strip">{[['1', 'Import', 'Validate the file and preview it'], ['2', 'Analyze', 'Infer, track and associate evidence'], ['3', 'Review', 'Inspect confirmed records and snapshots'], ['4', 'Export', 'Download traceable CSV reports']].map(([n, t, d]) => <div key={n}><span>{n}</span><div><strong>{t}</strong><small>{d}</small></div></div>)}</div></>;
}
function ScanIcon() { return <span className="setup-icon"><Sparkles aria-hidden="true" size={20}/></span>; }
function ArrowUpRightIcon() { return <ArrowRight aria-hidden="true" size={14}/>; }
