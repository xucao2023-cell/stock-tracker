// Tencent's Hong Kong timestamps are exchange-local (UTC+08:00).
// Keep reported quote time separate from fetch time and reject stale updates.
export function parseHkTimestamp(raw) {
  const m = String(raw || '').trim().match(/^(\d{4})[/-](\d{2})[/-](\d{2})\s+(\d{2}):(\d{2}):(\d{2})$/);
  if (!m) return null;
  const local = `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}`;
  const ms = Date.parse(local + '+08:00');
  if (!Number.isFinite(ms)) return null;
  // Date.parse can normalise impossible dates such as February 30.
  if (new Date(ms + 8 * 3600_000).toISOString().slice(0, 19) !== local) return null;
  return ms / 1000;
}

export function readTencentHkQuote(tencentSymbol, fields) {
  if (!/^hk\d{5}$/.test(tencentSymbol)) return null;
  const price = Number(fields[3]);
  const marketTime = parseHkTimestamp(fields[30]);
  if (!(price > 0) || !Number.isFinite(price) || marketTime == null) return null;
  if (fields[2] !== tencentSymbol.slice(2)) return null;
  return {
    symbol: tencentSymbol.slice(2) + '.HK', currency: 'HKD', price,
    name: fields[1], marketTime,
    source: 'Tencent Hong Kong ordinary-share quote',
    sourceUrl: 'https://qt.gtimg.cn/q=' + tencentSymbol,
    timestampType: 'Reported Hong Kong exchange quote time, Asia/Hong_Kong',
    timestampPrecision: 'second', session: 'regular',
  };
}

export function canReplaceHkQuote(stock, quote) {
  if (!quote || quote.symbol !== stock.code || quote.currency !== 'HKD' ||
      !(quote.price > 0) || !Number.isFinite(quote.marketTime)) return false;
  const previous = Date.parse(stock.priceAsOf || '');
  return !Number.isFinite(previous) || quote.marketTime * 1000 >= previous;
}
