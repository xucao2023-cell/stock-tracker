import test from 'node:test';
import assert from 'node:assert/strict';
import {parseATimestamp,readTencentAQuote,canReplaceAQuote} from './tencent_a_quote.mjs';
const fields=Array(31).fill('');fields[1]='长江电力';fields[2]='600900';fields[3]='31.620';fields[30]='20261120154615';
const now=Date.parse('2026-11-20T12:00:00Z');
test('A-share price retains cents even if the stored price was an integer',()=>{
  const q=readTencentAQuote('sh600900',fields,now);
  assert.equal(q.price,31.62);assert.equal(q.currency,'CNY');assert.equal(q.symbol,'600900.SH');
  assert.equal(canReplaceAQuote({code:'600900.SH',currency:'¥',price:31},q),true);
  assert.equal(new Date(q.marketTime*1000).toISOString(),'2026-11-20T07:46:15.000Z');
  assert.equal(q.session,'regular-close');assert.match(q.timestampType,/snapshot/);
});
test('impossible dates, missing times, future snapshots and wrong securities are rejected',()=>{
  assert.equal(parseATimestamp('20260230150000'),null);assert.equal(parseATimestamp(''),null);
  assert.equal(readTencentAQuote('sh600036',fields,now),null);
  assert.equal(readTencentAQuote('sh600900',fields,Date.parse('2026-11-19T12:00:00Z')),null);
  assert.equal(readTencentAQuote('sh600900',fields.map((x,i)=>i===30?'':x),now),null);
});
test('an older quote cannot replace a newer quote or change the display currency',()=>{
  const q=readTencentAQuote('sh600900',fields,now);
  assert.equal(canReplaceAQuote({code:'600900.SH',currency:'¥',priceAsOf:'2026-11-20T07:46:16Z'},q),false);
  assert.equal(canReplaceAQuote({code:'600900.SH',currency:'¥',priceAsOf:'2026-11-20T07:46:15Z'},q),true);
  assert.equal(canReplaceAQuote({code:'600900.SH',currency:'€'},q),false);
  assert.equal(canReplaceAQuote({code:'600900.SH',currency:'¥'},{...q,currency:'USD'}),false);
});
