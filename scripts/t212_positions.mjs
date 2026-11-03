// Trading 212 rate limits are shared by the whole account, including other sites.
// https://docs.trading212.com/api/section/rate-limiting/response-headers
const MAX_ATTEMPTS = 5;
const MAX_TOTAL_WAIT_MS = 90_000;
const MIN_WAIT_MS = 1_000;
const SLOT_CYCLE_MS = 10_000;
const SLOT_WIDTH_MS = 500;

// Site 1 sends in [0, 0.5) s and site 2 in [5, 5.5) s of each UTC cycle.
// The windows are at least 4.5 s apart even when jobs start at different times.
async function waitForRequestSlot(slot, { sleep, now, log, budgetMs }) {
  if (slot === null) return 0;
  if (slot !== 0 && slot !== 1) throw new RangeError('T212 requestSlot must be 0 or 1');
  const offset = slot * 5000;
  let waited = 0;
  for (;;) {
    const phase = ((now() % SLOT_CYCLE_MS) + SLOT_CYCLE_MS) % SLOT_CYCLE_MS;
    if (phase >= offset && phase < offset + SLOT_WIDTH_MS) return waited;
    const delay = (offset - phase + SLOT_CYCLE_MS) % SLOT_CYCLE_MS;
    if (waited + delay > budgetMs) throw new Error('T212 request-slot wait exceeds the remaining retry budget');
    log(`[t212] site ${slot + 1} waiting ${(delay / 1000).toFixed(3)}s for its request window`);
    await sleep(delay);
    waited += delay;
    // A delayed runner must recheck the window instead of sending after it.
  }
}

function retryDelayMs(headers, attempt, now, random) {
  const waits = [];
  const retryAfter = headers.get('retry-after');
  if (retryAfter !== null && retryAfter.trim() !== '') {
    const seconds = Number(retryAfter);
    const delay = Number.isFinite(seconds)
      ? seconds * 1000
      : Date.parse(retryAfter) - now;
    if (Number.isFinite(delay) && delay >= 0) waits.push(delay);
  }
  const resetHeader = headers.get('x-ratelimit-reset');
  const reset = resetHeader === null || resetHeader.trim() === '' ? NaN : Number(resetHeader);
  if (Number.isFinite(reset)) {
    const delay = reset * 1000 - now;
    if (delay >= 0) waits.push(delay);
  }
  // Some 429 responses omit rate-limit headers. Back off for 2, 4, 8, 16 s.
  const delay = waits.length ? Math.max(...waits) : 2000 * 2 ** (attempt - 1);
  return Math.max(MIN_WAIT_MS, delay) + Math.floor(random() * 251);
}

export async function fetchPositions({
  baseUrl,
  apiKey,
  apiSecret,
  requestSlot = null,
  fetchImpl = globalThis.fetch,
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  now = Date.now,
  random = Math.random,
  log = console.warn,
}) {
  const authorization = 'Basic ' + Buffer.from(`${apiKey}:${apiSecret}`, 'utf8').toString('base64');
  let totalWait = 0;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    totalWait += await waitForRequestSlot(requestSlot, { sleep, now, log, budgetMs: MAX_TOTAL_WAIT_MS - totalWait });
    if (requestSlot !== null) log(`[t212] positions request site ${requestSlot + 1} at ${new Date(now()).toISOString()}`);
    const response = await fetchImpl(`${baseUrl}/equity/positions`, {
      headers: { Authorization: authorization },
      signal: AbortSignal.timeout(15_000),
    });
    if (response.ok) return response.json();

    const body = await response.text();
    const error = new Error(`T212 /equity/positions HTTP ${response.status}: ${body}`);
    if (response.status !== 429 || attempt === MAX_ATTEMPTS) throw error;

    const delay = retryDelayMs(response.headers, attempt, now(), random);
    if (totalWait + delay > MAX_TOTAL_WAIT_MS) {
      throw new Error(`${error.message} (rate-limit wait exceeds the remaining retry budget)`);
    }
    log(`[t212] HTTP 429; remaining=${response.headers.get('x-ratelimit-remaining') ?? 'unknown'}, reset=${response.headers.get('x-ratelimit-reset') ?? 'unknown'}; retry ${attempt + 1}/${MAX_ATTEMPTS} in ${(delay / 1000).toFixed(3)}s`);
    await sleep(delay);
    totalWait += delay;
  }
}
