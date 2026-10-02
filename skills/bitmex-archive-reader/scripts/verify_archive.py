#!/usr/bin/env python3
"""校验 BitMEX 公开交易档案的本地副本是否与 manifest 一致。

用途
----
下载之后、动数据之前，先证明你手上的副本没有被截断、替换或损坏。

用法
----
    python verify_archive.py <档案目录>                  # 校验全部文件
    python verify_archive.py <档案目录> --skip-large     # 跳过 >5 MB 的两个主表
    python verify_archive.py <档案目录> --json           # 机器可读输出
    python verify_archive.py <档案目录> --no-hash        # 只比对大小与行数（快，但不验完整性）

退出码
------
    0  全部通过（或 --no-hash 下全部匹配）
    1  发现不一致
    2  用法错误 / 找不到 manifest.json

设计约束
--------
只读脚本。只读 manifest.json 与被校验目录内的文件，不写任何东西、不联网。
大文件默认参与校验但会消耗时间；--skip-large 用于快速自检。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

LARGE_THRESHOLD = 5 * 1024 * 1024
CHUNK = 1024 * 1024


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n} B"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def count_rows(path: Path) -> int | None:
    """二进制数换行，避开 csv 模块的编码/引号开销。"""
    if path.suffix.lower() != ".csv":
        return None
    rows = 0
    last = b"\n"
    with path.open("rb") as fh:
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            rows += block.count(b"\n")
            last = block[-1:]
    if last not in (b"\n", b""):
        rows += 1  # 末行无换行
    return max(rows - 1, 0)  # 减去表头


def main() -> int:
    ap = argparse.ArgumentParser(
        description="校验 BitMEX 公开交易档案副本与 manifest 的一致性")
    ap.add_argument("root", help="档案目录（含 manifest.json）")
    ap.add_argument("--skip-large", action="store_true",
                    help=f"跳过大于 {human(LARGE_THRESHOLD)} 的文件")
    ap.add_argument("--no-hash", action="store_true",
                    help="只比对字节数与行数，不计算 sha256（快但不验完整性）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    mpath = root / "manifest.json"

    if not mpath.is_file():
        print(f"[FAIL] 找不到 manifest.json: {mpath}", file=sys.stderr)
        return 2

    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] manifest.json 解析失败: {exc}", file=sys.stderr)
        return 2

    entries = manifest.get("files") or []
    if not entries:
        print("[FAIL] manifest.json 里没有 files 数组", file=sys.stderr)
        return 2

    results = []
    n_ok = n_bad = n_skip = n_missing = 0

    for e in entries:
        name = e.get("file")
        if not name:
            continue
        exp_size = e.get("size_bytes")
        exp_sha = (e.get("sha256") or "").lower()
        exp_rows = e.get("rows")
        path = root / name

        rec = {
            "file": name,
            "expected_bytes": exp_size,
            "expected_rows": exp_rows,
            "expected_sha256": exp_sha or None,
            "status": "unknown",
        }

        if not path.is_file():
            rec["status"] = "missing"
            n_missing += 1
            results.append(rec)
            continue

        actual_size = path.stat().st_size
        rec["actual_bytes"] = actual_size

        if args.skip_large and actual_size > LARGE_THRESHOLD:
            rec["status"] = "skipped_large"
            n_skip += 1
            results.append(rec)
            continue

        if actual_size != exp_size:
            rec["status"] = "size_mismatch"
            rec["actual_sha256"] = None
            n_bad += 1
            results.append(rec)
            continue

        if not args.no_hash and exp_sha:
            actual_sha = sha256_of(path)
            rec["actual_sha256"] = actual_sha
            if actual_sha != exp_sha:
                rec["status"] = "sha256_mismatch"
                n_bad += 1
                results.append(rec)
                continue

        if isinstance(exp_rows, int):
            actual_rows = count_rows(path)
            rec["actual_rows"] = actual_rows
            if actual_rows is not None and actual_rows != exp_rows:
                rec["status"] = "rows_mismatch"
                n_bad += 1
                results.append(rec)
                continue

        rec["status"] = "ok"
        n_ok += 1
        results.append(rec)

    # 额外提示：终端快照为 0 行是正常的（导出时无未平仓）
    pos = next((r for r in results if "position.snapshot" in r["file"]), None)
    zero_row_ok = pos is not None and pos.get("expected_rows") == 0

    summary = {
        "manifest_version": manifest.get("spec_version"),
        "release_status": manifest.get("release_status"),
        "generated_at": manifest.get("generated_at"),
        "ledger_cutoff_utc": (manifest.get("source_export") or {}).get("ledger_cutoff_utc"),
        "window": manifest.get("dataset_window"),
        "files_declared": len(entries),
        "ok": n_ok,
        "mismatch": n_bad,
        "missing": n_missing,
        "skipped": n_skip,
        "hashed": not args.no_hash,
        "results": results,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        w = summary["window"] or {}
        print("BitMEX 档案副本校验")
        print("=" * 78)
        print(f"  manifest spec   : {summary['manifest_version']}  "
              f"({summary['release_status']}, generated {summary['generated_at']})")
        print(f"  账本截止         : {summary['ledger_cutoff_utc']}")
        print(f"  数据窗口         : {w.get('first_time')} → {w.get('last_time')}")
        print(f"  声明文件数       : {summary['files_declared']}")
        print(f"  哈希校验         : {'是' if summary['hashed'] else '否（--no-hash）'}")
        print("-" * 78)
        print(f"{'文件':<44}{'状态':<18}{'实测/期望 字节'}")
        print("-" * 78)
        for r in results:
            a = r.get("actual_bytes")
            e = r.get("expected_bytes")
            size = f"{a:,}/{e:,}" if isinstance(a, int) and isinstance(e, int) else "-"
            mark = {"ok": "OK", "missing": "缺失", "size_mismatch": "大小不符",
                    "sha256_mismatch": "HASH 不符", "rows_mismatch": "行数不符",
                    "skipped_large": "跳过(大文件)"}.get(r["status"], r["status"])
            print(f"{r['file'][:43]:<44}{mark:<18}{size}")
        print("-" * 78)
        print(f"通过 {n_ok} ｜ 不一致 {n_bad} ｜ 缺失 {n_missing} ｜ 跳过 {n_skip}")
        if zero_row_ok:
            print("提示: position.snapshot 期望 0 行（导出时无未平仓）—— 这是正常的。")
        if n_bad or n_missing:
            print("\n结论: 副本与 manifest 不一致，先解决再动数据。")
        elif n_skip:
            print("\n结论: 已校验部分全部一致（大文件被跳过，如需完整校验去掉 --skip-large）。")
        else:
            print("\n结论: 全部一致。")

    return 1 if (n_bad or n_missing) else 0


if __name__ == "__main__":
    sys.exit(main())
