import test from 'node:test';
import assert from 'node:assert/strict';
import {parseBmwQuote} from './bmw_tradegate_quote.mjs';

const fixture = `<h2>Bayerische Motoren Werke AG</h2><th>Handelswährung</th>
<td>DE0005190003</td><td>EUR</td><strong id="last">56,50</strong>
<span id="rt_datum">03.11.2026</span><span id="rt_zeit">20:56:03</span>CET (UTC+1)`;
const now=Date.parse('2026-11-03T20:00:00Z');
test('preserves cents and source refresh time with CET conversion',()=>{
  const q=parseBmwQuote(fixture,now);
  assert.equal(q.price,56.5);assert.equal(q.currency,'EUR');assert.equal(q.isin,'DE0005190003');
  assert.equal(new Date(q.marketTime*1000).toISOString(),'2026-11-03T19:56:03.000Z');
  assert.match(q.timestampType,/last-trade timestamp not separately supplied/);
});
test('rejects wrong security or currency',()=>{
  assert.throws(()=>parseBmwQuote(fixture.replace('DE0005190003','DE0005190037'),now),/identity/);
  assert.throws(()=>parseBmwQuote(fixture.replace('<td>EUR','<td>USD'),now),/currency/);
});
test('accepts the provider HTML entity in the currency heading',()=>{
  assert.equal(parseBmwQuote(fixture.replace('Handelswährung','Handelsw&auml;hrung'),now).price,56.5);
});
test('fails closed for missing, malformed or zero last price',()=>{
  for(const price of ['0,00','--','56.50'])assert.throws(()=>parseBmwQuote(fixture.replace('56,50',price),now));
  assert.throws(()=>parseBmwQuote(fixture.replace('id="last"','id="bid"'),now),/missing last/);
});
test('rejects future timestamps and unknown timezone',()=>{
  assert.throws(()=>parseBmwQuote(fixture.replace('03.11.2026','04.11.2026'),now),/future/);
  assert.throws(()=>parseBmwQuote(fixture.replace('CET (UTC+1)','CEST'),now),/timezone/);
});
