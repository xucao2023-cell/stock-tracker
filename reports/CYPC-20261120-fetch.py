"""Dated CYPC public evidence snapshot; earlier valuation files remain unchanged."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests,hashlib,json,datetime,pymupdf
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'source/revaluation_20261120';OUT=ROOT/'extracted/revaluation_20261120'
SRC.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
URLS={
 'q3_report.pdf':'https://static.cninfo.com.cn/finalpage/2026-10-31/1225648852.PDF',
 'consensus.html':'https://basic.10jqka.com.cn/600900/worth.html',
 'announcements.html':'https://money.finance.sina.com.cn/corp/go.php/vCB_AllBulletin/stockid/600900.phtml',
 'xinjiang.html':'https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12684386&stockid=600900',
 'exchangeable_bond.html':'https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12687120&stockid=600900',
 'storage_official_social.html':'https://www.sina.cn/news/detail/5358649604312058.html',
 'tianfeng.html':'https://stock.finance.sina.com.cn/stock/go.php/vReport_Show/kind/search/rptid/847368911201/index.phtml',
 'kaiyuan.html':'https://stock.finance.sina.com.cn/stock/go.php/vReport_Show/kind/company/rptid/846924220032/index.phtml',
 'dividend_policy.html':'https://www.ctg.com.cn/cypc/tzzgx43/xxtm/glfpzcbh/index.html',
 'quote_tencent.txt':'https://qt.gtimg.cn/q=sh600900',
 'quote_google.html':'https://www.google.com/finance/quote/600900:SHA?hl=zh-CN',
 'quote_investing.html':'https://cn.investing.com/equities/yangtze-power-historical-data',
}
for page in [1,2,3]:
 params=dict(reportName='RPT_VALUEANALYSIS_DET',columns='ALL',filter='(SECURITY_CODE="600900")(TRADE_DATE<=\'2026-11-19\')',pageNumber=page,pageSize=1000,sortColumns='TRADE_DATE',sortTypes='-1',source='WEB',client='WEB')
 URLS[f'valuation_{page}.json']=requests.Request('GET','https://datacenter-web.eastmoney.com/api/data/v1/get',params=params).prepare().url
for symbol in ['sh000995','sh000300']:
 URLS[f'tencent_{symbol}.json']=requests.Request('GET','https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',params={'param':f'{symbol},day,2023-11-01,2026-11-19,800,qfq'}).prepare().url
p1=int(datetime.datetime(2023,11,1,tzinfo=datetime.timezone.utc).timestamp())
p2=int(datetime.datetime(2026,11,20,tzinfo=datetime.timezone.utc).timestamp())
URLS['yahoo_600900.SS.json']=f'https://query1.finance.yahoo.com/v8/finance/chart/600900.SS?period1={p1}&period2={p2}&interval=1d&events=div%2Csplits'

def fetch(item):
 name,url=item
 try:
  r=requests.get(url,timeout=30,headers={'User-Agent':'Mozilla/5.0','Referer':'https://finance.sina.com.cn'});r.raise_for_status()
  if name.endswith('.pdf') and not r.content.startswith(b'%PDF'):raise ValueError('not PDF')
  (SRC/name).write_bytes(r.content)
  if name.endswith('.pdf'):
   d=pymupdf.open(stream=r.content,filetype='pdf');txt='\n'.join(f'\n=== PDF PAGE {i+1} ===\n'+p.get_text(sort=True) for i,p in enumerate(d))
  elif name.endswith('.json'):txt=r.text
  else:
   r.encoding=r.apparent_encoding;txt=BeautifulSoup(r.text,'html.parser').get_text(' ',strip=True)
  (OUT/(Path(name).stem+'.txt')).write_text(txt)
  return dict(file=name,url=url,bytes=len(r.content),sha256=hashlib.sha256(r.content).hexdigest(),fetched_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 except Exception as e:return dict(file=name,url=url,error=str(e))

if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=8) as pool:manifest=list(pool.map(fetch,URLS.items()))
 # Primary PDFs referenced from the announcements, rather than trusting the text mirror alone.
 for label in ['xinjiang','exchangeable_bond']:
  if (SRC/f'{label}.html').exists():
   soup=BeautifulSoup((SRC/f'{label}.html').read_bytes(),'html.parser')
   links=[a.get('href') for a in soup.select('a[href]') if 'file.finance.sina.com.cn' in a.get('href','') and '.PDF' in a.get('href','').upper()]
   if links:manifest.append(fetch((label+'.pdf',links[0])))
 for name in ['2023_annual_report','2024_annual_report','2025_annual_report','2026_h1_report']:
  f=ROOT/'source'/f'{name}.pdf';manifest.append(dict(file=str(f.relative_to(ROOT)),source='existing company filing',sha256=hashlib.sha256(f.read_bytes()).hexdigest()))
 (SRC/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 for x in manifest:print(x['file'],x.get('bytes','existing'),x.get('error','OK'))
