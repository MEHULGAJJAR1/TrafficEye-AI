export const number = (value = 0) => Number(value || 0).toLocaleString('en-IN');
export const percent = (value = 0) => `${Number(value || 0).toFixed(1)}%`;
export const duration = (seconds = 0) => {
  const numeric = Number(seconds);
  const s = Number.isFinite(numeric) ? Math.max(0, numeric) : 0;
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
};
export const bytes = (value = 0) => value < 1024 * 1024 ? `${(value / 1024).toFixed(0)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`;
export const shortId = (id = '') => id.slice(0, 8).toUpperCase();
export const time = (value) => value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—';
export function localDatetime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '';
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
export function params(filters = {}, extra = {}) {
  const values = { ...filters, ...extra };
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== null && value !== undefined && value !== '' && value !== 'all-job') query.set(key, String(value));
  }
  return query.toString();
}
export function validateVideo(file, maxMB = 500) {
  if (!file) return 'Choose a video first.';
  if (!/\.(mp4|avi|mov)$/i.test(file.name)) return 'Please select an MP4, AVI or MOV video.';
  if (file.size === 0) return 'This file is empty.';
  if (file.size > maxMB * 1024 * 1024) return `This video exceeds the ${maxMB} MB limit.`;
  return null;
}
export function getError(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(x => `${(x.loc || []).slice(1).join('.')}: ${x.msg}`).join('; ');
  return 'The request could not be completed.';
}
