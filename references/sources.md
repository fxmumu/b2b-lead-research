# 线索来源与查询模板

本文件提供**通用框架**；具体来源清单按行业替换（见文末「分行业示例」）。查找目标始终是**需方**（买货的），不是**供方**（卖货的同行）。

## 1. 需求端 / 供给端词根表

组合查询词时按下表选词根：

| 需求端词根（找买家，优先用） | 供给端词根（会命中同行，慎用/只用于渠道型 ICP） |
|---|---|
| buyer / purchasing / procurement | manufacturer / producer / factory |
| importer / distributor wanted | supplier / exporter（除非 ICP 是 distributor/importer，此二词恰是需方自称） |
| contractor / installer / EPC + `<地区>` | B2B 平台卖家页（Alibaba supplier、Made-in-China 供应商） |
| tender / award / project + `<品类>` | 「dealer wanted / 招代理」类页面主体（它们在找渠道，不在找货源） |
| approved vendor / supplier list（政府/业主备案） | 同行聚合目录本身（可作线索源，但目录上的生产商条目不是候选） |

注意：`supplier`/`exporter` 一词两头用——需方（分销商、进口商）的自我介绍里常说「we are a supplier of…」，供给端公司也说自己是 supplier。判定看**采购关系**（它从别处进货吗），不看称呼，细则见 segmentation.md 的供需判定。

## 2. 通用来源类别（不依赖行业）

1. 政府 / 公用事业备案名单、招投标平台
2. 行业展会参展商目录（按目标行业选展会）
3. 行业协会会员名单
4. 垂直行业目录 / B2B 平台（只取需方条目，跳过生产商）
5. 项目 / 中标 / 采购新闻
6. 公司官网（About / Products / 经销页）、LinkedIn
7. 公司注册库（真实性核验用）：Companies House（UK）、Companies NZ、Pappers（FR）、Handelsregister（DE）、KVK（NL）、州务卿 / SEC（US）

## 3. 通用查询模板

- `<产品> + <地区> + (buyer OR importer OR distributor OR contractor OR installer OR EPC)` — 需求端词根组合
- `<产品> + <地区> + (tender OR award OR procurement)` — 项目 / 采购反查
- `site:linkedin.com <产品> <地区> (purchasing OR procurement OR buyer)`
- `<地区> <品类> approved contractor / vendor list`
- `<地区> dealer OR stockist OR stockists wanted <品类>` — 渠道型需方
- `<品牌/品类> + (trade show OR expo OR fair) + exhibitor list` — 展会名录

## 4. 本地语言提示（按目标市场替换）

用目标市场的本地语言扩展词根，例如：

- 法语：`cosmétique naturelle`、`acheteur`、`fournisseur de`
- 德语：`natürliche Hautpflege`、`Einkauf`、`Lieferant`
- 荷兰语：`natuurlijke huidverzorging`、`inkoper`
- 阿拉伯语（中东）：`طاقة شمسية`（太阳能）、`مقاول`（承包商）、`أنظمة تركيب`（支架系统）

## 5. 分行业示例（示例，非唯一）

> 下列仅为**示例**，说明如何把通用框架落到具体行业；实际任务按 `leads.yaml` 的产品替换。

### 例：光伏 / 支架（工程类）

- 目录：ENF Solar（只取 EPC / installer 条目，跳过生产商）
- 政府备案：阿联酋 DEWA / ADDC 备案承包商、沙特 SaudiGulf Projects
- 模板：`site:enfsolar.com <品类> <国家> (EPC OR installer)`、`<地区> solar approved contractor list`
- 本地语言：阿拉伯语「太阳能 / 承包商 / 支架系统」

### 例：化妆品 / 护肤品包装（快消类）

- 行业媒体：Paris Packaging Week、Formes de Luxe、Premium Beauty News、Cosmoprof 展商名录
- 独立品牌榜单 / 社群：NewBeauty Indie 360、The Ethos、Sustainable Jungle、Beauty Independent
- 公司注册：Companies NZ、Companies House（UK）、Pappers（FR）
- 模板：`<地区> indie skincare brand founder`、`<地区> natural cosmetics brand (stockist OR retailer)`、`"made in <地区>" skincare glass packaging`

### 例：通用机械 / 零部件（B2B 类）

- 目录：行业展会（如 Hannover Messe）、Europages、ThomasNet（US）
- 模板：`<地区> <部件> distributor OR importer`、`<地区> <部件> approved supplier list`

## 6. 优先级

优先用官方名单，其次是展会 / 协会，再次是第三方目录。
