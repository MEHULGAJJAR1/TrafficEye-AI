import { getError } from './utils';

export async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      credentials: 'same-origin',
      ...options,
      headers: { ...(options.body && typeof options.body === 'string' ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
    });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('Cannot reach the backend. Start the API on port 8000 and check the Vite proxy.');
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const error = new Error(getError(data.detail) || `API error ${response.status}`);
    error.status = response.status;
    if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('session-expired'));
    throw error;
  }
  return response.status === 204 ? null : response.json();
}
export async function downloadReport(query, name) {
  const response = await fetch(`/api/reports.csv?${query}`, { credentials: 'same-origin' });
  if (!response.ok) throw new Error(getError((await response.json().catch(() => ({}))).detail));
  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = href;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}
