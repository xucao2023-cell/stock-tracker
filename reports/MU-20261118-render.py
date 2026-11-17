"""Render the independently computed November 18 valuation; no calculations by hand."""
from pathlib import Path
import json
import datetime as dt

ROOT=Path(__file__).resolve().parents[1]
D=json.loads((ROOT/'extracted/revaluation_20261118/valuation_model.json').read_text())
R=D['results']; B=R['base']; FX=D['fx']['rates']['USD']
def money(x):return f'{x*10:,.2f}亿美元'
def usd(x):return f'{x:,.2f}美元/股'
def eur(x):return f'{x:,.2f}欧元/股'
def pct(x):return f'{x:.2%}'
def tab(head,rows):return '\n'.join(['| '+' | '.join(head)+' |','|'+'|'.join(['---']*len(head))+'|']+['| '+' | '.join(map(str,row))+' |' for row in rows])
annual=tab(['财年','收入','营业利润率','税后经营利润NOPAT','折旧摊销','现金净资本开支','Δ经营营运资金','FCFF','t / 折现因子','FCFF现值'],[
 [r['year'],money(r['revenue']),pct(r['operatingMargin']),money(r['nopat']),money(r['da']),money(r['netCashCapex']),money(r['dnwc']),money(r['fcff']),f"{r['t']:.4f} / {r['discountFactor']:.6f}",money(r['pv'])] for r in B['rows']])
hist=tab(['财年','收入','GAAP营业利润','GAAP毛利率','GAAP营业利润率','GAAP稀释EPS'],[
 [h['year'],money(h['revenue']),money(h['ebit']),pct(h['grossMargin']),pct(h['operatingMargin']),usd(h['dilutedEPS'])] for h in D['historicalFinancials']])
mult=tab(['财年末','普通股价格','企业价值EV','统一15.5%税率NOPAT','EV/NOPAT','处理'],[
 [h['date'],usd(h['price']),money(h['ev']),money(h['nopat']),f"{h['evNopat']:.2f}倍" if h['evNopat'] else '亏损无意义',
  '普通盈利年参考' if h['year'] in [2021,2022,2025] else '亏损/复苏谷底/超级景气，仅诊断'] for h in D['historicalMultiples']])
scenario=tab(['区间端点','正常化NOPAT × 退出倍数','高景气到正常化路径','价值美元/股','折合欧元/股'],[
 [name,f"{money(R[k]['normalizedNOPAT'])} × {R[k]['multiple']:.4f}倍",path,usd(R[k]['usdPerShare']),eur(R[k]['eurPerShare'])]
 for name,k,path in [('Z压力','Z_low','FY2027—FY2032，与基准相同盈利，仅倍数下降'),('H下限','H_low','六年正常化'),
 ('基准中枢','base','六年正常化'),('H上限','H_high','六年正常化'),('Z成长','Z_high','FY2027—FY2034，八年正常化')]])
sens=tab(['美元折现率','10倍退出','12倍退出','14倍退出'],[
 [pct(r)]+[eur(x['eur']) for x in D['sensitivity'] if abs(x['r']-r)<1e-9] for r in [.161,.171,.181]])
drift=tab(['顺序变更（美元口径）','每股结果','本步差额'],[
 [x['step'],usd(x['usd']),usd(x['deltaUSD'])] for x in D['oldNewBridge']])
growth=tab(['财年','收入','营业利润率','现金净资本开支','FCFF','FCFF现值'],[
 [r['year'],money(r['revenue']),pct(r['operatingMargin']),money(r['netCashCapex']),money(r['fcff']),money(r['pv'])] for r in R['Z_high']['rows']])
margin_sens=tab(['正常化营业利润率','主锚每股结果'],[[pct(x['margin']),eur(x['eur'])] for x in D['normalMarginSensitivity']])
revenue_sens=tab(['正常化年及退出收入','主锚每股结果'],[[money(x['revenue']),usd(x['usd'])] for x in D['normalRevenueSensitivity']])
q=D['quote']; qtime=dt.datetime.fromtimestamp(q['regularMarketTime'],dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat()
base_oldfx=B['usdPerShare']/D['oldSite']['fx']
text=f'''# 美光重新估值与欧元网站同步依据（2026-11-18）

**正式替代2026-10-15企业文件夹估值：H核心带 {eur(R['H_low']['eurPerShare'])}—{eur(R['H_high']['eurPerShare'])}，中枢 {eur(B['eurPerShare'])}；Z压力/成长带 {eur(R['Z_low']['eurPerShare'])}—{eur(R['Z_high']['eurPerShare'])}。** 美光为强周期存储制造商，主锚采用“有限景气期现金流＋正常化税后经营利润×中周期退出倍数”，同利润口径DCF交叉检查为{eur(R['dcf']['eurPerShare'])}。这是有条件的研究区间，不是公司指引、统计置信区间或保证底价。DCF低于Z下端，单独披露，不把Z称为所有可能结果的包络。

估值时点为北京时间2026-11-18。最新完整财报是**2026财年年报**（截至2026-09-03，业绩于2026-09-30披露，10-K于2026-10-09提交），不是日历年三季报。证券为NASDAQ:MU普通股，一股对应一股，无ADS比例。财务模型内部单位为十亿美元、十亿股；正文各金额逐项转成亿美元和每股价格。采用稀释股数11.50亿股，FY26实际平均11.43亿股仅作核对，不与股权价值混用。

市场比较快照为{qtime}，{usd(q['regularMarketPrice'])}，按本次估值汇率等值{eur(q['regularMarketPrice']/FX)}。这是报告快照，发布时网站另取最新可得成交，两个时间不冒充一致。估值汇率固定为[ECB 2026-11-17参考汇率](https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml)：**1欧元={FX:.4f}美元，欧元/股=美元/股÷{FX:.4f}**。网站行情日后采用自身最新报价汇率，不自动漂移估值。

## 1. 来源分层及新信息的作用

| 类别 | 可追溯输入 | 本次处理 |
|---|---|---|
| 财报事实，一级 | FY26收入1,331.88亿美元、GAAP营业利润993.40亿美元、归母净利849.69亿美元、稀释EPS74.33美元/股；10-K损益表p67 | 作为实际数，不永久外推峰值 |
| 财报事实，一级 | 年经营现金流896.75亿美元、现金净资本开支273.74亿美元、公司调整FCF623.01亿美元；D&A95.03亿美元、SBC13.33亿美元 | 报表现金流包括递延纳税好处；预测使用正常现金税，不额外加回SBC |
| 公司正式指引，一级 | FY27 Q1收入615亿美元±15亿美元；GAAP毛利率85.95%，调整86.25%；GAAP EPS37.84美元/股±1美元/股、调整38.15美元/股±1美元/股；全年税率15.5%，稀释股数约11.5亿股 | 最新指引没有被本任务检索到的后续正式财务披露替换；不凭新闻直接宣布下调 |
| 公司资本开支指引，一级 | FY27 Q1现金净资本开支约115亿美元、上半年约250亿美元、下半年高于上半年；全年营业费用同比约增加25亿美元 | 全年550亿美元是自建输入，不是公司正式全年精确指引 |
| 分析师财务预测，三级汇总 | StockAnalysis/S&P Global最后更新2026-11-09：FY27收入2,758.9亿美元、调整EPS176.50美元/股；FY28收入3,200.6亿美元、调整EPS207.76美元/股；FY27表列43名分析师，EPS独立样本数未核验 | 快照早于11月14/16日风险事件；不把“尚未下调”当作“已证实无影响”；不使用分析师目标价 |
| 自建预测 | FY27收入2,600亿美元、毛利率86%、费用110亿美元；FY28收入2,800亿美元、毛利率82%、费用140亿美元；FY29起见逐年表 | 近两年沿用10月15日基准，收入低于分析师共识；新闻压力另做，不偷换成正式指引 |

本次查询SEC最新提交，11月5日8-K为董事退休，11月12日为Form144，未见新一期10-Q。11月18日TomorrowX活动预定美山地时间10:50，即北京时间11月19日01:50；截至本快照未发生，不能提前写成公司给出了新指引。

新风险已核原文：①[11月14日法院裁定](https://cases.justia.com/federal/district-courts/california/candce/5:2026cv06345/472931/68/0.pdf)驳回DRAM反垄断案撤诉申请，案件继续，尚非赔偿判决；②[BIS 11月16日公告](https://media.bis.gov/sites/default/files/documents/BIS%20Issues%20Rule%20Addressing%20Remote%20Access%20to%20American%20Super%20Intelligence%20Technology.pdf)限制经第三国数据中心远程取得先进算力，不等于全部美光DRAM被禁售；完整规则及美光客户敞口未量化；③[TrendForce 11月11日](https://www.trendforce.com/presscenter/news/20261111-13303.html)PC库存上升、采购趋谨慎，但Q4 PC DRAM合约价仍预计环比上升13%—18%，不可套成全部HBM/服务器价格下降；④[中央社11月17日](https://www.cna.com.tw/news/aipl/202611170103.aspx)劳资争议仍在，暂无可核算的产量损失。保留这些为经营压力与监控，不凭空计提罚款、永久加息或一刀切砍收入。

## 2. 正常化盈利与历史市场锚

{hist}

财报来源：本地`source/MU_FY23_10-K_mu-20230831.htm`、FY24和FY25同类文件的合并损益表及MD&A；FY26年报p67；SEC公司事实XBRL交叉核对。FY23 GAAP毛利为**负14.16亿美元**，与某些财务网站调整口径不同，不能误抄为正值。营业利润由收入减成本及GAAP费用计算，库存减值与重组不默默剔除。

正常化窗口取最近五个完整财年FY2022—FY2026，同时包括FY23亏损和FY26新高：

**正常化营业利润率 = ({' + '.join(pct(x['operatingMargin']) for x in D['historicalFinancials'][1:])}) ÷5 = {pct(D['normalMargin'])}。** 五年简单平均毛利率为{pct(D['normalGrossMargin'])}，不沿用旧模型长期50%毛利率。不能用收入加权后被FY26大幅主导的利润率替代穿越周期年均值。

**正常化收入2,400亿美元 × {pct(D['normalMargin'])}营业利润率 × (1−15.5%) = {money(B['normalizedNOPAT'])}正常化NOPAT；÷11.50亿股 = {usd(B['normalizedCoreEPS'])}核心经营EPS。** 这是税后经营利润/股，非GAAP或分析师调整EPS。2,400亿美元收入仍是低置信自建假设：基于FY27扩产后平台、Tongluo/美国/新加坡计划，给出价格正常化而数量增长的路径；缺少逐产品bit出货量×ASP独立核对，不能称为已验证产能收入。FY22—FY26平均包含新高，可能仍高估旧周期中枢；反之AI/SCA结构改善也可能使旧历史偏低，见敏感性。

{mult}

历史价格取Yahoo逐日未复权收盘，股数取年末实际普通股数；现金、投资、债务含融资租赁取同期年报；为口径一致，历史经营利润也统一按15.5%算NOPAT。以上是事后财年末截面，不是当时已知的前瞻倍数，不做回测收益宣传。FY26 EV另加客户押金和既存税负债，以接近本次桥；早年未逐项重构其他税负债，历史倍数仍为代理。

FY2021/2022/2025普通盈利年度参考为14.91/7.15/16.90倍，中位{D['historicalReferenceMedian']:.2f}倍。FY23亏损、FY24低利润导致约100倍、FY26超级景气单列，不拿谷底极高PE证明应给高倍数。**H取10/12/14倍，中枢12倍低于上述中位**：当前资本成本高、企业接近新一轮供给扩张，保留折价；这是在稀疏历史点内的审慎研究选择，不宣称12倍为精确历史中位或已验证公允倍数。Z压力用样本低值{R['Z_low']['multiple']:.4f}倍，盈利和景气持续期不同时再砍；Z成长用样本高值{R['Z_high']['multiple']:.4f}倍，并延长景气期。没有虚构连续历史前瞻估值分位。

5年逐日收盘价格区间48.88—1,213.56美元/股只作价格阶段观察：公司盈利规模已变化，旧绝对股价不能直接等同今天合理价值。H与历史倍数参考域重叠，但完整行业横向、连续历史前瞻倍数分位仍缺，置信度保留中低。

## 3. 美元资本成本

每次重新用本司完整周复权收益计算：截至2026-11-09标签周（交易截至11月13日），三年156周对SPY Beta={D['betas']['156']['SPY']['beta']:.6f}，R²={D['betas']['156']['SPY']['r2']:.3f}；两年104周={D['betas']['104']['SPY']['beta']:.6f}。对SOXX的行业诊断Beta分别={D['betas']['156']['SOXX']['beta']:.6f}/{D['betas']['104']['SOXX']['beta']:.6f}，R²约0.60。不把SOXX Beta与大盘ERP直接相乘。两种窗口都显示高于1的周期敏感性，旧1.3未经回测，本次不再沿用；近期大涨也会放大经验Beta，未来稳定Beta仍不确定，故给利率敏感性。

美元无风险利率沿用检查单10月22日4.953%缓存；本次^TNX为{D['newTnx']['regularMarketPrice']:.3f}%，差{(D['newTnx']['regularMarketPrice']/100-D['rf'])*10000:.1f}bp，缓存未满一月且变化不足25bp，不刷新全局参数。ERP沿用本月Lumentum等美元报告4.50%，[Damodaran 11月1日调整派息隐含ERP](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/home.htm)4.41%为外部依据；0.09个百分点为明确研究余量，不称4.50%是官网原数。

Ke=4.953%+{D['betas']['156']['SPY']['beta']:.6f}×4.50%={pct(D['ke'])}。债务成本5.2%为市场代理，未逐债验证，税率15.5%；按快照市值{money(D['quote']['regularMarketPrice']*D['shares'])}、账面有息债务51.79亿美元加权，WACC={pct(D['waccExact'])}，模型取**17.10%**。未加规模或流动性溢价。美元现金流用美元折现率，折欧元只在每股结果后做，不用德国利率替换美元利率。

## 4. 现金流过程、资本开支与股权桥

公式：EBIT=收入×营业利润率；NOPAT=EBIT×(1−15.5%)；**FCFF=NOPAT＋折旧摊销−现金净资本开支−Δ经营营运资金**。FY27/FY28的毛利率已包含生产折旧，不能再从毛利重复扣一次折旧；之后只在FCFF桥加回一次。SBC留在GAAP费用/历史利润率内，不作为自由现金加回，不凭回购授权预先减少股数。

修正后的期初经营营运资金：应收361.97亿美元＋库存103.72亿美元−贸易应付35.18亿美元−薪酬应付44.47亿美元−其他应计3.96亿美元−其他流动经营负债43.86亿美元 = **{money(D['nwc0'])}**；÷收入1,331.88亿美元={pct(D['nwcRatio'])}。设备应付86.18亿美元及应交所得税/其他税56.26亿美元不混入营运资金。现金净资本开支假设包括设备付款，因此不再把设备应付从企业价值重复减除；既存税负债则在股权桥一次扣除。营运资金比例是以当前报表为基础的代理，不是已验证稳定周转率。

{annual}

例如FY2027：收入2,600亿美元×81.7692%×84.5%=1,796.47亿美元NOPAT；加120亿美元折旧、减550亿美元现金净资本开支、减{money(B['rows'][0]['dnwc'])}营运资金，得FCFF **{money(B['rows'][0]['fcff'])}**；按(1+17.1%)^{B['rows'][0]['t']:.4f}折现，现值{money(B['rows'][0]['pv'])}。

FY27净资本开支550亿美元符合“上半年250亿美元、下半年更高”的公司方向；FY28的600亿美元及以后600/500/440/380亿美元均为自建，假设项目集中投入后逐步回落。D&A120→280亿美元反映资产投产，未声称是公司折旧指引。FY2030/31营业利润率45%/32%，FY2032回到20.10%，六年为过渡期限；RPO截至2026年覆盖最长五年，不支持2027/28毛利率永续，六年过渡也非合同保证。终年净资本支出100亿美元加营运资金25.39亿美元仍挤占现金；终值DCF按新增投资回报调整，不能只假设资本开支等于折旧。

折现日期以各年8月31日为财年末建模代理，距离估值日分别见t列，并非公司已经发布的精确财年日历。期初净资产仍用9月3日真实报表、FY27全年现金流全额预测：9月至11月已发生部分没有新报表可核对，统一放到FY27末收到，不另造“截至今天新增现金”，也不重复加一份累计盈利。该时点与税款支付期限仍是简化。

股权加减（10-K p68、p77、p88、p90）：

**现金383.64亿美元＋短期投资50.70亿美元＋长期投资300.19亿美元−流动债务4.91亿美元−长期债务46.88亿美元−可退客户现金押金127.47亿美元−当前所得税及其他税56.26亿美元−非流动应付所得税98.20亿美元 = {money(D['netCash'])}。**

客户押金以已收到的现金127.47亿美元代理，不把320亿美元客户财务承诺全当现金。当前税项56.26亿美元含其他税且期限未分拆，非流动税项98.20亿美元来自年报原文，按面值扣减是审慎简化；未来NOPAT现金税只覆盖未来利润，因此扣既存欠税并非重复计税。旧模型净现金555.27亿美元漏减了上述154.46亿美元既存税负债，影响{usd(15.446/1.15)}。不另加未提取20亿美元信贷或未兑现信用证。经营租赁费用留在利润，未作租赁重分类再扣一次债；融资租赁已含于债务。

主锚终值：**{money(B['normalizedNOPAT'])}×12倍={money(B['terminalValue'])}**；÷(1+17.1%)^{B['rows'][-1]['t']:.4f}={money(B['pvTerminal'])}，终值占企业价值{pct(B['terminalShare'])}。

**股权价值=六年FCFF现值{money(B['pvExplicit'])}＋退出价值现值{money(B['pvTerminal'])}＋调整净现金{money(D['netCash'])}={money(B['equityValue'])}；÷11.50亿股={usd(B['usdPerShare'])}；÷{FX:.4f}={eur(B['eurPerShare'])}。** 不再额外加一份“正常盈利×倍数”，也不把近两年EPS×低PE当穿越周期结果。

DCF交叉法保持相同显性期、正常化NOPAT和资产桥：g=3%、增量ROIC=15%为自建；次年终值FCFF={money(B['normalizedNOPAT'])}×1.03×(1−3%/15%)={money(R['dcf']['terminalFCFF'])}；TV=该FCFF÷(17.1%−3%)={money(R['dcf']['terminalValue'])}；终值现值{money(R['dcf']['pvTerminal'])}，占EV{pct(R['dcf']['terminalShare'])}。每股=({money(B['pvExplicit'])}＋{money(R['dcf']['pvTerminal'])}＋{money(D['netCash'])})÷11.50亿股={usd(R['dcf']['usdPerShare'])}={eur(R['dcf']['eurPerShare'])}。主锚高于该DCF{pct(B['usdPerShare']/R['dcf']['usdPerShare']-1)}，未超过30%分歧线；仍不平均。选择正常化盈利市场主锚符合强周期行业，DCF较低结果单独保留，反映资本回报/增长约束与市场退出定价差异，不能说两者相互验证同一个精确值。

## 5. H/Z情景、反向估值及敏感性

{scenario}

H三点均使用{money(B['normalizedNOPAT'])}正常化盈利，只改变10/12/14倍；核心带不是旧中枢±固定百分比。Z压力使用“倍数端”历史样本低值：不再叠加最差盈利或额外罚款，参考低点来自FY2022年末。FY2022归母净利86.87亿美元到FY2023负58.33亿美元的降幅超过100%，机械折半会制造假底，故不用利润回撤公式。Z成长处于本轮高景气、假设高利润维持更久；最终正常化盈利不超过已报FY26核心规模，退出倍数不超过普通盈利年参考高点。Z不是概率分布。

Z成长逐年过程：

{growth}

Z成长FCFF现值{money(R['Z_high']['pvExplicit'])}＋{money(B['normalizedNOPAT'])}×{R['Z_high']['multiple']:.4f}倍的折现终值{money(R['Z_high']['pvTerminal'])}＋净现金{money(D['netCash'])}，÷11.50亿股={usd(R['Z_high']['usdPerShare'])}={eur(R['Z_high']['eurPerShare'])}。其FY2027/28高利润预测超过历史全年EPS，依据公司季度指引所示增长、仍为自建而非已经实现的历史上限；真正入退出倍数的正常化盈利是同一{usd(B['normalizedCoreEPS'])}，没有把未来预测新高冒充历史峰值。

新闻经营压力单独测试：FY27/28收入各减10%、毛利率各减5个百分点，费用/资本开支不降、正常化盈利和12倍不改，FCFF现值从{money(B['pvExplicit'])}降至{money(R['operating_stress']['pvExplicit'])}，每股从{usd(B['usdPerShare'])}变成{usd(R['operating_stress']['usdPerShare'])}，差{usd(R['operating_stress']['usdPerShare']-B['usdPerShare'])}；折欧元{eur(R['operating_stress']['eurPerShare'])}。这是假设冲击的量尺，不声称已验证新闻将造成10%收入损失。诉讼没有可核赔偿区间，未入模；若一年后确定支付10亿美元、无税盾无保险，每股扣10亿美元÷1.171÷11.5亿股={usd(D['legalCashSensitivity'][0]['deltaUSD_perShare'])}，只作单位敏感性。

反向估值按报告价{usd(D['quote']['regularMarketPrice'])}：保持近年FCFF和17.1%折现率不变，需要正常化退出倍数{D['reverse']['requiredExitMultiple']:.2f}倍，或保持12倍但正常化营业利润率约{pct(D['reverse']['requiredNormalMargin'])}（仅调整正常化年和终值）；后者远高于五年平均20.10%，代表结构性改善主张。保持全部经营预测及12倍退出，股价隐含折现率{pct(D['reverse']['impliedPrimaryR'])}；同经营DCF则隐含{pct(D['reverse']['impliedDcfR'])}，均低于本次CAPM/WACC。固定倍数的隐含r是条件求根，不是唯一市场成本估计；公司与市场尚可能采取更强收入、利润或持续期假设。

{sens}

正常化年及终值营业利润率敏感性（其他显性年不变）：

{margin_sens}

{revenue_sens}

上述收入敏感性仅改正常化年/退出收入并重算该年营运资金，非全路径同比例削减。DCF增量ROIC与g是低置信输入，不能用高g无限抬价值。主锚和DCF的终值占比均低于70%，仍完整披露。没有经历史校准的12个月胜率，不能把三情景、目标价或估值差额当获利概率。

## 6. 与10月15日的差额

{drift}

以上每步代码复算，保持其他参数依次不变；其中经营曲线/正常化/期限/资本开支一起换成新主路径，是方法与自建假设修正，不能解释为近期新闻已经导致同额业绩损失。原始DCF{usd(D['oldNewBridge'][0]['usd'])}到新主锚{usd(B['usdPerShare'])}，差{usd(B['usdPerShare']-D['oldNewBridge'][0]['usd'])}。旧综合中枢900美元/股并非原始DCF，其与新中枢差{usd(B['usdPerShare']-900)}；旧750—1,050美元/股还混合了折现率和主观情景判断，新H按同一正常化盈利10—14倍构造，不能逐端当作同比盈利降幅。

旧网站H为671.32—939.85欧元/股（原750—1,050美元/股，固定旧汇率1.1172），新H为{eur(R['H_low']['eurPerShare'])}—{eur(R['H_high']['eurPerShare'])}。以中枢为例：900÷1.1172={eur(900/1.1172)}；先换美元估值为{usd(B['usdPerShare'])}、仍按旧汇率={eur(base_oldfx)}；再更新汇率到1.0989后={eur(B['eurPerShare'])}，其中单纯汇率贡献{eur(B['eurPerShare']-base_oldfx)}。主因是风险/正常化方法修正，汇率只是最后换算。

## 7. 先行指标、承诺与可推翻条件

FY26年报p88：截至9月3日最低价格/固定区间口径RPO1,340亿美元，约四分之一即335亿美元在未来12个月，剩余在五年内；按本模型FY27收入2,600亿美元，RPO总额仅约{134/260:.2f}倍、未来12个月部分约{33.5/260:.2%}覆盖，不能把RPO称为保证五年全额营收。9月30日公司口径RPO1,500亿美元、客户财务承诺320亿美元与此前日期不同；财务承诺含信用证，不全是到账押金。SCA预期约占至2030累计收入35%以上；其中约四分之三预计收入有定价框架，多数有价格上下限，另约四分之一SCA预计收入定期重议价格。公司同时明确判断：即使按价格下限，利润率也将显著高于以往周期峰值；并已签部分延至2031的协议/续期。这是支持更长高利润期的重要定性证据，本模型没有把FY2029即视为旧周期水平，而是到FY2032、现有RPO最长五年及已披露2031延长期之后才正常化。公司未公布下限价格、对应具体利润率或到期续签条款，因此该表述不能量化成永久80%毛利率；如果2027—2031的合同比例或新续签足以证明FY2032后仍明显高于历史，则本次20.10%正常化利润率应上修。新口径自FY26变重要，不能与FY25“不重大”直接算增长率。

年报MD&A p60、Note10 p80：一年内设备采购义务约41.8亿美元，剩余期限超过一年的不可取消采购承诺约108亿美元（FY27/FY28/FY29/FY30/FY31及以后分别13/18/14/11/8/44亿美元）；涉及设备、气体供应等，可能与已建模资本开支/费用重叠，不额外全部扣一次，但支出刚性不能忽略。Tongluo18亿美元收购于2026年3月已完成并入报表，无新在途重大并购股本要做两套；10月8日351.6亿美元回购授权12月9日起可执行，尚不等于已减少股数。

仓位解释：报告价/Z压力约{D['quote']['regularMarketPrice']/R['Z_low']['usdPerShare']:.2f}倍，按检查单≤2倍属价值框架可讨论，但**报告价高于H和本次Z上端，不存在本模型确认的安全边际**。这不是清仓或买卖指令，真实成本/份额未知。

每月看PC/服务器DRAM和NAND合约价、终端库存、BIS许可与客户延期；每季度核对收入、毛利率、应收回收、实际现金税与净资本开支；每次披露核SCA/RPO最低价格覆盖及保证金。会推翻本模型的证据包括：①公司撤回FY27顺序增长/毛利率底部叙述；②连续两个季度经营现金转换显著弱于NOPAT；③新增产能与客户合同证实正常化收入远高于或低于2,400亿美元；④SCA价格底线/盈利含量量化表明20.10%长期营业利润率不适用；⑤可量化诉讼/出口许可/罢工导致现金损失。若高利润跨新供给周期仍稳定，必须按新证据上修正常化盈利，不能固守本次历史均值。

## 附录：检查单完成情况与未验证项目

本次已完整读取全局估值检查单v2.5，**未宣称完整通过**。常规可完成项已做，主要缺口如下。

| 检查项 | 本次结果、缺失证据及影响 |
|---|---|
| 0 属性/行业/仓位 | 已做，强周期；有限景气现金流＋正常化盈利市场退出；价位与仓位框架分开 |
| 0A/A 快照、财报勾稽 | 已做，DRAM1,006.79＋NAND317.85＋其他7.24=1,331.88亿美元；74.33美元/股×11.43亿股≈849.59亿美元，与净利849.69亿美元为舍入差；报告/指导/预测分层 |
| 1 正常化 | 同一五年营业利润率用于显性末年、退出倍数及DCF；正常收入缺bit/ASP验证，结构变化仍低置信 |
| 2 终值 | 已列两种公式/比例、反向和矩阵；不触发>70%规则 |
| 3 市场/历史锚 | 本司历史EV/NOPAT已算，H在历史参考域；仅三个普通盈利年截面，缺连续前瞻分位和同口径同行统计，12倍是判断 |
| 4 先行指标/口径/重大事项/采购 | 最新年报及近期SEC提交、RPO期限/覆盖、保证金及采购义务已核；SCA利润含量、floor金额缺，无法证明长期峰值利润 |
| 5 目标价/胜率 | 目标价不入公式；胜率无校准，不输出伪精确概率 |
| 6 来源分层 | 财报/官方/分析师财务汇总/自建分开；媒体建设消息不直接入损失金额 |
| 7 SOTP | 不适用：使用合并经营利润与企业价值，不拼重复分部价值 |
| 8 折现 | 两/三年本司市场和行业Beta重算；rf/ERP依据、CAPM与隐含r、利率矩阵已列；债务市场成本为代理，未来Beta稳定性未验证 |
| 9 H/Z/漂移 | 正常化盈利×倍数逐端展示，熊市仅降倍数；成长延长有限景气；新旧逐步代码桥；不是概率带 |
| 税/净现金/股数/币种 | 股权桥已扣既存税/押金；当前税混合余额及偿付期、期初到估值日现金桥简化；美元普通股折欧元，没有ADS |
| 完整新闻敞口 | BIS原公告及法院原裁定已核；完整实施细则、客户地区收入暴露、赔偿范围、台湾产量影响缺，不能说“零影响” |
| 发布及自动行情 | 以`site_sync/20261118_site1_mu/publication_status.json`为准；报告生成不等于已发布，必须另查成功证据 |

复现：[计算脚本](scripts/revalue_20261118.py)、[报告脚本](scripts/render_revaluation_20261118.py)、[结果JSON](extracted/revaluation_20261118/valuation_model.json)、[逐年CSV](extracted/revaluation_20261118/cashflows.csv)、[公式工作簿](美光_重新估值模型_20261118.xlsx)。

关键外部原文：[FY26年报](https://www.sec.gov/Archives/edgar/data/723125/000072312526000023/mu-20260903.htm)、[Q4 FY26业绩](https://www.sec.gov/Archives/edgar/data/723125/000072312526000018/a2026q4ex991-pressrelease.htm)、[Q4管理层讲稿](https://s25.q4cdn.com/621799436/files/doc_financials/2026/q4/Q4-FY26-Prepared-Remarks.pdf)、[FY22年报](https://www.sec.gov/Archives/edgar/data/723125/000072312522000048/mu-20220901.htm)、[财务共识](https://stockanalysis.com/stocks/mu/forecast/)、[SEC XBRL事实](https://data.sec.gov/api/xbrl/companyfacts/CIK0000723125.json)。市场接口、汇率、周收益和提交记录快照存`source/revaluation_20261118/`；新闻原文索引见同日新闻专题与其source。
'''
(ROOT/'美光_重新估值与欧元同步_20261118.md').write_text(text)
print('Wrote report',len(text),'characters')
