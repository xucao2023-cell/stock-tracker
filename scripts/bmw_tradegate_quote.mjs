// BMW ordinary share, EUR. Page refresh time is not a last-trade timestamp.
export const BMW_QUOTE_URL = 'https://www.tradegatebsx.com/orderbuch.php?isin=DE0005190003';

function field(html, id) {
  const match = html.match(new RegExp(`<[^>]+\\bid=["']${id}["'][^>]*>([^<]+)<`, 'i'));
  if (!match) throw new Error(`Tradegate BMW missing ${id}`);
  return match[1].trim();
}

export function parseBmwQuote(html, now = Date.now()) {
  if (!html.includes('DE0005190003') || !html.includes('Bayerische Motoren Werke') ||
      !/Handelsw(?:ä|&auml;)hrung[\s\S]{0,1200}\bEUR\b/.test(html)) {
    throw new Error('Tradegate BMW identity/currency mismatch');
  }
  const number = field(html, 'last');
  if (!/^\d+(?:\.\d{3})*,\d{2,4}$/.test(number)) throw new Error('Tradegate BMW invalid last price');
  const price = Number(number.replace(/\./g, '').replace(',', '.'));
  if (!(price > 0)) throw new Error('Tradegate BMW nonpositive last price');
  const day = field(html, 'rt_datum').match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  const clock = field(html, 'rt_zeit');
  if (!day || !/^\d{2}:\d{2}:\d{2}$/.test(clock)) throw new Error('Tradegate BMW invalid refresh timestamp');
  if (!html.includes('CET (UTC+1)')) throw new Error('Tradegate BMW timezone not declared');
  const iso = `${day[3]}-${day[2]}-${day[1]}T${clock}+01:00`;
  const marketTime = Date.parse(iso) / 1000;
  if (!Number.isFinite(marketTime) || marketTime * 1000 > now + 300_000) {
    throw new Error('Tradegate BMW invalid/future refresh timestamp');
  }
  return {price, currency:'EUR', symbol:'BMW.DE', isin:'DE0005190003', marketTime,
    source:'Tradegate BSX', sourceUrl:BMW_QUOTE_URL,
    timestampType:'quote-page-refresh; last-trade timestamp not separately supplied'};
}

export async function fetchBmwQuote() {
  const res = await fetch(BMW_QUOTE_URL, {
    headers: {'User-Agent':'Mozilla/5.0'}, signal:AbortSignal.timeout(20_000), cache:'no-store'
  });
  if (!res.ok) throw new Error(`Tradegate BMW HTTP ${res.status}`);
  return parseBmwQuote(await res.text());
}
