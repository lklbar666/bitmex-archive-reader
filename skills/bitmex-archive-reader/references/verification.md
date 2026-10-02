# 校验手册

**动数据之前先证明副本是完整的。** 一份被截断的 CSV 不会报错，只会静默给你错误的行数。

---

## 一、sha256 校验（唯一强证据）

`manifest.json` 为每个文件给出 `sha256` 与 `size_bytes`。逐字节比对即可证明副本未被改动。

```bash
PY="C:/Users/15836/.workbuddy/binaries/python/versions/3.13.12/python.exe"
SK="C:/Users/15836/.workbuddy/skills/bitmex-archive-reader"

"$PY" "$SK/scripts/verify_archive.py" <档案目录>
```

| 参数 | 用途 |
|---|---|
| 无参数 | 全部 14 个文件都算 sha256（**首次下载后必跑**） |
| `--skip-large` | 跳过 >5 MB 的文件（`execution.csv` / `tradeHistory.csv` / `order.csv` / `equity-curve.csv`），约几秒 |
| `--no-hash` | 只比对字节数与行数，**不验完整性**，仅用于改动后快速自查 |
| `--json` | 机器可读，便于接入其他流程 |

退出码：`0` 全部通过 ｜ `1` 有不一致或缺失 ｜ `2` 用法错误 / 找不到 manifest

### 手工核对单个文件

```bash
# macOS / Git Bash
shasum -a 256 api-v1-order.csv
# PowerShell
Get-FileHash api-v1-order.csv -Algorithm SHA256
# Python（跨平台）
python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" api-v1-order.csv
```

### 用 API 取单个文件

`raw.githubusercontent.com` 直连可能不稳，**用 `api.github.com` 的 contents 接口更可靠**：

```bash
curl -sL -H "Accept: application/vnd.github.raw" \
  "https://api.github.com/repos/bwjoke/BTC-Trading-Since-2020/contents/<文件名>" -o <文件名>
```

---

## 二、⚠ 一个必须知道的事实：manifest 只声明 14 个文件

`manifest.json` 的 `files` 数组含 **14 项**（11 个 CSV + PNG + 2 个 README）。
**`manifest.json` 自身不在其中** —— 所以「14/14 一致」**不代表 manifest 可信**。

要验证 manifest 本身，只能靠：
- 交叉核对 manifest 内部数值与 CSV 实际行数（脚本已做）
- 交叉核对 manifest 汇总值与 CSV 聚合值（见下）

---

## 三、内部一致性交叉核对

### 3.1 `execution` 与 `tradeHistory` 的行数差 = 生命周期事件数

```
173,592 − 173,577 = 15
```

而 `execution.exec_type_counts` 里非余额变动事件恰好：
`New 8 + Replaced 6 + TriggeredOrActivatedBySystem 1 = 15` ✅

**对上了 → 两表口径自洽。若对不上，说明 manifest 与 CSV 不同版本。**

### 3.2 钱包累计值 vs manifest 汇总

```python
import pandas as pd, json
m = json.load(open("manifest.json", encoding="utf-8"))
s = m["equity_curve_summary"]

wh = pd.read_csv("api-v1-user-walletHistory.csv")
dep = wh[(wh.transactType == "Deposit") & (wh.transactStatus == "Completed")].amount.sum()
wdr = wh[(wh.transactType == "Withdrawal") & (wh.transactStatus == "Completed")].amount.sum()

print(dep / 1e8, "vs", s["completed_deposits_total_xbt"])    # 期望 1.77199051
print(wdr / 1e8, "vs", s["completed_withdrawals_total_xbt"]) # 期望 99.51625171
```

⚠ 必须按 `transactStatus == "Completed"` 过滤 —— 未完成的出入金不计入。
（`scale` 请改用 `wallet-assets.csv` 的 `scale` 字段，不要硬编码 `1e8`，见 `field-semantics.md`）

### 3.3 权益曲线终值

```python
eq = pd.read_csv("derived-equity-curve.csv")
print(eq.adjustedWealthXBT.iloc[-1], "vs", s["latest_adjusted_wealth_xbt"])   # 99.46454272
print(eq.adjustedWealthMultipleVsBaseline.iloc[-1], "vs", s["latest_adjusted_wealth_multiple"])  # 54.070351
```

### 3.4 `instrument` join 覆盖率

```python
inst = pd.read_csv("api-v1-instrument.all.csv")
KNOWN = set(inst.symbol)
th = pd.read_csv("api-v1-execution-tradeHistory.csv", usecols=["symbol"])
miss = th[~th.symbol.isin(KNOWN)].symbol.value_counts()
print(f"未匹配 symbol: {len(miss)} 种 / {miss.sum()} 行")
```

**期望有少量未匹配** —— 合约可能已下架或代码变更。
**未匹配行必须保留并在结论中披露，不要静默 drop。**

---

## 四、已完成的验证（2026-10-02 实测）

在本次核查中，用 `api.github.com` 取小文件并逐字节校验：

| 文件 | 字节 | sha256 对 `manifest` |
|---|---|---|
| `README.md` | 13,480 | ✅ 一致 |
| `README.zh-CN.md` | 13,171 | ✅ 一致 |
| `api-v1-position.snapshot.csv` | 716 | ✅ 一致 |
| `api-v1-user-margin.snapshot-all.csv` | 704 | ✅ 一致 |
| `api-v1-user-wallet.snapshot-all.csv` | 881 | ✅ 一致 |
| `api-v1-user-walletSummary.all.csv` | 4,859 | ✅ 一致 |
| `api-v1-wallet-assets.csv` | 17,456 | ✅ 一致 |

**7 / 7 完全一致。**
两个大 CSV（`execution.csv` 65,583,792 B ／ `tradeHistory.csv` 68,621,108 B）**当时未下载**，故未校验。

### 同时实测读出的三项事实

| 事实 | 依据 |
|---|---|
| **导出时无未平仓** | `position.snapshot.csv` **0 行数据**（仅表头） |
| **XBt 已全部换为 USDt** | `margin.snapshot` @ 2026-07-23T12:56:05.357Z：XBt `walletBalance = 0`；USDt = 5,043,156 |
| **并非纯 BTC 账户** | `walletSummary` 含 `XBt,RealisedPNL,AAVEUSDT,71730556`（0.7173 XBT 的 USDC 结算盈亏），与「~1.1% settles in USDt」一致 |

---

## 五、下载建议

| 方式 | 说明 |
|---|---|
| **Releases 页** | 上游提供 `.zip` / `.tar.gz` 的单次下载，**比 clone 全历史省流量** |
| `codeload` zip | `https://codeload.github.com/bwjoke/BTC-Trading-Since-2020/zip/refs/heads/main` |
| `api.github.com` contents | 单文件下载，**本机实测最稳**（`raw.githubusercontent.com` 直连可能 http=000） |

⚠ 完整解压后约 **150 MB**。两个大 CSV 各 65 MB+，用 pandas 读入时：
`usecols` 选列、`chunksize` 分块、`dtype` 显式指定（`orderID` / `execID` 是长字符串）。

---

## 六、校验清单（动数据前逐条打勾）

- [ ] `verify_archive.py` 退出码为 `0`
- [ ] 无 `missing`（除刻意不下载的大文件）
- [ ] `execution` 行数 − `tradeHistory` 行数 **= 15**
- [ ] `execType` 分布与 manifest 一致（Trade 160,642 / Funding 12,916 / Settlement 19 / New 8 / Replaced 6 / Triggered 1）
- [ ] 钱包累计出入金与 `equity_curve_summary` 对上
- [ ] `adjustedWealthXBT` 终值与 manifest 对上
- [ ] `position.snapshot` 为 0 行（这是正常状态，不是缺失）
- [ ] 已读 `coverage-limits.md`，确认本次问题在数据能回答的范围内
- [ ] 已知悉：撤单率 / 拒单率 / 订单存活时长 / 完整 NAV **无法从本数据得出**
