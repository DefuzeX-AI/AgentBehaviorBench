#!/usr/bin/env python3
"""\u6e05\u7406\u5404\u4efb\u52a1\u4e0a\u62a5/\u56de\u4f20\u7684\u7167\u7247 (uploads \u53ca results \u4e0b\u7684\u56fe\u7247), \u53ea\u5220\u56fe\u7247, \u4fdd\u7559 JSON \u8bb0\u5f55\u4e0e\u65e5\u5fd7\u3002

\u5f15\u64ce\u56de\u4f20\u7684\u7167\u7247\u4ec5\u5728\u8bc6\u56fe\u90a3\u4e00\u523b\u6709\u7528, \u4e4b\u540e\u5c31\u662f\u6b7b\u91cd\u91cf (\u5355\u6b21\u5b9e\u9a8c\u53ef\u79ef\u7d2f\u4e0a\u5343\u5f20\u3001GB \u7ea7)\u3002\u672c\u811a\u672c:
  - \u53ea\u5220\u56fe\u7247\u6269\u5c55\u540d (.jpg/.jpeg/.png/.bmp/.webp);
  - Only removes matching files below `uploads/` and `results/` in examples/.
  - \u9ed8\u8ba4\u53ea\u5220 **\u4fee\u6539\u65f6\u95f4\u65e9\u4e8e --older-than-min \u5206\u949f** \u7684, \u907f\u514d\u5220\u6389\u6b63\u5728\u8bc6\u56fe\u7684\u5728\u9014\u7167\u7247;
  - \u7edd\u4e0d\u78b0 .json / .log / .jsonl / .txt / \u4ee3\u7801\u3002

\u7528\u6cd5:
  python scripts/cleanup_task_photos.py --dry-run           # \u53ea\u62a5\u544a, \u4e0d\u5220
  python scripts/cleanup_task_photos.py                     # \u5220 60 \u5206\u949f\u524d\u7684\u56fe\u7247
  python scripts/cleanup_task_photos.py --older-than-min 0  # \u5220\u5168\u90e8\u56fe\u7247 (\u542b\u521a\u4e0a\u4f20\u7684)
"""
import argparse
import os
import time
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SCAN_DIR_NAMES = {"uploads", "results"}
REPO_ROOT = Path(__file__).resolve().parent.parent
TASK_ROOTS = [REPO_ROOT / "examples"]


def iter_photo_files(older_than_sec: float):
    cutoff = time.time() - older_than_sec
    for base in TASK_ROOTS:
        if not base.is_dir():
            continue
        
        for task_dir in base.iterdir():
            if not task_dir.is_dir():
                continue
            for sub in SCAN_DIR_NAMES:
                d = task_dir / sub
                if not d.is_dir():
                    continue
                for path in d.rglob("*"):
                    if path.suffix.lower() not in IMAGE_SUFFIXES or not path.is_file():
                        continue
                    try:
                        if path.stat().st_mtime <= cutoff:
                            yield path
                    except OSError:
                        continue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--older-than-min", type=float, default=60.0,
                    help="\u53ea\u5220\u4fee\u6539\u65f6\u95f4\u65e9\u4e8e\u8be5\u5206\u949f\u6570\u7684\u56fe\u7247 (\u9ed8\u8ba460; \u8bbe0\u5220\u5168\u90e8)")
    ap.add_argument("--dry-run", action="store_true", help="\u53ea\u62a5\u544a\u4e0d\u5220\u9664")
    args = ap.parse_args()

    older_than_sec = max(0.0, args.older_than_min) * 60.0
    n = 0
    freed = 0
    for path in iter_photo_files(older_than_sec):
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if args.dry_run:
            n += 1
            freed += size
            continue
        try:
            path.unlink()
            n += 1
            freed += size
        except OSError as exc:
            print(f"[\u6e05\u7406] \u5220\u9664\u5931\u8d25 {path}: {exc}", flush=True)

    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    verb = "\u5f85\u5220" if args.dry_run else "\u5df2\u5220"
    print(f"[\u6e05\u7406] {stamp}  {verb}\u7167\u7247 {n} \u5f20, \u91ca\u653e {freed / 1048576:.1f} MB "
          f"(\u9608\u503c: \u65e9\u4e8e {args.older_than_min:.0f} \u5206\u949f; \u53ea\u5220 uploads/ \u4e0e results/ \u4e0b\u56fe\u7247, \u4fdd\u7559 JSON/\u65e5\u5fd7)",
          flush=True)


if __name__ == "__main__":
    main()
