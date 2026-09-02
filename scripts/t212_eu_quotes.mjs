// scripts/t212_eu_quotes.mjs
//
// Fetch current prices for 6 European stocks from your Trading 212 live
// account via the T212 Public API, write them to data.json, commit, push.
//
// Pre-requisite: 6 EU stocks must be in your T212 portfolio (bought with ~€1
// fractional shares each). T212 positions endpoint only returns CURRENT
// holdings, not arbitrary instruments, so non-held stocks cannot be priced.
//
// Auth: HTTP Basic with TRADING212_API_KEY : TRADING212_API_SECRET.
// Both are read from process.env (set in GitHub Secrets for workflow).
//
// Sources: = Trading 212 Public API v0 (/equity/positions + /equity/account/summary)
//
// Usage:
//   T212_API_KEY=... T212_API_SECRET=... node scripts/t212_eu_quotes.mjs
//   T212_API_KEY=... T212_API_SECRET=... node scripts/t212_eu_quotes.mjs --dry-run
//
// Runs in GitHub Actions (see .github/workflows/update-prices.yml).

import { readFileSync, writeFileSync } from 'node:fs';
import { execSync } from 'node:child_process';

const DRY_RUN = process.argv.includes('--dry-run');
const DATA_PATH = new URL('../data.json', import.meta.url);

const T212_BASE = 'https://live.trading212.com/api/v0';
const T212_KEY = process.env.T212_API_KEY;
const T212_SECRET = process.env.T212_API_SECRET;

if (!T212_KEY || !T212_SECRET) {
  console.error('[fatal] T212_API_KEY and T212_API_SECRET env vars are required');
  process.exit(2);
}

// T212 ticker → data.json code. UNIAa_EQ is the Amsterdam listing of Unilever,
// priced in EUR (matches data.json currency=€ for ULVR.L).
const TICKER_TO_CODE = new Map([
  ['BMWd_EQ', 'BMW.DE'],
  ['AIRd_EQ', 'AIR.PA'],
  ['AIRp_EQ', 'AIR.PA'],
  ['EOANd_EQ', 'EOAN.DE'],
  ['UNIAa_EQ', 'ULVR.L'],
  ['ASMLa_EQ', 'AMS.AS'],
  ['MUV2d_EQ', 'MUV2.DE'],
]);

const SANITY_THRESHOLD = 0.5; // skip if |new-old|/old > 50%

// ---------- helpers ----------

function basicAuthHeader(key, secret) {
  return 'Basic ' + Buffer.from(`${key}:${secret}`, 'utf8').toString('base64');
}

function isInt(v) {
  return Number.isFinite(v) && Number.isInteger(v);
}

function formatPriceLikeOriginal(value, original) {
  const rounded = Math.round(value * 100) / 100;
  if (isInt(original)) return String(Math.round(rounded));
  return String(rounded);
}

// ---------- API fetchers ----------

async function fetchPositions() {
  const res = await fetch(`${T212_BASE}/equity/positions`, {
    headers: { 'Authorization': basicAuthHeader(T212_KEY, T212_SECRET) },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`T212 /equity/positions HTTP ${res.status}: ${text}`);
  }
  return res.json();
}

// ---------- main ----------

async function main() {
  const t0 = Date.now();
  console.log(`[t212_eu_quotes] starting (dry-run=${DRY_RUN})`);

  // 1) Fetch T212 positions
  let positions;
  try {
    positions = await fetchPositions();
  } catch (e) {
    console.error('[t212]', e.message);
    process.exit(1);
  }
  console.log(`[t212] fetched ${positions.length} positions`);

  // 2) Filter to the 6 EU stocks via ticker map
  const codeToPrice = new Map();
  for (const p of positions) {
    const ticker = p.instrument?.ticker;
    const code = TICKER_TO_CODE.get(ticker);
    if (code && Number.isFinite(p.currentPrice) && p.currentPrice > 0) {
      codeToPrice.set(code, p.currentPrice);
    }
  }
  console.log(`[t212] mapped ${codeToPrice.size}/6 EU stocks`);
  if (codeToPrice.size < 6) {
    const missing = ['BMW.DE','AIR.PA','EOAN.DE','ULVR.L','AMS.AS','MUV2.DE']
      .filter((c) => !codeToPrice.has(c));
    console.warn(`[t212] missing in portfolio: ${missing.join(', ')}`);
  }

  if (codeToPrice.size === 0) {
    console.log('[abort] no EU prices found in T212 positions, skipping commit');
    return;
  }

  // 3) Load data.json + apply updates
  const data = JSON.parse(readFileSync(DATA_PATH, 'utf8'));
  let updated = 0, skipped = 0;
  const report = [];
  for (const s of data.stocks) {
    const newPrice = codeToPrice.get(s.code);
    if (newPrice == null) continue;
    const oldPrice = s.price;
    if (oldPrice > 0) {
      const diff = Math.abs(newPrice - oldPrice) / oldPrice;
      if (diff > SANITY_THRESHOLD) {
        report.push(`  ${s.code.padEnd(10)} ${s.name.padEnd(10)} SKIP (sanity: ${oldPrice} → ${newPrice}, Δ ${(diff * 100).toFixed(1)}%)`);
        skipped++;
        continue;
      }
    }
    const formatted = formatPriceLikeOriginal(newPrice, oldPrice);
    const parsedFormatted = isInt(oldPrice) ? parseInt(formatted, 10) : parseFloat(formatted);
    report.push(`  ${s.code.padEnd(10)} ${s.name.padEnd(10)} ${String(oldPrice).padEnd(10)} → ${formatted} (t212)`);
    if (!DRY_RUN) s.price = parsedFormatted;
    updated++;
  }

  console.log('\n=== update report ===');
  for (const line of report) console.log(line);
  console.log(`\n=== summary: updated=${updated} skipped=${skipped} (${((Date.now() - t0) / 1000).toFixed(1)}s) ===`);

  if (DRY_RUN) {
    console.log('\n[dry-run] not writing data.json');
    return;
  }
  if (updated === 0) {
    console.log('\n[abort] no EU updates, skipping commit');
    return;
  }

  // 4) Bump updatedAt + write
  data.updatedAt = new Date().toISOString();
  writeFileSync(DATA_PATH, JSON.stringify(data, null, 2) + '\n');

  // 5) Commit & push
  try {
    execSync('git config user.name "github-actions[bot]"', { cwd: new URL('..', import.meta.url), stdio: 'inherit' });
    execSync('git config user.email "418401008+github-actions[bot]@users.noreply.github.com"', { cwd: new URL('..', import.meta.url), stdio: 'inherit' });
    execSync('git add data.json', { cwd: new URL('..', import.meta.url), stdio: 'inherit' });
    execSync(
      `git commit -m "sync: T212 EU prices @ ${data.updatedAt}"`,
      { cwd: new URL('..', import.meta.url), stdio: 'inherit' }
    );
    execSync('git push origin main', { cwd: new URL('..', import.meta.url), stdio: 'inherit' });
  } catch (e) {
    console.error('[git] push failed:', e.message);
    process.exit(2);
  }

  // 6) Purge jsDelivr CDN
  try {
    const purgeRes = await fetch('https://purge.jsdelivr.net/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: ['/gh/xucao2023-cell/stock-tracker/data.json'] }),
    });
    console.log(`[jsdelivr-purge] status=${purgeRes.status}`);
  } catch (e) {
    console.warn('[jsdelivr-purge] failed (non-fatal):', e.message);
  }
}

main().catch((e) => {
  console.error('[fatal]', e);
  process.exit(1);
});