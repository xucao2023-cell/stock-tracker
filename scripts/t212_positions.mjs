// Trading 212 rate limits are shared by the whole account, including other sites.
// https://docs.trading212.com/api/section/rate-limiting/response-headers
const MAX_ATTEMPTS = 5;
const MAX_TOTAL_WAIT_MS = 90_000;
const MIN_WAIT_MS = 1_000;

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
  fetchImpl = globalThis.fetch,
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  now = Date.now,
  random = Math.random,
  log = console.warn,
}) {
  const authorization = 'Basic ' + Buffer.from(`${apiKey}:${apiSecret}`, 'utf8').toString('base64');
  let totalWait = 0;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
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
