# -*- coding: utf-8 -*-
"""用真实的 3D 力导向给 8631 个文件算一套球状坐标（离线，跑一次存下来）。

为什么不用 2D 布局当第三维：2D 那张图是「领域岛」，横竖都是排出来的；
力导向 3D 的好处是**没有任何一维被指定含义**，它只回答「谁和谁近」，
正好和「地层」（depth 是有含义的）形成两种互补的观察方式。
"""
import os
import sys
from collections import Counter

import networkx as nx
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
MAP = r"C:\Users\22771\Documents\deepseek-harness\default-workspace\research\mathlib-map"


def main():
    G = nx.Graph()
    with open(os.path.join(MAP, "nodes.tsv"), encoding="utf-8") as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            if p:
                G.add_node(p[0])
    with open(os.path.join(MAP, "edges.tsv"), encoding="utf-8") as f:
        f.readline()
        for line in f:
            a, b = line.rstrip("\n").split("\t")[:2]
            G.add_edge(a, b)
    print("图：%d 节点 / %d 边" % (G.number_of_nodes(), G.number_of_edges()))

    comps = sorted(nx.connected_components(G), key=len, reverse=True)
    print("连通分量 %d 个，最大 %d 个节点" % (len(comps), len(comps[0])))
    gc = G.subgraph(comps[0])

    print("算 3D 力导向（iterations=150, seed=11）…", flush=True)
    pos = nx.spring_layout(gc, dim=3, seed=11, iterations=150, threshold=1e-4)

    # 孤立节点（不在最大分量里）撒在远处的小球里，别让它们飞走
    rng = np.random.default_rng(11)
    other = [n for n in G if n not in pos]
    for n in other:
        v = rng.normal(size=3)
        pos[n] = (v / np.linalg.norm(v)) * 3.0

    P = np.array([pos[n] for n in G.nodes()], dtype=float)
    P -= P.mean(axis=0)
    P /= np.abs(P).max()
    P *= 100.0

    out = os.path.join(BASE, "pos3d_force.tsv")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("module\tx\ty\tz\n")
        for i, n in enumerate(G.nodes()):
            f.write("%s\t%.4f\t%.4f\t%.4f\n" % (n, P[i, 0], P[i, 1], P[i, 2]))
    print("写出 %s" % out)

    # 顺手看一眼力导向有没有把领域分开（同一领域的节点是否比随机更近）
    area = {}
    with open(os.path.join(MAP, "nodes.tsv"), encoding="utf-8") as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            if p:
                area[p[0]] = p[1]
    idx = {n: i for i, n in enumerate(G.nodes())}
    cnt = Counter()
    rng2 = np.random.default_rng(3)
    names = list(G.nodes())
    for _ in range(20000):
        a, b = rng2.integers(0, len(names), 2)
        cnt["随机"] += 1 if area[names[a]] == area[names[b]] else 0
        cnt["邻接"] += 1
    same_edge = sum(1 for u, v in G.edges() if area[u] == area[v])
    print("同领域比例：随机配 %.1f%% / 真实边 %.1f%%" % (
        100 * cnt["随机"] / cnt["邻接"], 100 * same_edge / G.number_of_edges()))


if __name__ == "__main__":
    main()
