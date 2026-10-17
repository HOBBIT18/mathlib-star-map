# -*- coding: utf-8 -*-
"""把 Mathlib 的依赖图压成一个能被浏览器直接 <script> 加载的 data.js。

产出：research\mathlib-3d\data.js  →  window.MLDATA = {...}

关键点：
- **sky（头顶压着多少个文件）用位掩码算**。朴素做法是 8631 次 BFS，太慢；
  位掩码一次拓扑推进就够，8631 个 bit ≈ 1 KB/节点，总共不到 10 MB。
- 两套坐标：`cone`（y = 依赖层数，有含义）与 `ball`（3D 力导向，无机含义）。
- **不发 259,059 个点**。只发每个文件的声明数与坐标，浏览器里用确定性抖动展开——
  省下十几 MB 传输，效果一样。
"""
import json
import os
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
MAP = r"C:\Users\22771\Documents\deepseek-harness\default-workspace\research\mathlib-map"


def read_tsv(path):
    with open(path, encoding="utf-8") as f:
        cols = f.readline().rstrip("\n").split("\t")
        return [dict(zip(cols, line.rstrip("\n").split("\t")))
                for line in f if line.strip()]


def main():
    nodes = read_tsv(os.path.join(MAP, "nodes.tsv"))
    edges = read_tsv(os.path.join(MAP, "edges.tsv"))
    depth = {r["module"]: int(r["depth"]) for r in read_tsv(os.path.join(MAP, "depth.tsv"))}
    ground = {r["module"]: int(r["ground"]) for r in read_tsv(os.path.join(MAP, "depth.tsv"))}
    lay = {r["module"]: (float(r["x"]), float(r["y"]))
           for r in read_tsv(os.path.join(MAP, "layout.tsv"))}
    births = sorted({r["birth"] for r in read_tsv(os.path.join(MAP, "birth.tsv"))})
    bidx = {b: i for i, b in enumerate(births)}
    birth = {r["module"]: bidx[r["birth"]] for r in read_tsv(os.path.join(MAP, "birth.tsv"))}

    mods = [r["module"] for r in nodes]
    idx = {m: i for i, m in enumerate(mods)}
    n = len(mods)
    areas = sorted({r["area"] for r in nodes})
    aidx = {a: i for i, a in enumerate(areas)}

    print("文件 %d / 领域 %d / 边 %d" % (n, len(areas), len(edges)))

    # ---------- 度 ----------
    # 去重：edges.tsv 里有 74 条完全重复的 (src,dst)（同一对文件被 import 语句写了两遍），
    # 不去重会让 indeg 与实际「有多少个文件依赖它」不符。
    indeg = Counter()
    outdeg = Counter()
    rev = defaultdict(list)
    fwd = defaultdict(list)
    E = []
    seen_e = set()
    skipped_self = 0
    for e in edges:
        a, b = e["src"], e["dst"]
        if a not in idx or b not in idx:
            continue
        ia, ib = idx[a], idx[b]
        if ia == ib:
            skipped_self += 1
            continue
        if (ia, ib) in seen_e:
            continue
        seen_e.add((ia, ib))
        E.append((ia, ib))
        outdeg[a] += 1
        indeg[b] += 1
        rev[b].append(a)
        fwd[a].append(b)
    print("去重后边 %d（丢掉重复 %d / 自环 %d）" % (
        len(E), len(edges) - len(E) - skipped_self, skipped_self))

    # ---------- sky：头顶压着多少个文件（位掩码）----------
    print("算 sky（位掩码，%d 位/节点）…" % n, flush=True)
    memo = {}
    order = sorted(mods, key=lambda m: -depth.get(m, 0))
    for start in order:
        if start in memo:
            continue
        stack = [start]
        onstack = {start}          # 环保护：import 图是 DAG，但真出现环也不能卡死
        while stack:
            cur = stack[-1]
            if cur in memo:
                stack.pop(); onstack.discard(cur)
                continue
            pend = [m for m in rev[cur] if m not in memo and m not in onstack]
            if pend:
                stack.extend(pend); onstack.update(pend)
                continue
            b = 0
            for m in rev[cur]:
                if m == cur or m in onstack:   # 自环或回边——跳过
                    continue
                b |= memo[m] | (1 << idx[m])
            memo[cur] = b
            stack.pop(); onstack.discard(cur)
    sky = {m: bin(memo[m]).count("1") for m in mods}
    print("sky 中位 %d / 最大 %d（%s）" % (
        sorted(sky.values())[n // 2], max(sky.values()),
        max(sky, key=sky.get)))

    # ---------- 坐标 ----------
    xs = [lay[m][0] for m in mods if m in lay]
    ys = [lay[m][1] for m in mods if m in lay]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    sc = 180.0 / max(max(xs) - min(xs), max(ys) - min(ys))
    D = max(depth.values()) or 1

    cone = []
    for m in mods:
        x, y = lay.get(m, (0.0, 0.0))
        cone += [round((x - cx) * sc, 2), round(depth.get(m, 0) / D * 200.0 - 100.0, 2),
                 round((y - cy) * sc, 2)]

    ball = None
    fp = os.path.join(BASE, "pos3d_force.tsv")
    if os.path.exists(fp):
        f3 = {r["module"]: (float(r["x"]), float(r["y"]), float(r["z"]))
              for r in read_tsv(fp)}
        # 力导向的体量都挤在中心，外围只有几个离群点（1% 分位 ±17，最大 +100）。
        # 先按 1/99 分位夹紧、按中位居中，再统一缩放到「98% 的点落在半径 95 内」，
        # 否则球状模式下整张图只有屏幕中间一小坨。
        raw = [list(f3.get(m, (0.0, 0.0, 0.0))) for m in mods]
        for k in range(3):
            col = sorted(v[k] for v in raw)
            lo, hi = col[len(col) // 100], col[-1 - len(col) // 100]
            for v in raw:
                v[k] = min(max(v[k], lo), hi)
        for k in range(3):
            col = sorted(v[k] for v in raw)
            med = col[len(col) // 2]
            for v in raw:
                v[k] -= med
        import math as _m
        rad = sorted(_m.sqrt(sum(v[k] * v[k] for k in range(3))) for v in raw)
        s = 95.0 / max(rad[int(0.98 * len(rad))], 1e-9)
        ball = []
        for v in raw:
            ball += [round(max(-108.0, min(108.0, v[k] * s)), 2) for k in range(3)]
        print("球状坐标已并入（%d 个，缩放 ×%.2f，半径 98%% 分位 %.1f）"
              % (len(f3), s, rad[int(0.98 * len(rad))]))

    data = {
        "n": n,
        "areas": areas,
        "modules": mods,
        "area": [aidx[r["area"]] for r in nodes],
        "decls": [int(r["decls"]) for r in nodes],
        "lines": [int(r["lines"]) for r in nodes],
        "depth": [depth.get(m, 0) for m in mods],
        "ground": [ground.get(m, 0) for m in mods],
        "sky": [sky[m] for m in mods],
        "indeg": [indeg[m] for m in mods],
        "outdeg": [outdeg[m] for m in mods],
        "birth": [birth.get(m, -1) for m in mods],
        "births": births,
        "cone": cone,
        "ball": ball,
        "edges": [v for pair in E for v in pair],
        "maxDepth": D,
        "stats": {
            "decls_total": sum(int(r["decls"]) for r in nodes),
            "edges_total": len(E),
            "areas_total": len(areas),
            "area_files": Counter(r["area"] for r in nodes).most_common(),
        },
    }
    out = os.path.join(BASE, "data.js")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("// 由 build_demo_data.py 生成，不要手改。\n")
        f.write("window.MLDATA = ")
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    print("写出 %s（%.2f MB）" % (out, os.path.getsize(out) / 1e6))
    print("声明总数 %d / 边 %d" % (data["stats"]["decls_total"], len(E)))
    print("前 6 个被依赖最多的：")
    for m in sorted(mods, key=lambda m: -sky[m])[:6]:
        print("   sky %5d  indeg %4d  depth %3d  %s" % (
            sky[m], indeg[m], depth.get(m, 0), m))


if __name__ == "__main__":
    main()
