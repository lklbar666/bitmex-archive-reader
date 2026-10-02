# 文件地图

11 个 CSV + 1 个 PNG + `manifest.json`。所有统计值取自 `manifest.json`（`spec_version 1.1`，`generated_at 2026-09-11T10:15:30Z`）。

---

## 一览

| 文件 | 行数 | 列数 | 主键 | 时间范围（首 → 末） | 角色 |
|---|---|---|---|---|---|
| `api-v1-execution.csv` | 173,592 | 55 | `execID` | 2020-05-01T09:03:47.360Z → 2026-07-23T10:00:39.900Z | API 返回的全部执行事件（**非**完整生命周期日志） |
| `api-v1-execution-tradeHistory.csv` | 173,577 | 40 | `execID` | 同上 | **主余额账本** |
| `api-v1-order.csv` | 43,258 | 22 | `orderID` | 同上 | 订单意图 + 每单最新状态 |
| `api-v1-user-walletHistory.csv` | 17,620 | 13 | `transactID` | **2020-05-01T01:05:55.004Z** → 2026-07-23T12:56:05.357Z | 钱包事件账本 |
| `derived-equity-curve.csv` | 17,602 | 21 | `timestamp` | 2020-05-01T14:39:40.387Z → 2026-07-23T12:56:05.357Z | 派生权益曲线 |
| `api-v1-instrument.all.csv` | 3,109 | 98 | `symbol` | 2014-11-21T21:00:02.409Z → 2026-09-11T09:49:55.755Z | 合约规格字典 |
| `api-v1-wallet-assets.csv` | 52 | 14 | `currency` | 无时间戳 | **资产 scale 字典** |
| `api-v1-user-walletSummary.all.csv` | 80 | 10 | 无（汇总） | 无时间戳 | BitMEX 自算汇总，**仅供交叉核对** |
| `api-v1-user-wallet.snapshot-all.csv` | 15 | 10 | `currency` | ⚠ **2025-11-25T09:22:52.847Z** → 2026-07-23T12:56:05.357Z | 终端钱包锚点 |
| `api-v1-user-margin.snapshot-all.csv` | 3 | 25 | `currency` | 2026-07-23T09:07:47.913Z → 2026-07-23T12:56:05.357Z | 终端保证金/权益锚点 |
| `api-v1-position.snapshot.csv` | **0** | 55 | — | **无**（仅表头） | 终端持仓锚点 → **导出时无未平仓** |
| `cumulative-performance.png` | — | — | — | — | 由权益曲线派生 |

---

## ⚠ 三个必须知道的时序陷阱

### 1 · `user-wallet.snapshot-all.csv` 的时间范围只有 1.5 年

`first_time` = **2025-11-25**，不是 2020。
原因是它只列出**近期有活动记录的币种**（15 行里大量 alt 币余额为 0）。

**→ 绝不能用这张表算历史累计出入金。** 累计值要用 `walletHistory` 的 `transactType` 过滤。

对照值（`walletHistory` 推导，与 manifest 汇总一致）：

| 币种 | 累计入金 | 累计出金 |
|---|---|---|
| XBt | 177,199,051 satoshi = **1.77199051 XBT** | 9,951,625,171 satoshi = **99.51625171 XBT** |
| USDt | 0 | 0 |

### 2 · 三个快照是**顺序读取**，不是同一时刻

`manifest.source_export.snapshot_consistency` =
`Sequential API reads, not an atomic account snapshot`

实际时间戳：

| 快照 | 读取时刻 |
|---|---|
| margin（BMEx） | 2026-07-23T09:07:47.913Z |
| margin（USDt） | 2026-07-23T10:00:39.900Z |
| wallet（USDt） | 2026-07-23T10:00:39.900Z |
| **margin + wallet（XBt）** | **2026-07-23T12:56:05.357Z** |

**→ 跨快照做加减会引入最多 3 小时 48 分钟的时间错位。**

### 3 · 导出时刻 ≠ 账本最后事件

| 概念 | 时刻 |
|---|---|
| 账本截止（`ledger_cutoff_utc`） | 2026-09-11T09:43:29Z |
| 导出完成（`completed_at_utc`） | 2026-09-11T09:57:16Z |
| **数据里最后一个账户事件** | **2026-07-23T12:56:05.357Z** |

**→ 2026-07-23 到 09-11 之间约 7 周的活动不在档案里。** 别把它当"截至今天"的镜像。

---

## 终端状态快照（已实测读出）

`margin.snapshot` @ 2026-07-23T12:56:05.357Z：

| 币种 | walletBalance | marginBalance |
|---|---|---|
| **XBt** | **0** | 0 |
| USDt | 5,043,156 | 5,043,156 |
| BMEx | 120,000 | 120,000 |

`position.snapshot`：**0 行数据**。

**→ 导出时该账户无未平仓，且 XBT 已全部换为 USDt。**

---

## 权益曲线基线

| 项 | 值 |
|---|---|
| 基线时刻 | 2020-05-01T14:39:40.387Z（首个交易日的最后一次入金后的首个满仓 XBT 余额） |
| `baselineBalanceXBT` | **1.83953943** |
| 最新调整后财富 | **99.46454272 XBT** |
| 倍数 | **54.070351×** |
| 最新标记市值 | **manifest 汇总为空 —— 未计算**（曲线文件里 `adjustedMarkedWealthXBT` 列存在，但汇总未给出终值） |
| 结算币种分布 | ~98.9% 结算于 XBt，~1.1% USDt |
| BTC 相关标的名义占比 | 全期 ~84.0% ｜ 2022 起 ~93.8% ｜ 2023 起 ~96.1% ｜ 2024 起 ~99.0% |

**注意**：54× 是**钱包等价口径**，已扣除后续入金的影响，但**不是** mark-to-market NAV（作者明确排除全资产 NAV）。
