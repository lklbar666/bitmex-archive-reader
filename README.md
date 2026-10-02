# bitmex-archive-reader

**读 `bwjoke/BTC-Trading-Since-2020` 这份公开 BitMEX 交易档案时，先知道它答不了什么。**

那是一个真实账户（`@coolish`）从 2020-05-01 到 2026-07-23 的完整账本镜像：43,258 张订单、173,577 条成交、17,620 条钱包事件。它最罕见的不是 54 倍收益，而是**在结果揭晓之前就已公开的轨迹**。

但这份数据有几个坑，踩中任何一条，算出来的数就是错的。本仓库把坑写成规则。

| 文件 | 字节 | 作用 |
|---|---|---|
| `LICENSE` | 1,065 | MIT (c) 2026 lklbar666 |
| `README.md` | 本文件 | — |
| `skills/bitmex-archive-reader/SKILL.md` | 7,689 | **八条硬规则** + 6 步工作流 + 主表选择表 |
| `skills/bitmex-archive-reader/references/file-map.md` | 4,550 | 11 个 CSV 逐个：主键 / 列数 / 时间范围 + 三个时序陷阱 |
| `skills/bitmex-archive-reader/references/field-semantics.md` | 6,585 | `execType` / `ordStatus` / `transactType` 语义、单位换算、两个财富口径 |
| `skills/bitmex-archive-reader/references/join-and-dedup.md` | 6,859 | 去重 / left join / scale 换算 / 划转中性化 / 复算骨架 |
| `skills/bitmex-archive-reader/references/coverage-limits.md` | 5,628 | **动数据前必读** —— 这份数据不能回答什么 |
| `skills/bitmex-archive-reader/references/verification.md` | 6,606 | sha256 校验 + 内部一致性对账 + 9 项打勾清单 |
| `skills/bitmex-archive-reader/scripts/verify_archive.py` | 7,912 | 只读校验器：sha256 / 字节数 / 行数三档核对 |

---

## 安装

把 `skills/bitmex-archive-reader/` 整个目录放进你的技能目录：

```
skills/bitmex-archive-reader/
├── SKILL.md
├── references/  (5 份)
└── scripts/verify_archive.py
```

WorkBuddy 用户放 `C:\Users\<你>\.workbuddy\skills\`；Claude Code 放 `~/.claude/skills/`。

**本仓库不含数据。** 技能是规范，数据要自己去取。

---

## 八条硬规则（摘要）

1. **主余额账本是 `tradeHistory`**，`execution` 是事件流
2. ⚠️ **两表重叠，禁止直接 `concat`** —— 行数差 15 就是重叠部分，必须按 `execID` 去重
3. ⚠️ **缺失事件 ≠ 该操作没发生** —— `Canceled` / `Rejected` 返回 **0 条**，撤单率这类指标**算不出来**
4. `order.csv` 是**终态**快照，不是状态转移日志
5. join 用 `orderID`，定位单条成交用 `execID`，**必须 left join 保留未匹配行**
6. ⚠️ 金额是**各自最小单位**（XBt 是 satoshi），**查 `wallet-assets.csv` 的 `scale`，别硬编码 1e8**
7. ⚠️ 三个快照是**顺序读取非原子**，跨表时间错位最大 3h48m
8. ⚠️ `adjustedWealthXBT`（钱包等价）与 `adjustedMarkedWealthXBT`（标记市值）**不可混用**，后者本 build 未计算

细则与可运行的 pandas 骨架见 `references/`。

---

## 数据从哪来

```bash
# 仓库（约 150 MB 原始 CSV）
https://github.com/bwjoke/BTC-Trading-Since-2020
# Releases 页有单次下载的 zip / tar.gz，比 clone 省流量
```

数据窗口 **2020-05-01 → 2026-07-23**（账本最后事件），导出 2026-09-11，
`release_status: final_snapshot` —— **上游已声明不再更新**。

---

## 校验（动数据前必做）

```bash
python scripts/verify_archive.py <档案目录>
```

按 `manifest.json` 逐文件核对 sha256、字节数、行数。退出码 `0` 全部通过。

| 参数 | 用途 |
|---|---|
| `--skip-large` | 跳过 >5 MB 的文件（几秒出结果） |
| `--no-hash` | 只比对行数与字节数（更快，**但不验完整性**） |
| `--json` | 机器可读输出 |

2026-10-02 实测：7 个小文件 sha256 与 manifest **逐字节一致**；两个大 CSV 未下载。

---

## 版权与来源声明

- **数据**：`bwjoke/BTC-Trading-Since-2020`。该仓库**无 LICENSE 文件**（GitHub API `license: null`），即默认保留所有权利。本仓库**只提供解读规范，不包含、不再分发任何数据文件**。
- **本仓库内容**：引用的是 BitMEX API 的字段名（事实性标识符）与 `manifest.json` 中的统计值（可校验的客观数字），**不复制上游 README 正文**。八条规则与五份参考文档为独立撰写。
- **BitMEX API**：<https://docs.bitmex.com/api-explorer/bitmex-api.html>
- 上游作者已声明这份档案关乎「**不确定下的决策质量**」而非价格预测能力，并承认任何长期结果都包含时机与运气。**本仓库的结论同样只适用于 n = 1。**
