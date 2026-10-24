import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const key = process.env.TE_E2E_KEY || fs.readFileSync(process.env.TE_E2E_KEY_FILE || path.join(ROOT, 'data/access.key'), 'utf8').trim();
const samplePath = path.join(ROOT, 'samples/traffic_demo_60s.mp4');
const ownJobs = [];

async function unlock(page) {
  await page.goto('/');
  await page.getByLabel('Workspace access key').fill(key);
  await page.getByRole('button', { name: 'Unlock workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Operations overview' })).toBeVisible();
}
async function go(page, label) { await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: label, exact: true }).click(); }
async function jobState(page, id) { return (await page.request.get(`/api/jobs/${id}`)).json(); }
async function dismissToasts(page) {
  while (await page.getByRole('button', { name: 'Dismiss notification', exact: true }).count()) {
    await page.getByRole('button', { name: 'Dismiss notification', exact: true }).first().click();
  }
}

test('complete upload → scripted analysis → tracking → decision → snapshot → CSV', async ({ page }) => {
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await unlock(page);
  await go(page, 'Video workspace');
  await page.getByLabel('Video file', { exact: true }).setInputFiles(samplePath);
  await expect(page.getByLabel('Selected video preview')).toBeVisible();
  const response = page.waitForResponse(r => r.url().endsWith('/api/uploads') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Upload video', exact: true }).click();
  const uploaded = await response;
  expect(uploaded.status()).toBe(201);
  const job = await uploaded.json(); ownJobs.push(job.id);
  await expect(page.getByRole('heading', { name: 'Selected source' })).toBeVisible();
  await expect(page.getByLabel('Analysis mode')).toHaveValue('demo');
  await expect(page.getByLabel('Video span')).toHaveValue('60');
  await page.getByRole('button', { name: 'Start processing', exact: true }).click();
  await expect(page.getByRole('progressbar', { name: 'Processing progress' })).toBeVisible();
  await expect.poll(async () => (await jobState(page, job.id)).processed_frames).toBeGreaterThan(5);
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  await expect.poll(async () => (await jobState(page, job.id)).status).toBe('paused');
  await page.getByRole('button', { name: 'Resume', exact: true }).click();
  await expect.poll(async () => (await jobState(page, job.id)).status).toBe('running');
  await go(page, 'Live monitor');
  await expect(page.getByRole('heading', { name: 'Frame inspector' })).toBeVisible();
  await expect(page.getByAltText(/Annotated scripted demo frame/)).toBeVisible();
  await expect(page.getByText('WEBSOCKET CONNECTED', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect.poll(async () => (await jobState(page, job.id)).status).toBe('cancelled');
  await expect(page.getByRole('button', { name: 'Reprocess video' })).toBeVisible();
  await page.getByRole('button', { name: 'Reprocess video' }).click();
  await expect.poll(async () => (await jobState(page, job.id)).status, { timeout: 60000, intervals: [500, 1000] }).toBe('completed');
  const completed = await jobState(page, job.id);
  expect(completed.processed_frames).toBe(720);
  expect(completed.progress).toBe(1);
  expect(completed.inference_fps).toBe(0);
  expect(completed.last_result.detections).toBeTruthy();
  const stats = await (await page.request.get(`/api/analytics?job_id=${job.id}`)).json();
  expect(stats.summary.total_vehicles).toBeGreaterThan(15);
  expect(stats.summary.confirmed_violations).toBeGreaterThan(0);
  await go(page, 'Evidence vault');
  await expect(page.locator('.evidence-card').first()).toBeVisible();
  await page.locator('.evidence-image').first().click();
  const dialog = page.getByRole('dialog', { name: 'Violation evidence' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText('SCRIPTED DEMO', { exact: true })).toBeVisible();
  const image = dialog.locator('img.evidence-large');
  await expect.poll(() => image.evaluate(el => el.complete && el.naturalWidth > 0)).toBeTruthy();
  const evidenceDownload = page.waitForEvent('download');
  await dialog.getByRole('link', { name: 'Save image' }).click();
  expect((await evidenceDownload).suggestedFilename()).toMatch(/\.jpg$/);
  await dialog.getByRole('button', { name: 'Close dialog' }).click();
  const csvDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export violations', exact: true }).click();
  const report = await csvDownload;
  const csv = fs.readFileSync(await report.path(), 'utf8');
  expect(csv).toContain('source_mode'); expect(csv).toContain(',demo,'); expect(csv).toContain('evidence_filename');
  await go(page, 'Vehicle tracking');
  await expect(page.locator('table tbody tr').first()).toBeVisible();
  await page.getByLabel('Vehicle class filter').selectOption('Bike');
  await expect.poll(async () => page.locator('table tbody tr').count()).toBeGreaterThan(0);
  await expect(page.locator('table tbody')).toContainText('Bike');
  await page.getByLabel('Vehicle class filter').selectOption('');
  await go(page, 'Overview');
  await expect(page.getByRole('heading', { name: 'Operations overview' })).toBeVisible();
  await page.waitForTimeout(1000); // chart settle for the actual screenshot, not for processing completion
  await dismissToasts(page);
  await page.screenshot({ path: path.join(ROOT, 'docs/dashboard.png'), fullPage: true });
  fs.writeFileSync(path.join(ROOT, 'docs/demo-workflow-result.json'), JSON.stringify({ job_id: job.id, mode: 'scripted-demo-not-ai', processed_frames: completed.processed_frames, duration_seconds: completed.duration, active_elapsed_seconds: completed.elapsed, processing_fps: completed.processing_fps, inference_fps: completed.inference_fps, summary: stats.summary, note: 'Synthetic fixture pipeline measurements, NOT model accuracy or real-world benchmarks.' }, null, 2));
  expect(errors).toEqual([]);
});

test('all views, client errors, configuration, mobile layout and session locking', async ({ page }) => {
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await unlock(page);
  const headings = { 'Live monitor': 'Live processing monitor', 'Video workspace': 'Every insight starts with a video', 'Vehicle tracking': 'Vehicle intelligence', 'Violations': 'A closer look at every violation', 'Evidence vault': 'Evidence that tells the full story', 'Analytics': 'Traffic patterns, made clear', 'Activity log': 'Nothing happens in the dark', 'Reports': 'Traceable reports. Open formats.', 'Settings': 'A system tuned to your road' };
  for (const [nav, heading] of Object.entries(headings)) { await go(page, nav); await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible(); }
  await page.getByRole('button', { name: 'Validate saved model' }).click();
  await expect(page.getByText(/[Mm]issing.*models\//).first()).toBeVisible();
  await page.getByRole('button', { name: 'Save configuration', exact: true }).first().click();
  await expect(page.getByText('Configuration saved. Existing jobs keep their original settings.', { exact: true })).toBeVisible();
  await go(page, 'Video workspace');
  await page.getByLabel('Video file', { exact: true }).setInputFiles({ name: 'bad.txt', mimeType: 'text/plain', buffer: Buffer.from('not a video') });
  await expect(page.getByRole('alert')).toContainText('MP4, AVI or MOV');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByLabel('Open navigation', { exact: true }).click();
  await go(page, 'Overview');
  await expect(page.getByRole('heading', { name: 'Operations overview' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await dismissToasts(page);
  await page.waitForTimeout(1000); // settle responsive chart reflow before the actual capture
  await page.screenshot({ path: path.join(ROOT, 'docs/mobile.png'), fullPage: true });
  await page.getByLabel('Open navigation', { exact: true }).click();
  await go(page, 'Settings');
  await expect(page.getByRole('heading', { name: 'A system tuned to your road' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByLabel('Open navigation', { exact: true }).click();
  await page.getByLabel('Lock workspace', { exact: true }).click();
  await expect(page.getByLabel('Workspace access key')).toBeVisible();
  expect(errors).toEqual([]);
});

test('WebSocket outage falls back to genuine HTTP job updates', async ({ page }) => {
  await page.routeWebSocket('**/api/ws/**', socket => socket.close({ code: 1001, reason: 'QA transport failure' }));
  await unlock(page);
  await go(page, 'Live monitor');
  await expect(page.getByText('POLLING FALLBACK', { exact: true })).toBeVisible();
  await expect(page.getByText('Polling fallback', { exact: true })).toBeVisible();
});

test.afterAll(async ({ request }) => {
  // Remove only jobs created by this test run; never reset a user's database.
  const headers = { Authorization: `Bearer ${key}` };
  for (const id of ownJobs) {
    const base = process.env.TE_E2E_URL || 'http://127.0.0.1:5173';
    await request.post(`${base}/api/jobs/${id}/cancel`, { headers }).catch(() => {});
    await request.delete(`${base}/api/jobs/${id}`, { headers });
  }
});
