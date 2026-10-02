---
name: bitmex-archive-reader
description: 正确读取与查询 bwjoke/BTC-Trading-Since-2020 公开 BitMEX 交易档案（2020-05-01 至 2026-07-23，43,258 订单 / 173,577 成交 / 17,620 钱包事件）。当用户要分析这份档案、算盈亏或权益曲线、统计交易行为、连接订单与成交、核对 manifest 里的 sha256 与数据完整性、或需要判断某个问题能否被该数据回答时使用。核心是八条硬规则：tradeHistory 才是主余额账本、execution 与 tradeHistory 禁止直接拼接、缺失事件不等于事件未发生、快照非原子、两个财富口径不可混用、金额单位须查 wallet-assets 的 scale 而非硬编码 1e8。触发词：BitMEX 档案、BTC-Trading-Since-2020、coolish、54 倍账户、173577 行成交、权益曲线重建、execType 统计、realisedPnl 汇总、撤单率算不出来、manifest.json 校验、sha256 对不对、walletHistory 金额单位换算、contract multiplier 换算。
---

# BitMEX 公开交易档案读取器

一份**数据集的读取规范**，不是数据集本身。

| 项 | 值 |
|---|---|
| 数据源 | `https://github.com/bwjoke/BTC-Trading-Since-2020` |
| 账户 | BitMEX 公开镜像（`@coolish`） |
| 数据窗口 | **2020-05-01T01:05:55.004Z → 2026-07-23T12:56:05.357Z** |
| 账本截止 | 2026-09-11T09:43:29Z ｜ `release_status: final_snapshot`（**不再更新**） |
| 体量 | 11 个 CSV，**150,482,438 B**（两个主表各 65.6 / 68.6 MB） |
| 事实基准 | `manifest.json`（含逐文件 `sha256` / `rows` / `columns` / `coverage_note`） |

**本技能不包含数据。** 需要数据时从仓库或 Releases 下载，并用本技能的脚本校验。

---

## 八条硬规则（读这份档案前必读）

### 1 · 主余额账本是 `tradeHistory`，不是 `execution`

`api-v1-execution-tradeHistory.csv`（173,577 行）是**唯一记录余额变动**的成交账本。
`api-v1-execution.csv`（173,592 行）是 API 返回的**全部执行事件流**。

### 2 · ⚠ 两者重叠，禁止直接拼接

**把 `execution` 与 `tradeHistory` 合并算 PnL 或成交量会重复计数。**
需要合并时，**必须按 `execID` 显式去重**。

### 3 · ⚠ 缺失事件 ≠ 该操作没发生

`execution.csv` 的 `execType` 实际分布（manifest 实测）：

| execType | 次数 |
|---|---|
| `Trade` | 160,642 |
| `Funding` | 12,916 |
| `Settlement` | 19 |
| **`New`** | **8** |
| **`Replaced`** | **6** |
| `TriggeredOrActivatedBySystem` | 1 |

→ 生命周期事件**合计 15 个**。manifest 字段 `complete_historical_lifecycle_guaranteed: false`，
`Canceled` 与 `Rejected` **返回 0 条**。
**结论：撤单率、拒单率、订单存活时长这类指标，这份数据算不出来。** 任何给出这些数字的结论都是编的。

### 4 · `order.csv` 是「最新状态」，不是状态转移日志

43,258 行，每行是**一个订单最后一次被 API 返回的状态**。
想知道订单中途经历过哪些状态——**做不到**。`ordRejReason` 存在但绝大多数为空。

### 5 · join 规则

| 目的 | 键 |
|---|---|
| execution → order | **`orderID`** |
| 定位单条成交事件 | **`execID`** |
| 成交与订单内部匹配 | `trdMatchID` |

**必须用 left join 并保留未匹配的 execution 行** —— 即使 `orderID` 非空，也可能没有对应的 order 记录（API 未返回）。

### 6 · ⚠ 金额单位不是「个币」，是各自最小单位

`XBt` / `deposited` / `withdrawn` 的整数值是 **satoshi（1 XBT = 1e8）**。
换算必须查 `api-v1-wallet-assets.csv` 的 **`scale`** 字段，**不要硬编码 1e8**（不同币种 scale 不同）。

### 7 · ⚠ 三个快照是顺序读取的，不是原子快照

manifest 明写 `snapshot_consistency: Sequential API reads, not an atomic account snapshot`。
`position` / `wallet` / `margin` 分别在不同时间点读取（`position` 读到的是 **0 行 = 无未平仓**）。
**不要把它们当作同一时刻的状态做加减。**

### 8 · ⚠ 两个「财富」口径不同，内部划转不是盈亏

`derived-equity-curve.csv` 同时给出两列：

| 列 | 含义 |
|---|---|
| `adjustedWealthXBT` | 钱包等价财富。基线后**加回已完成出金、减去已完成入金**，内部 `Transfer` 中性化 |
| `adjustedMarkedWealthXBT` | 标记市值，还含未实现盈亏。**本 build 的 manifest 汇总里该值为空 —— 未计算** |

另：`Conversion` 与 XBT↔USDt 的 `SpotTrade` 配对是**钱包内部换币**，**必须中性化**，否则算出假盈亏。

---

## 标准工作流

| 步 | 做什么 | 判据 |
|---|---|---|
| **1** | 校验数据副本 | `scripts/verify_archive.py <目录>` 全部 sha256 一致 |
| **2** | 读 `references/coverage-limits.md` | **确认本次问题落在数据能回答的范围内** |
| **3** | 选主表（见下表） | 不用 `execution` 当主表 |
| **4** | join / 去重 | 按 `execID` 去重；left join 保留未匹配行 |
| **5** | 归一化单位与时间 | 用 `wallet-assets.csv` 的 `scale` 换算；时间统一 UTC |
| **6** | 输出 | **逐条标 [已证实] / [推断]，并写明未覆盖项** |

### 主表选择表

| 你要算什么 | 用哪张表 |
|---|---|
| 余额变动 / 真实 PnL / 资金流 | `api-v1-user-walletHistory.csv` |
| 逐笔成交明细 | `api-v1-execution-tradeHistory.csv` |
| 订单意图与最终状态 | `api-v1-order.csv` |
| 财富曲线 / 净值倍数 | `derived-equity-curve.csv` |
| 合约规格、scale、最小变动价位 | `api-v1-instrument.all.csv`、`api-v1-wallet-assets.csv` |
| 交叉核对 | `api-v1-user-walletSummary.all.csv`（BitMEX 自算汇总，**非主账本**） |

---

## 这份数据能回答 / 不能回答

| 能 | 不能 |
|---|---|
| 逐笔成交的时间、价格、数量、结算币 | 撤单率、拒单率、订单存活时长（见规则 3） |
| 资金流入流出的**时间序列** | 订单的完整状态转移路径（见规则 4） |
| 手工/自主交易的仓位节奏与集中度 | HFT / CLOB 微观结构、毫秒级价格预测（作者本人明确排除） |
| 权益曲线的**钱包等价**口径 | 全资产历史 mark-to-market NAV（作者明确排除） |
| 哪些币种被交易、名义占比 | 账户实名、IP、设备、链上 tx hash（作者已移除） |
| —— | 标的资产的同期价格序列（**需另取数据源**） |

---

## 参考资料路由

| 需要 | 读取 |
|---|---|
| 11 个文件各自的角色、主键、列数、时间范围 | [文件地图](references/file-map.md) |
| `execType` / `ordStatus` / `transactType` / `realisedPnl` / `homeNotional` / `scale` 等字段语义 | [字段语义](references/field-semantics.md) |
| join、去重、单位换算的具体写法 | [连接与去重](references/join-and-dedup.md) |
| **动数据之前先读这个** | [覆盖局限](references/coverage-limits.md) |
| 校验数据副本 + 一致性自检 | [校验手册](references/verification.md) |

---

## 版权与来源声明

上游仓库 **无 LICENSE 文件**（GitHub API `license: null`），即默认保留所有权利。

**本技能是独立撰写的解读工具**：只引用 API 字段名（事实性标识符）与 `manifest.json` 中的统计值，
**不复制上游 README 的正文**。分析结论请自行基于数据得出并标注确定度，不要把本技能当权威来源转述。

- 数据集：`https://github.com/bwjoke/BTC-Trading-Since-2020`
- BitMEX API 文档：`https://docs.bitmex.com/api-explorer/bitmex-api.html`
