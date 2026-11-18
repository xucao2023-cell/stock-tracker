import test from 'node:test';
import assert from 'node:assert/strict';
import { parseHkTimestamp, readTencentHkQuote, canReplaceHkQuote } from './tencent_hk_quote.mjs';

const fields = Array(31).fill('0');
fields[1]='腾讯控股'; fields[2]='00700'; fields[3]='372.800'; fields[30]='2026/11/18 16:08:10';

test('Hong Kong close timestamp is preserved as exchange time, not fetch time',()=>{
  const q=readTencentHkQuote('hk00700',fields);
  assert.equal(q.symbol,'00700.HK'); assert.equal(q.currency,'HKD'); assert.equal(q.price,372.8);
  assert.equal(new Date(q.marketTime*1000).toISOString(),'2026-11-18T08:08:10.000Z');
  assert.equal(parseHkTimestamp('2026-02-30 16:00:00'),null);
  assert.equal(parseHkTimestamp(''),null);
});

test('an older HK quote cannot overwrite a newer stored quote',()=>{
  const q=readTencentHkQuote('hk00700',fields);
  assert.equal(canReplaceHkQuote({code:'00700.HK',priceAsOf:'2026-11-18T08:08:11Z'},q),false);
  assert.equal(canReplaceHkQuote({code:'00700.HK',priceAsOf:'2026-11-18T08:08:10Z'},q),true);
  assert.equal(canReplaceHkQuote({code:'00700.HK',priceAsOf:'2026-11-17T08:08:10Z'},q),true);
});

test('security and currency mismatches are rejected before FX conversion',()=>{
  const q=readTencentHkQuote('hk00700',fields);
  assert.equal(canReplaceHkQuote({code:'00700.HK'},{...q,currency:'USD'}),false);
  assert.equal(canReplaceHkQuote({code:'01810.HK'},q),false);
  assert.equal(readTencentHkQuote('hk01810',fields),null);
  assert.equal(readTencentHkQuote('hk00700',fields.map((v,i)=>i===30?'':v)),null);
});
