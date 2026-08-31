
// scripts/update_prices.mjs
// Daily price updater for xucao2023-cell/stock-tracker.
//
// Sources:
//   - Tencent qt.gtimg.cn  → batch fetch A-share / HK / US (one HTTP call covers 20+ symbols)
//   - Yahoo v8/finance/chart → European tickers (3 sequential calls with 1500ms throttle)
//
// Usage:
//   node scripts/update_prices.mjs           # update + commit + push
//   node scripts/update_prices.mjs --dry-run # fetch + report only, no writes
//
// Runs in GitHub Actions on cron (see .github/workflows/update-prices.yml).

import { readFileSync, writeFileSync } from 'node:fs';
import { execSync } from 'node:child_process';
import iconv from 'iconv-lite';

const DRY_RUN = process.argv.includes('--dry-run');
const DATA_PATH = new URL('../data.json', import.meta.url);
const TENCENT_URL = 'https://qt.gtimg.cn/q=';
const YAHOO_URL = (sym) => `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?interval=1d&range=5d`;
const YAHOO_UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';
const YAHOO_THROTTLE_MS = 1500;
const SANITY_THRESHOLD = 0.5; // skip price if |new-old|/old > 50%

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------- helpers ----------

// Map a stock's `code` field → Tencent symbol.
//   600036.SH  → sh600036      000858.SZ  → sz000858
//   00700.HK   → hk00700
//   AAPL.US    → usAAPL        (BRK.B.US → usBRKB)
//   AAPL       → usAAPL        (no-suffix US also accepted)
function toTencentCode(code) {
  const c = code.trim();
  if (/^\d{6}\.SH$/.test(c)) return 'sh' + c.slice(0, 6);
  if (/^\d{6}\.SZ$/.test(c)) return 'sz' + c.slice(0, 6);
  if (/^\d{5}\.HK$/.test(c)) return 'hk' + c.slice(0, 5);
  // bare Chinese A-share code (no suffix) — guess by leading digit
  if (/^\d{6}$/.test(c)) return (c.startsWith('6') ? 'sh' : 'sz') + c;
  // .US suffix (e.g. AAPL.US) — strip suffix + any dots (BRK.B.US → usBRKB)
  if (/^[A-Za-z.]+\.US$/.test(c)) return 'us' + c.replace(/\.US$/i, '').replace(/\./g, '').toUpperCase();
  // bare US ticker (AAPL, BRK.B) — just strip dots
  if (/^[A-Za-z.]+$/.test(c)) return 'us' + c.replace(/\./g, '').toUpperCase();
  return null; // not coverable by Tencent (e.g. .DE, .PA)
}

// Yahoo code — strip leading zero for HK (0700.HK not 00700.HK) and drop .US suffix.
// A-share / EU pass through unchanged.
function toYahooCode(code) {
  if (/^\d{5}\.HK$/.test(code)) {
    return code.replace(/^0+/, '') + '.HK'; // 00700.HK → 700.HK
  }
  if (/^[A-Za-z.]+\.US$/.test(code)) {
    return code.replace(/\.US$/i, '');
  }
  return code;
}

function classifyMarket(code) {
  // Tencent covers: A-share (6-digit), HK (5-digit .HK), US (letters or .US).
  // Yahoo covers: everything else (.DE, .PA, etc.).
  const c = code.trim();
  const isA = /^\d{6}(\.SH|\.SZ)?$/.test(c);
  const isHK = /^\d{5}\.HK$/.test(c);
  const isUS = /^[A-Za-z.]+(\.US)?$/.test(c) && !/\.(DE|PA|L|AS|NL|IT|ES|CH)$/i.test(c);
  if (isA || isHK || isUS) return 'tencent';
  return 'yahoo';
}

function isInt(v) {
  return Number.isFinite(v) && Number.isInteger(v);
}

// Format a price preserving the original JSON integer-vs-float shape.
//   453    → "453"      (no decimal point)
//   40.1   → "40.1"     (one decimal places whatever the value actually is)
//   27.62  → "27.62"
function formatPriceLikeOriginal(value, original) {
  if (isInt(original)) {
    return String(Math.round(value));
  }
  // For floats, keep the value as-is. JSON.stringify will use the natural representation.
  return String(value);
}

// ---------- API fetchers ----------

async function fetchTencentBatch(tencentSymbols) {
  if (tencentSymbols.length === 0) return {};
  const url = TENCENT_URL + tencentSymbols.join(',');
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Tencent HTTP ${res.status}`);
  const buf = Buffer.from(await res.arrayBuffer());
  const text = iconv.decode(buf, 'gbk'); // names are GBK; prices are ASCII so unaffected
  const out = {};
  // Response format: v_sh600036="1~name~code~price~...";v_sz000858="...";v_usAAPL="200~...";
  // Symbol can be lowercase prefix + mixed-case letters (usAAPL, usBRKB).
  const re = /v_([A-Za-z][\w]*)="([^"]*)"/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const sym = m[1];
    const fields = m[2].split('~');
    if (fields.length < 4) continue;
    const price = parseFloat(fields[3]);
    if (!Number.isFinite(price) || price <= 0) continue;
    out[sym] = { price, name: fields[1] };
  }
  return out;
}

async function fetchYahooOne(symbol, attempt = 0) {
  // Alternate query1 / query2 for load balancing; retry once on 429.
  const host = (attempt + symbol.charCodeAt(0)) % 2 === 0 ? 'query1' : 'query2';
  const url = `https://${host}.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(toYahooCode(symbol))}?interval=1d&range=5d`;
  const res = await fetch(url, { headers: { 'User-Agent': YAHOO_UA } });
  if (res.status === 429 && attempt < 2) {
    await sleep(2000 * (attempt + 1));
    return fetchYahooOne(symbol, attempt + 1);
  }
  if (!res.ok) throw new Error(`Yahoo ${symbol} HTTP ${res.status}`);
  const j = await res.json();
  const r = j?.chart?.result?.[0];
  const price = r?.meta?.regularMarketPrice;
  const prev  = r?.meta?.chartPreviousClose;
  const currency = r?.meta?.currency;
  if (!Number.isFinite(price)) throw new Error(`Yahoo ${symbol} no price in response`);
  return { price, prev, currency };
}

// ---------- main ----------

async function main() {
  const t0 = Date.now();
  const raw = readFileSync(DATA_PATH, 'utf8');
  const data = JSON.parse(raw);
  const stocks = data.stocks;
  console.log(`[update_prices] ${stocks.length} stocks, dry-run=${DRY_RUN}`);

  // Build batches
  const tencentByStock = []; // [{stock, tencentSym}]
  const yahooSymbols = [];    // [{stock, code}]
  for (const s of stocks) {
    const market = classifyMarket(s.code);
    if (market === 'tencent') {
      const ts = toTencentCode(s.code);
      if (ts) tencentByStock.push({ stock: s, tencentSym: ts });
      else yahooSymbols.push({ stock: s, code: s.code });
    } else {
      yahooSymbols.push({ stock: s, code: s.code });
    }
  }
  console.log(`[update_prices] ${tencentByStock.length} via Tencent (batch), ${yahooSymbols.length} via Yahoo`);

  // Tencent: batch into chunks of 60 (server limit, generous)
  const TENCENT_CHUNK = 60;
  const tencentPrices = {};
  for (let i = 0; i < tencentByStock.length; i += TENCENT_CHUNK) {
    const chunk = tencentByStock.slice(i, i + TENCENT_CHUNK);
    const syms = chunk.map((c) => c.tencentSym);
    try {
      const got = await fetchTencentBatch(syms);
      Object.assign(tencentPrices, got);
    } catch (e) {
      console.warn(`[tencent] batch failed: ${e.message}`);
    }
  }

  // Yahoo: sequential with throttle
  const yahooPrices = {};
  for (let i = 0; i < yahooSymbols.length; i++) {
    const { code } = yahooSymbols[i];
    if (i > 0) await sleep(YAHOO_THROTTLE_MS);
    try {
      yahooPrices[code] = await fetchYahooOne(code);
    } catch (e) {
      console.warn(`[yahoo] ${code} failed: ${e.message}`);
    }
  }

  // Apply updates
  let updated = 0, skipped = 0, failed = 0;
  const report = [];
  for (const s of stocks) {
    let newPrice = null;
    let src = null;

    const market = classifyMarket(s.code);
    if (market === 'tencent') {
      const ts = toTencentCode(s.code);
      const got = tencentPrices[ts];
      if (got) { newPrice = got.price; src = 'tencent'; }
    } else {
      const got = yahooPrices[s.code];
      if (got) { newPrice = got.price; src = 'yahoo'; }
    }

    if (newPrice == null) {
      report.push(`${s.code.padEnd(10)} ${s.name.padEnd(10)} SKIP (no quote)`);
      failed++;
      continue;
    }

    const oldPrice = s.price;
    if (oldPrice > 0) {
      const diff = Math.abs(newPrice - oldPrice) / oldPrice;
      if (diff > SANITY_THRESHOLD) {
        report.push(
          `${s.code.padEnd(10)} ${s.name.padEnd(10)} SKIP (sanity: ${oldPrice} → ${newPrice}, Δ ${(diff * 100).toFixed(1)}%)`
        );
        skipped++;
        continue;
      }
    }

    const formatted = formatPriceLikeOriginal(newPrice, oldPrice);
    const parsedFormatted = isInt(oldPrice) ? parseInt(formatted, 10) : parseFloat(formatted);
    report.push(
      `${s.code.padEnd(10)} ${s.name.padEnd(10)} ${String(oldPrice).padEnd(10)} → ${formatted.padEnd(10)} (${src})`
    );
    if (!DRY_RUN) {
      s.price = parsedFormatted;
    }
    updated++;
  }

  console.log('\n=== update report ===');
  for (const line of report) console.log(line);
  console.log(
    `\n=== summary: updated=${updated} skipped=${skipped} failed=${failed} (${((Date.now() - t0) / 1000).toFixed(1)}s) ===`
  );

  if (DRY_RUN) {
    console.log('\n[dry-run] not writing data.json');
    return;
  }
  if (updated === 0) {
    console.log('\n[abort] no updates — skipping commit');
    return;
  }

  // Bump updatedAt to ISO 8601 UTC with ms precision (matches existing format).
  data.updatedAt = new Date().toISOString();

  // Pretty-print with 2-space indent + trailing newline to match existing style.
  writeFileSync(DATA_PATH, JSON.stringify(data, null, 2) + '\n');

  // Commit & push
  try {
    execSync('git config user.name "github-actions[bot]"', { cwd: new URL('..', import.meta.url), stdio: 'inherit' });
    execSync('git config user.email "41898282+github-actions[bot]@users.noreply.github.com"', { cwd: new URL('..', import.meta.url), stdio: 'inherit' });
    execSync('git add data.json', { cwd: new URL('..', import.meta.url), stdio: 'inherit' });
    execSync(
      `git commit -m "sync: 自动更新收盘价 @ ${data.updatedAt}"`,
      { cwd: new URL('..', import.meta.url), stdio: 'inherit' }
    );
    execSync('git push origin main', { cwd: new URL('..', import.meta.url), stdio: 'inherit' });
  } catch (e) {
    console.error('[git] push failed:', e.message);
    process.exit(2);
  }

  // Purge jsDelivr CDN cache (HANDOFF 第九节踩坑：path 必须是数组)
  try {
    const purgeRes = await fetch('https://purge.jsdelivr.net/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: ['/gh/xucao2023-cell/stock-tracker/data.json'] }),
    });
    const purgeText = await purgeRes.text();
    console.log(`[jsdelivr-purge] status=${purgeRes.status} body=${purgeText.slice(0, 200)}`);
  } catch (e) {
    console.warn('[jsdelivr-purge] failed (non-fatal):', e.message);
  }
}

main().catch((e) => {
  console.error('[fatal]', e);
  process.exit(1);
});
