# 线索来源与查询模板

## 需求端/供给端词根表

本 skill 找的是**需方**（买货的），不是**供方**（卖货的同行）。组合查询词时按下表选词根：

| 需求端词根（找买家，优先用） | 供给端词根（会命中同行，慎用/只用于渠道型 ICP） |
|---|---|
| buyer / purchasing / procurement | manufacturer / producer / factory |
| importer / distributor wanted | supplier / exporter（除非 ICP 是 distributor/importer，此二词恰是需方自称） |
| contractor / installer / EPC + `<地区>` | B2B 平台卖家页（Alibaba supplier、Made-in-China 供应商） |
| tender / award / project + `<品类>` | 「dealer wanted / 招代理」类页面主体（它们在找渠道，不在找货源） |
| approved vendor / supplier list（政府/业主备案） | 同行聚合目录本身（可作线索源，但目录上的生产商条目不是候选） |

注意：`supplier`/`exporter` 一词两头用——需方（分销商、进口商）的自我介绍里常说「we are a supplier of…」，供给端公司也说自己是 supplier。判定看**采购关系**（它从别处进货吗），不看称呼，细则见 segmentation.md 的供需判定。

## 通用来源

- 政府/公用事业备案承包商名单
- 行业展会参展商目录
- 行业协会会员名单
- 行业目录（如 ENF Solar）
- 项目新闻/中标公告
- 招标/采购平台
- 公司官网、LinkedIn

## 查询模板

- `<产品> + <地区> + (EPC OR installer OR contractor OR distributor OR importer)` — 需求端词根组合
- `<产品> + <地区> + (tender OR award OR procurement)` — 项目/采购反查
- `site:linkedin.com <产品> <地区> (purchasing OR procurement OR buyer)`
- `site:enfsolar.com <品类> <国家> (EPC OR installer)` — 目录页只取服务类条目，跳过生产商
- `<地区> solar/光伏 approved contractor list`
- `<地区> tender/award <品类>`

## 本地语言提示

中东阿拉伯语关键词（按需）：

- طاقة شمسية（太阳能）
- مقاول（承包商）
- أنظمة تركيب（支架系统）

## 区域补充

- 阿联酋：DEWA、ADDC/AADC 备案光伏承包商名单
- 沙特：SaudiGulf Projects、本地 CR 商业注册
- 卡塔尔/阿曼/巴林/约旦/埃及：本地商业目录与展会名录

优先用官方名单，其次是展会/协会，再次是第三方目录。
