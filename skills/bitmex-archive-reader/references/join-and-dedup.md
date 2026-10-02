# 连接、去重与单位换算

可直接改用的 pandas 骨架。所有列名已对照 `manifest.json` 的 `columns` 核实。

---

## 一、⚠ 去重：`execution` 与 `tradeHistory` 禁止直接拼接

两者**行数接近、内容重叠**：

| 表 | 行数 |
|---|---|
| `api-v1-execution.csv` | 173,592 |
| `api-v1-execution-tradeHistory.csv` | 173,577 |
| 差 | **15** |

差值 15 = `execution` 多出的生命周期事件数（`New` 8 + `Replaced` 6 + `TriggeredOrActivatedBySystem` 1）。

**它们不是包含关系**：`tradeHistory` 含余额变动事件，`execution` 额外含少量生命周期事件。
**直接 `concat` 会让那 15 条重复，也会让口径混乱。**

```python
import pandas as pd

ex = pd.read_csv("api-v1-execution.csv")
th = pd.read_csv("api-v1-execution-tradeHistory.csv")

# ✅ 合并口径一：只取余额变动事件
balance_affecting = {"Trade", "Funding", "Settlement"}
bal = ex[ex.execType.isin(balance_affecting)]

# ✅ 合并口径二：需要全部事件时，按 execID 去重
merged = (pd.concat([ex, th])
            .drop_duplicates(subset="execID", keep="first"))

# ❌ 绝对不要这样
# wrong = pd.concat([ex, th])          # 重复计数
# wrong = th.merge(ex, on="execID")    # 一对多膨胀，且口径已混
```

**自检**：`len(merged)` 应 ≈ `len(ex) + 15` 减去真实重复数。若远超，说明 `execID` 有空值或重复。

---

## 二、⚠ join：必须 left join 并保留未匹配行

```python
orders = pd.read_csv("api-v1-order.csv")

# ✅ 正确：left join，保留全部成交
m = th.merge(orders[["orderID", "ordStatus", "ordType", "ordRejReason"]],
             on="orderID", how="left", suffixes=("", "_order"))

unmatched = m["ordStatus_order"].isna().sum()
print(f"未匹配到订单的成交行: {unmatched} / {len(m)}")
```

**为什么必须保留**：API 可能返回了 `orderID` 但没返回对应的 order 记录。
**这些行不是脏数据，是「订单侧信息缺失的成交」** —— 丢掉就低估了成交数。

```python
# ❌ 错误
m = th.merge(orders, on="orderID", how="inner")   # 静默丢行
```

### 对账：行数守恒检查

```python
assert len(m) == len(th), "join 改变了行数 → 检查 orderID 是否重复"
dup = orders.orderID.duplicated().sum()
print(f"order.csv 中重复 orderID: {dup}")   # 期望 0
```

---

## 三、⚠ 金额单位换算

**永远查 scale，不要硬编码 1e8。**

```python
import pandas as pd

assets = pd.read_csv("api-v1-wallet-assets.csv")
SCALE = dict(zip(assets.currency, assets.scale))

def to_major(amount, currency):
    """把最小单位整数换算成主币种。"""
    s = SCALE.get(currency)
    if s is None:
        raise KeyError(f"{currency} 不在 wallet-assets.csv 中，先核对币种代码")
    return amount / s

# 验证（对照 manifest 汇总）
# XBt:  deposited 177,199,051 → 1.77199051
print(to_major(177_199_051, "XBt"))      # 1.77199051
print(to_major(9_951_625_171, "XBt"))    # 99.51625171
# 期望值来自 manifest.equity_curve_summary
```

### 合约张数 → 标的数量

```python
inst = pd.read_csv("api-v1-instrument.all.csv")
MULT = dict(zip(inst.symbol, inst.multiplier))
INV  = dict(zip(inst.symbol, inst.isInverse))

def contract_to_base(qty, symbol):
    m = MULT.get(symbol)
    if m is None:
        raise KeyError(f"{symbol} 不在 instrument 表中（可能已下架或代码不匹配）")
    return qty * m
```

⚠ **inverse 合约**（`isInverse=True`）的 `price` 语义是「USD per XBT」而非「XBT per USD」，
乘 `multiplier` 前先确认方向。

---

## 四、时间处理

```python
for df, name in [(th, "tradeHistory"), (ex, "execution"), (wh, "walletHistory")]:
    df["ts"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    # transactTime 保留但不当会计顺序（见 field-semantics.md 第一节）

th = th.sort_values("ts")
```

**用 `timestamp` 而非 `transactTime` 排序** —— 权益曲线方法即如此。

### 持仓时长的正确算法

```python
# 用相邻同向订单的成交差近似「持仓持续时间」
# ⚠ 这只是近似：完整生命周期不可得（见 coverage-limits.md）
trades = th[th.execType == "Trade"].sort_values("ts")
trades["prev_ts"] = trades["ts"].shift(1)
trades["gap_h"] = (trades["ts"] - trades["prev_ts"]).dt.total_seconds() / 3600
```

---

## 五、内部划转必须中性化

算盈亏时，这几类**不是盈亏**：

```python
NEUTRAL = {"Transfer", "Conversion"}
# SpotTrade 若为 XBT<->USDt 配对，同样中性化

flows = wh[~wh.transactType.isin(NEUTRAL)].copy()
# 剩余有效类型：Deposit / Withdrawal / Funding / RealisedPNL
```

⚠ 漏掉这一步 → 把换币算成亏损或盈利，**结论直接反向**。

---

## 六、复算权益曲线的最小骨架

```python
baseline = 1.83953943          # manifest.equity_curve_summary.baseline_balance_xBT
base_ts  = "2020-05-01T14:39:40.387Z"

wh = pd.read_csv("api-v1-user-walletHistory.csv")
wh["ts"] = pd.to_datetime(wh["timestamp"], utc=True, format="ISO8601")
post = wh[wh["ts"] > pd.Timestamp(base_ts)]

adj = 0.0
for _, r in post.sort_values("ts").iterrows():
    t, amt = r.transactType, r.amount
    if   t == "Withdrawal": adj += amt / SCALE["XBt"]   # 加回
    elif t == "Deposit":    adj -= amt / SCALE["XBt"]   # 减去
    elif t in NEUTRAL:      pass                        # 中性化
    # Funding / RealisedPNL 已在 XBT 余额中体现，不要重复加

wealth = baseline + adj
print(f"复算调整后财富 ≈ {wealth:.8f} XBT")   # 期望 99.46454272
```

若复算值与 `derived-equity-curve.csv` 的 `adjustedWealthXBT` 终值不一致，
先查 `methodologyVersion` 是否与本骨架假设的一致。

---

## 七、交叉核对层

`api-v1-user-walletSummary.all.csv`（80 行）是 **BitMEX 自算的汇总**，列：
`currency, transactType, symbol, amount, fee, walletBalance, marginBalance, pendingDebit, realisedPnl, unrealisedPnl`

**用途**：验证你从 `walletHistory` 聚合出的分类合计是否对得上。
**不要用它当主账本** —— 它是交易所自己算的，可能与逐条事件聚合有舍入或归类差异。

```python
sm = pd.read_csv("api-v1-user-walletSummary.all.csv")
mine = flows.groupby(["currency", "transactType"]).amount.sum().reset_index()
cmp = mine.merge(sm.groupby(["currency", "transactType"]).amount.sum().reset_index(),
                 on=["currency", "transactType"], how="outer",
                 suffixes=("_mine", "_bitmex"))
cmp["diff"] = cmp.get("amount_mine", 0) - cmp.get("amount_bitmex", 0)
print(cmp[cmp["diff"].abs() > 1e-6])   # 期望输出为空
```
