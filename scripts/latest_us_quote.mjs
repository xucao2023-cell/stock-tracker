// USD listings only. Compare reported quote times, never the fetch time.
export const isUsStock = code => /^[A-Z.]+\.US$/i.test(code);
const positive = value => Number.isFinite(value) && value > 0;
const nyParts = new Intl.DateTimeFormat('en-US', {
  timeZone:'America/New_York', year:'numeric', month:'2-digit', day:'2-digit',
  hour:'2-digit', minute:'2-digit', second:'2-digit', hourCycle:'h23'
});
const parts = ms => Object.fromEntries(nyParts.formatToParts(ms).filter(p => p.type !== 'literal').map(p => [p.type, Number(p.value)]));

function fromNyWall(year, month, day, hour, minute, second = 0) {
  const wall = Date.UTC(year, month - 1, day, hour, minute, second);
  let instant = wall;
  for (let i = 0; i < 3; i++) {
    const p = parts(instant);
    instant += wall - Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
  }
  const p = parts(instant);
  if ([p.year,p.month,p.day,p.hour,p.minute,p.second].some((v,i) => v !== [year,month,day,hour,minute,second][i])) return null;
  return instant / 1000;
}

export function parseEtTimestamp(text) {
  if (typeof text !== 'string') return null;
  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/);
  if (iso) return fromNyWall(...iso.slice(1).map(Number));
  const m = text.replace(/^Closed at\s+/i, '').match(/^([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)\s+ET$/i);
  if (!m) return null;
  const month = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'].indexOf(m[1].toLowerCase()) + 1;
  const hour = Number(m[4]);
  if (!month || hour < 1 || hour > 12 || Number(m[5]) > 59 || Number(m[6] || 0) > 59) return null;
  return fromNyWall(Number(m[3]),month,Number(m[2]),hour % 12 + (m[7].toUpperCase() === 'PM' ? 12 : 0),Number(m[5]),Number(m[6] || 0));
}

function sessionAt(time) {
  const p = parts(time * 1000), minute = p.hour * 60 + p.minute;
  if (minute >= 240 && minute < 570) return 'pre';
  if (minute >= 570 && minute <= 960) return 'regular';
  if (minute > 960 && minute < 1200) return 'post';
  return null;
}

export function selectLatestQuote(candidates, now = Date.now()) {
  const valid = candidates.filter(q => q && positive(q.price) && positive(q.marketTime) &&
    q.marketTime * 1000 <= now + 60_000 && q.currency === 'USD');
  // Last-sale and minute-bar timestamps are comparable only to their stated precision.
  valid.sort((a,b) => Math.floor(b.marketTime / 60) - Math.floor(a.marketTime / 60) ||
    (b.priority || 0) - (a.priority || 0) || b.marketTime - a.marketTime);
  return valid[0] || null;
}

export function parseNasdaqInfo(payload, symbol, now = Date.now()) {
  const data = payload?.data;
  if (data?.symbol?.toUpperCase() !== symbol.toUpperCase() || data.assetClass?.toUpperCase() !== 'STOCKS') throw new Error('Nasdaq security mismatch');
  const candidates = [];
  for (const key of ['primaryData','secondaryData']) {
    const row = data[key];
    if (!row || !/^\$[\d,.]+$/.test(row.lastSalePrice || '')) continue;
    const price = Number(row.lastSalePrice.slice(1).replaceAll(',',''));
    const marketTime = parseEtTimestamp(row.lastTradeTimestamp);
    if (!positive(marketTime)) continue;
    let session = /^Closed at/i.test(row.lastTradeTimestamp) ? 'regular' : sessionAt(marketTime);
    if (key === 'primaryData' && /after.?hours/i.test(data.marketStatus || '') && session === 'regular' && parts(marketTime * 1000).hour === 16) session = 'post';
    if (!session) continue;
    candidates.push({symbol,currency:'USD',price,marketTime,session,source:'Nasdaq last sale',
      sourceUrl:`https://api.nasdaq.com/api/quote/${encodeURIComponent(symbol)}/info?assetclass=stocks`,
      timestampType:'Reported last-sale time in America/New_York; minute precision unless seconds supplied',
      timestampPrecision: /:\d{2}:\d{2}\s/.test(row.lastTradeTimestamp) ? 'second' : 'minute',
      sourceReportedRealTime:row.isRealTime === true, priority:70});
  }
  return selectLatestQuote(candidates, now);
}

export function parseYahooChart(payload, symbol, now = Date.now()) {
  const chart = payload?.chart?.result?.[0], meta = chart?.meta;
  if (meta?.symbol !== symbol || meta.currency !== 'USD') throw new Error('Yahoo security/currency mismatch');
  const sourceUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=1m&range=1d&includePrePost=true`;
  const candidate = (price,marketTime,session,kind,priority) => ({symbol,currency:'USD',price,marketTime,session,
    source:'Yahoo extended-hours chart',sourceUrl,timestampType:kind,timestampPrecision:'second',priority});
  const candidates = [candidate(meta.regularMarketPrice,meta.regularMarketTime,'regular','Regular-market quote time',50)];
  for (const session of ['pre','post']) candidates.push(candidate(meta[session+'MarketPrice'],meta[session+'MarketTime'],session,'Extended-market quote time',60));
  const close = chart?.indicators?.quote?.[0]?.close || [];
  const periods = Object.entries(meta.tradingPeriods || {}).flatMap(([session,groups]) =>
    Array.isArray(groups) ? groups.flat(Infinity).filter(p => p && typeof p === 'object').map(p => ({...p,session})) : []);
  for (const [i,time] of (chart.timestamp || []).entries()) {
    if (!positive(time)) continue;
    const period = periods.find(p => time >= p.start && time < p.end);
    const session = period?.session || sessionAt(time);
    if (session) candidates.push(candidate(close[i],time,session,'Latest available 1-minute interval close; timestamp belongs to chart point',20));
  }
  const selected = selectLatestQuote(candidates, now);
  if (selected) selected.regularQuote = {price:meta.regularMarketPrice,marketTime:meta.regularMarketTime};
  return selected;
}

export function canReplaceQuote(stock, quote) {
  const previous = Date.parse(stock.priceAsOf || '');
  return positive(quote?.price) && positive(quote?.marketTime) &&
    (!Number.isFinite(previous) || quote.marketTime * 1000 >= previous);
}

export async function fetchLatestUsQuote(code, {fallback = null, fetchImpl = fetch, now = Date.now(), log = () => {}} = {}) {
  const symbol = code.replace(/\.US$/i, '').toUpperCase();
  const endpoints = [
    {name:'Nasdaq',url:`https://api.nasdaq.com/api/quote/${encodeURIComponent(symbol)}/info?assetclass=stocks`,parse:parseNasdaqInfo},
    {name:'Yahoo',url:`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=1m&range=1d&includePrePost=true`,parse:parseYahooChart}
  ];
  const results = await Promise.allSettled(endpoints.map(async endpoint => {
    const response = await fetchImpl(endpoint.url, {headers:{'User-Agent':'Mozilla/5.0','Accept':'application/json','Origin':'https://www.nasdaq.com'},signal:AbortSignal.timeout(7000),cache:'no-store'});
    if (!response.ok) throw new Error(`${endpoint.name} HTTP ${response.status}`);
    return endpoint.parse(await response.json(),symbol,now);
  }));
  const candidates = fallback ? [fallback] : [];
  results.forEach((result,i) => {
    if (result.status === 'fulfilled') candidates.push(result.value);
    else log(`${code} ${endpoints[i].name}: ${result.reason.message}`);
  });
  const selected = selectLatestQuote(candidates, now);
  if (!selected) throw new Error(`No timestamped USD quote for ${symbol}`);
  selected.regularQuote ||= candidates.find(q => q?.regularQuote)?.regularQuote ||
    (fallback?.session === 'regular' ? {price:fallback.price,marketTime:fallback.marketTime} : undefined);
  return selected;
}
