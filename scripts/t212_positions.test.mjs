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

async function requestTimes(slot, start, replies = [ok()], firstWakeLateMs = 0) {
  let time = 1_800_000_000_000 + start;
  let firstSleep = true;
  const times = [];
  await fetchPositions({
    baseUrl: 'https://live.trading212.com/api/v0', apiKey: 'test-key', apiSecret: 'test-secret',
    requestSlot: slot, now: () => time, random: () => 0, log: () => {},
    sleep: async (ms) => {
      time += ms + (firstSleep ? firstWakeLateMs : 0);
      firstSleep = false;
    },
    fetchImpl: async () => {
      times.push(time);
      const reply = replies.shift();
      assert(reply, 'unexpected extra request');
      return reply;
    },
  });
  return times;
}

test('simultaneously started sites send five seconds apart', async () => {
  const [one, two] = await Promise.all([requestTimes(0, 0), requestTimes(1, 0)]);
  assert.equal(two[0] - one[0], 5000);
});

test('independently delayed jobs always send inside their own windows', async () => {
  const one = [], two = [];
  for (const start of [0, 250, 499, 500, 1250, 4500, 5000, 5250, 5499, 5500, 9999]) {
    one.push(...await requestTimes(0, start));
    two.push(...await requestTimes(1, start));
  }
  for (const time of one) assert(time % 10000 < 500);
  for (const time of two) assert(time % 10000 >= 5000 && time % 10000 < 5500);
  for (const a of one) for (const b of two) assert(Math.abs(a - b) >= 4500);
});

test('late wakeups wait for the next window instead of colliding', async () => {
  const times = await requestTimes(0, 9500, [ok()], 600);
  assert.equal(times[0], 1_800_000_020_000);
});

test('429 retries also respect the assigned request window', async () => {
  const times = await requestTimes(1, 0, [limited({ 'retry-after': '1' }), ok()]);
  assert.deepEqual(times, [1_800_000_005_000, 1_800_000_015_000]);
});

test('invalid site slot fails before requesting positions', async () => {
  await assert.rejects(requestTimes(2, 0), /requestSlot must be 0 or 1/);
});
