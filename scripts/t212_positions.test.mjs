import test from 'node:test';
import assert from 'node:assert/strict';
import { fetchPositions } from './t212_positions.mjs';

const positions = [{ instrument: { ticker: 'BMWd_EQ' }, currentPrice: 58 }];
const ok = () => new Response(JSON.stringify(positions));
const limited = (headers = {}) => new Response('TooManyRequests', { status: 429, headers });

function client(responses, options = {}) {
  let calls = 0;
  let time = 1_800_000_000_000;
  const waits = [], logs = [];
  const run = () => fetchPositions({
    baseUrl: 'https://live.trading212.com/api/v0',
    apiKey: 'test-key', apiSecret: 'test-secret',
    fetchImpl: async (url, request) => {
      assert.equal(url, 'https://live.trading212.com/api/v0/equity/positions');
      assert.equal(request.headers.Authorization, 'Basic ' + Buffer.from('test-key:test-secret').toString('base64'));
      assert(request.signal instanceof AbortSignal);
      const response = responses[calls++];
      assert(response, 'made an unexpected extra request');
      return response;
    },
    sleep: async (ms) => { waits.push(ms); time += ms; },
    now: () => time, random: () => 0, log: (line) => logs.push(line),
    ...options,
  });
  return { run, waits, logs, calls: () => calls };
}

test('successful first response needs no retry', async () => {
  const c = client([ok()]);
  assert.deepEqual(await c.run(), positions);
  assert.equal(c.calls(), 1);
  assert.deepEqual(c.waits, []);
});

test('429 then success respects Retry-After seconds', async () => {
  const c = client([limited({ 'Retry-After': '3', 'x-ratelimit-remaining': '0' }), ok()]);
  assert.deepEqual(await c.run(), positions);
  assert.deepEqual(c.waits, [3000]);
  assert.match(c.logs[0], /HTTP 429.*remaining=0.*retry 2\/5/);
  assert(!c.logs[0].includes('test-key') && !c.logs[0].includes('test-secret'));
});

test('HTTP-date Retry-After and account reset both constrain the wait', async () => {
  const c = client([limited({ 'Retry-After': new Date(1_800_000_004_000).toUTCString(), 'x-ratelimit-reset': '1800000006' }), ok()]);
  assert.deepEqual(await c.run(), positions);
  assert.deepEqual(c.waits, [6000]);
});

test('reset header works without Retry-After', async () => {
  const c = client([limited({ 'x-ratelimit-reset': '1800000002' }), ok()]);
  await c.run();
  assert.deepEqual(c.waits, [2000]);
});

test('missing or invalid headers trigger increasing backoff with jitter', async () => {
  const c = client([limited(), limited({ 'retry-after': 'invalid', 'x-ratelimit-reset': 'invalid' }), ok()], { random: () => 0.5 });
  await c.run();
  assert.deepEqual(c.waits, [2125, 4125]);
});

test('zero Retry-After cannot cause an immediate burst', async () => {
  const c = client([limited({ 'retry-after': '0' }), ok()]);
  await c.run();
  assert.deepEqual(c.waits, [1000]);
});

test('persistent limiting stops after five attempts', async () => {
  const c = client(Array.from({ length: 5 }, () => limited()));
  await assert.rejects(c.run(), /HTTP 429/);
  assert.equal(c.calls(), 5);
  assert.deepEqual(c.waits, [2000, 4000, 8000, 16000]);
});

test('a long server cooldown is not shortened into an early retry', async () => {
  const c = client([limited({ 'retry-after': '120' })]);
  await assert.rejects(c.run(), /retry budget/);
  assert.equal(c.calls(), 1);
  assert.deepEqual(c.waits, []);
});

test('non-rate-limit errors are surfaced without repeated requests', async () => {
  for (const status of [401, 403, 500]) {
    const c = client([new Response('upstream error', { status })]);
    await assert.rejects(c.run(), new RegExp(`HTTP ${status}`));
    assert.equal(c.calls(), 1);
    assert.deepEqual(c.waits, []);
  }
});
