import test from 'node:test';
import assert from 'node:assert/strict';
import {parseEtTimestamp,parseNasdaqInfo,parseYahooChart,selectLatestQuote,canReplaceQuote,fetchLatestUsQuote} from './latest_us_quote.mjs';
const now = Date.parse('2026-11-09T10:00:00Z');
const regularTime = Date.parse('2026-11-06T21:00:01Z') / 1000;
const preTime = Date.parse('2026-11-09T09:08:00Z') / 1000;
const chart = extra => ({chart:{result:[{meta:{symbol:'ON',currency:'USD',regularMarketPrice:63.31,regularMarketTime:regularTime,...extra?.meta},timestamp:extra?.timestamp || [],indicators:{quote:[{close:extra?.close || []}]}}]}});
const nasdaq = (time='Nov 9, 2026 4:08 AM ET',price='$61.20') => ({data:{symbol:'ON',assetClass:'STOCKS',marketStatus:'Pre-Market',primaryData:{lastSalePrice:price,lastTradeTimestamp:time,isRealTime:true},secondaryData:{lastSalePrice:'$63.31',lastTradeTimestamp:'Closed at Nov 6, 2026 4:00 PM ET'}}});
test('New York time uses winter and summer offsets', () => {
  assert.equal(parseEtTimestamp('Nov 9, 2026 4:08 AM ET'),preTime);
  assert.equal(parseEtTimestamp('Jul 6, 2026 4:08 AM ET'),Date.parse('2026-07-06T08:08:00Z') / 1000);
  assert.equal(parseEtTimestamp('2026-11-06 16:00:01'),regularTime);
  assert.equal(parseEtTimestamp('Feb 31, 2026 4:08 AM ET'),null);
});
test('Nasdaq premarket last sale replaces its prior regular close', () => {
  const quote = parseNasdaqInfo(nasdaq(),'ON',now);
  assert.equal(quote.price,61.2); assert.equal(quote.session,'pre'); assert.equal(quote.marketTime,preTime);
});
test('Yahoo null bars are ignored while its premarket point wins over regular close', () => {
  const quote = parseYahooChart(chart({timestamp:[preTime,preTime+60],close:[62,null]}),'ON',now);
  assert.equal(quote.price,62); assert.equal(quote.session,'pre');
});
test('after-hours point is used after regular close', () => {
  const t = Date.parse('2026-11-06T23:30:00Z') / 1000;
  const quote = parseYahooChart(chart({timestamp:[t],close:[64]}),'ON',now);
  assert.equal(quote.session,'post'); assert.equal(quote.price,64);
});
test('Monday premarket supersedes Friday postmarket', () => {
  const t = Date.parse('2026-11-06T23:30:00Z') / 1000;
  assert.equal(parseYahooChart(chart({timestamp:[t,preTime],close:[64,62]}),'ON',now).price,62);
});
test('latest regular quote supersedes an older extended quote', () => {
  const t = Date.parse('2026-11-09T15:00:00Z') / 1000;
  const quote = parseYahooChart(chart({meta:{regularMarketPrice:65,regularMarketTime:t},timestamp:[preTime],close:[62]}),'ON',t*1000+1000);
  assert.equal(quote.price,65); assert.equal(quote.session,'regular');
});
test('same-minute trade is preferred over chart point, newer minute takes precedence', () => {
  const a=parseNasdaqInfo(nasdaq(),'ON',now),b=parseYahooChart(chart({timestamp:[preTime+9],close:[62]}),'ON',now);
  assert.equal(selectLatestQuote([a,b],now).price,61.2);
  assert.equal(selectLatestQuote([a,{...b,marketTime:preTime+60}],now).price,62);
});
test('wrong ticker and currency cannot enter stored quotes', () => {
  assert.throws(()=>parseYahooChart(chart({meta:{currency:'EUR'}}),'ON',now),/mismatch/);
  assert.throws(()=>parseNasdaqInfo(nasdaq(),'LITE',now),/mismatch/);
});
test('future and nonpositive quote points are ignored', () => {
  const quote = parseYahooChart(chart({timestamp:[preTime,now/1000+3600],close:[0,99]}),'ON',now);
  assert.equal(quote.price,63.31);
});
test('missing extended data falls back to timestamped regular close', () => {
  assert.equal(parseYahooChart(chart(),'ON',now).marketTime,regularTime);
});
test('older quote may not overwrite a newer stored extended quote', () => {
  assert.equal(canReplaceQuote({priceAsOf:'2026-11-09T09:09:00Z'},parseNasdaqInfo(nasdaq(),'ON',now)),false);
});
test('one source outage still returns the other source', async () => {
  const quote = await fetchLatestUsQuote('ON.US',{now,fetchImpl:async url => {
    if(url.includes('nasdaq.com')) throw new Error('network');
    return {ok:true,json:async()=>chart({timestamp:[preTime],close:[62]})};
  }});
  assert.equal(quote.price,62);
});
test('both source outages retain the supplied timestamped fallback', async () => {
  const fallback={symbol:'ON',currency:'USD',price:63.31,marketTime:regularTime,session:'regular'};
  const quote=await fetchLatestUsQuote('ON.US',{fallback,fetchImpl:async()=>{throw new Error('offline');}});
  assert.equal(quote.price,63.31);
});
