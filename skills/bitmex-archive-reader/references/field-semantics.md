# 字段语义

只收录**读错就会算错**的字段。完整列清单见 `manifest.json` 的 `columns` 字段。

---

## 一、三个"时间"字段，别混用

| 字段 | 含义 | 用它做什么 |
|---|---|---|
| `timestamp` | **BitMEX 撮合/事件发生时刻** | ✅ 事件排序、持仓时长、持仓路径 |
| `transactTime` | 交易所写入钱包/账务的时刻 | 资金流对账；可能晚于或早于 `timestamp` |
| `export` 系列 | 见 `file-map.md` | 只用于确认数据边界 |

**规则**：算「持仓多久」「多久平仓」「事件间隔」→ 用 `timestamp`。
算「钱什么时候到账」→ 用 `transactTime`。
**不要因为 `transactTime` 存在就默认它更准** —— manifest 的权益曲线方法说明里，作者的做法是
「BitMEX 同时提供两者时，**优先按 `timestamp` 排序**，但保留 `transactTime` 作为交易所原始字段，
**不盲目当作会计生效顺序**」。

---

## 二、`execType` — 执行事件类型（`execution.csv` 实测分布）

| 值 | 次数 | 含义 | 是否影响余额 |
|---|---|---|---|
| `Trade` | 160,642 | 成交 | ✅ |
| `Funding` | 12,916 | 永续资金费结算 | ✅ |
| `Settlement` | 19 | 交割结算 | ✅ |
| `New` | **8** | 订单创建 | ❌ |
| `Replaced` | **6** | 订单修改 | ❌ |
| `TriggeredOrActivatedBySystem` | 1 | 系统触发 | ❌ |
| `Canceled` | **0（未返回）** | 撤单 | — |
| `Rejected` | **0（未返回）** | 拒单 | — |

**⚠ 后两行的 0 是"API 没返回"，不是"没发生过"。**
manifest 字段 `complete_historical_lifecycle_guaranteed: false`。

**能算的**：`Trade`/`Funding`/`Settlement` 的量价与资金流。
**不能算的**：撤单率、拒单率、改单率、订单存活时长。

---

## 三、`ordStatus` — 订单状态（`execution.csv` 实测分布）

| 值 | 次数 |
|---|---|
| `PartiallyFilled` | 129,342 |
| `Filled` | 44,235 |
| `New` | 15 |

**⚠ 这是 `execution.csv` 里的 `ordStatus`，语义是「该成交发生当时订单的状态」，
不是订单的最终状态。** 订单最终状态在 `order.csv` 里。
两者对同一 `orderID` 可能不同 —— 这是正常的，不要当成冲突。

---

## 四、`transactType` — 钱包事件类型（`walletHistory.csv`）

| 值 | 含义 | 对权益曲线的影响 |
|---|---|---|
| `Deposit` | 外部入金 | **减**（基线后） |
| `Withdrawal` | 外部出金 | **加**（基线后） |
| `Funding` | 资金费 | 计入 |
| `RealisedPNL` | 已实现盈亏 | 计入 |
| `Transfer` | 账户内部划转 | **中性化（必须）** |
| `Conversion` | 币种兑换 | **中性化（必须）** |
| `SpotTrade` | 现货兑换 | **中性化（必须）** |

配 `transactStatus` 使用。`network` 与 `address` 字段在 Withdrawal / Transfer 时**已被上游脱敏**。

### 权益曲线方法（作者公开的 7 步）

1. 追踪 **XBT 与 USDt 的钱包等价财富**
2. 基线 = 首个交易日最后一次入金后的首个满仓 XBT 余额
3. 基线之后：**已完成出金加回、已完成入金减去、内部 `Transfer` 中性化**
4. `Conversion` 与 XBT/USDt `SpotTrade` 配对视为**内部换币，不是亏损**
5. USDt 按钱包账本中**最后一次内部 XBT/USDT 兑换或现货汇率**折回 XBT
6. 事件排序用 `timestamp`（`transactTime` 保留但不当作会计生效顺序）
7. 结果是「公开友好的 XBT 等价财富曲线」，**不是**覆盖所有非 XBT 钱包/资产的历史 NAV

---

## 五、⚠ 金额与单位

| 字段 | 单位 | 换算 |
|---|---|---|
| `orderQty` / `lastQty` / `leavesQty` / `cumQty` | **合约张数** | 需乘 `instrument.multiplier` 才是标的数量 |
| `price` / `lastPx` / `avgPx` | **USD** |  inverse 合约的价格语义不同，务必查 `instrument.isInverse` |
| `execCost` | 结算币 | 符号约定随 `side` 变化 |
| `realisedPnl` | 结算币 | **可能为负**，是已实现盈亏 |
| `homeNotional` / `foreignNotional` | 合约面值 | 配合 `instrument` 解读 |
| `walletHistory.amount` / `fee` / `walletBalance` | **该币种最小单位** | ⚠ 见下 |
| `wallet.snapshot.deposited` / `withdrawn` | **satoshi** | XBt: 1 XBT = 1e8 |
| `margin.snapshot.*Balance` | **该币种最小单位** | USDt 实测 `5043156` = 5,043,156 USDt（scale=1e6） |

### ⚠ 不要硬编码 scale

不同币种的最小单位不同。**必须查** `api-v1-wallet-assets.csv`：

| 字段 | 含义 |
|---|---|
| `currency` | 币种代码 |
| `scale` | **该币种的最小单位换算因子** ← 用这个 |
| `majorCurrency` | 主币种 |
| `currencyType` | 币种类型 |
| `isMarginCurrency` | 是否可作保证金币 |
| `asset` / `networks` | 链上资产与网络（已脱敏） |

---

## 六、两个「财富」列，语义不同

`derived-equity-curve.csv`：

| 列 | 含义 | 何时用 |
|---|---|---|
| `walletBalanceXBT` | XBT 钱包余额 | 看币种余额 |
| `usdtWalletBalanceUSDt` | USDt 钱包余额 | 看币种余额 |
| `xbtUsdtRate` | 折算用汇率 | 复算时核对 |
| **`adjustedWealthXBT`** | **钱包等价财富**（已扣后续入金/加回出金/中性化划转） | ✅ **默认用这个** |
| `adjustedWealthMultipleVsBaseline` | 相对基线倍数 | 报业绩用这个 |
| `adjustedMarkedWealthXBT` | 标记市值，含未实现盈亏 | ⚠ 本 build **未计算终值** |
| `baselineBalanceXBT` / `baselineTimestamp` | 基线 | 复算起点 |
| `cumulativeCompletedDepositsAfterBaselineXBT` | 基线后累计入金 | 对账用 |
| `cumulativeCompletedWithdrawalsAfterBaselineXBT` | 基线后累计出金 | 对账用 |
| `methodologyVersion` | 方法版本 | **复现前先核对这个** |

---

## 七、`instrument` 字典里最常用的字段

`api-v1-instrument.all.csv`（3,109 行 × 98 列）：

| 字段 | 用途 |
|---|---|
| `symbol` | 合约代码（join 键） |
| `isInverse` / `isQuanto` | **价格与盈亏语义** |
| `multiplier` | 合约面值 → 标的数量 |
| `lotSize` | 最小下单张数 |
| `tickSize` | 最小价格变动 |
| `settlCurrency` / `quoteCurrency` / `underlying` | 三币种关系 |
| `state` | 合约状态（是否已下架） |
| `list` / `expiry` | 上市与到期 |
| `makerFee` / `takerFee` | 费率 |
| `fundingInterval` / `fundingRate` | 永续资金费参数 |

⚠ 该表 `first_time` 是 **2014-11-21** —— 含 2020 年之前已下架的合约。**按 `symbol` join 时不要假设都能匹配上。**
