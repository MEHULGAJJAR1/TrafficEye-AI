import test from 'node:test';
import assert from 'node:assert/strict';
import { duration, bytes, params, validateVideo, getError, percent, shortId, localDatetime } from '../src/utils.js';

test('video duration is finite, nonnegative and padded', () => {
  assert.equal(duration(60), '01:00');
  assert.equal(duration(7.9), '00:07');
  assert.equal(duration(-12), '00:00');
  assert.equal(duration(undefined), '00:00');
});
test('file size labels', () => {
  assert.equal(bytes(1024), '1 KB');
  assert.equal(bytes(1024 * 1024), '1.0 MB');
});
test('query serialization never drops valid zero values', () => {
  const p = new URLSearchParams(params({ confidence: 0, source: 'demo', nothing: '', job_id: 'all-job' }));
  assert.equal(p.get('confidence'), '0');
  assert.equal(p.get('source'), 'demo');
  assert.equal(p.has('nothing'), false);
  assert.equal(p.has('job_id'), false);
});
test('query text is correctly encoded', () => {
  assert.equal(new URLSearchParams(params({ filename: '../a & b.mov' })).get('filename'), '../a & b.mov');
});
test('client rejects unsupported, empty and oversized videos', () => {
  assert.match(validateVideo({ name: 'x.txt', size: 20 }), /MP4/);
  assert.match(validateVideo({ name: 'x.mp4', size: 0 }), /empty/);
  assert.match(validateVideo({ name: 'x.mp4', size: 2 * 1024 * 1024 }, 1), /exceeds/);
});
test('MP4, AVI and MOV extension matching is case-insensitive', () => {
  for (const name of ['road.MP4', 'road.avi', 'road.MOV']) assert.equal(validateVideo({ name, size: 10 }), null);
});
test('server validation messages are readable', () => {
  assert.equal(getError([{ loc: ['body', 'imgsz'], msg: 'Invalid resolution' }]), 'imgsz: Invalid resolution');
  assert.equal(getError('Missing model'), 'Missing model');
});
test('display helpers preserve source values', () => {
  assert.equal(percent(25), '25.0%');
  assert.equal(shortId('abcdef12-3456'), 'ABCDEF12');
});

test('non-finite video durations are never rendered as infinity', () => {
  assert.equal(duration(Infinity), '00:00');
  assert.equal(duration(NaN), '00:00');
});


test('date-filter input values survive reopening the filters panel', () => {
  assert.equal(localDatetime(''), '');
  assert.equal(localDatetime('not-a-date'), '');
  assert.equal(localDatetime(new Date(2026, 9, 23, 10, 5).toISOString()), '2026-10-23T10:05');
});
