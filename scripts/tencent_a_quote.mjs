// A-share native CNY quote metadata. The upstream snapshot timestamp may refresh
// after the market closes; it must not be described as a last-trade timestamp.
export function parseATimestamp(raw) {
  const m=String(raw||'').trim().match(/^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$/);
  if(!m) return null;
  const local=`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}`;
  const ms=Date.parse(local+'+08:00');
  if(!Number.isFinite(ms)||new Date(ms+8*3600000).toISOString().slice(0,19)!==local) return null;
  return ms/1000;
}

export function readTencentAQuote(symbol,fields,now=Date.now()) {
  if(!/^(sh|sz)\d{6}$/.test(symbol)||fields[2]!==symbol.slice(2)) return null;
  const price=Number(fields[3]), marketTime=parseATimestamp(fields[30]);
  if(!(price>0)||!Number.isFinite(price)||marketTime==null||marketTime*1000>now+300000) return null;
  return {symbol:symbol.slice(2)+(symbol.startsWith('sh')?'.SH':'.SZ'),currency:'CNY',
    price:Math.round(price*100)/100,name:fields[1],marketTime,
    source:'Tencent A-share native CNY quote',sourceUrl:'https://qt.gtimg.cn/q='+symbol,
    timestampType:'Reported Tencent quote snapshot time, Asia/Shanghai; not necessarily last-trade time',
    timestampPrecision:'second',session:Number(fields[30].slice(8,12))>=1500?'regular-close':'regular'};
}

export function canReplaceAQuote(stock,quote) {
  if(!quote||quote.symbol!==stock.code||quote.currency!=='CNY'||
    !['¥','CNY','RMB'].includes(stock.currency)||!(quote.price>0)||!Number.isFinite(quote.marketTime)) return false;
  const previous=Date.parse(stock.priceAsOf||'');
  return !Number.isFinite(previous)||quote.marketTime*1000>=previous;
}
