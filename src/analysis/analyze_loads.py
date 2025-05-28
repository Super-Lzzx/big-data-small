#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_loads.py —— 完整版，包含箱线图、PCA 可视化、主成分公式输出与分类验证，
并将图覆盖式保存到已有的 results/monitor 目录。
"""

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.font_manager import FontProperties
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.decomposition import PCA
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix

# 1. 中文字体（请确认路径下有该字体文件）
zh_font = FontProperties(fname="/usr/share/fonts/truetype/arphic/ukai.ttc", size=12)

# 2. 项目根目录 & 数据文件
# __file__ 位于 src/analysis/analyze_loads.py，项目根目录在三层上
PROJECT_ROOT = Path(__file__).parents[2].resolve()
csv_path    = PROJECT_ROOT / "data" / "processed" / "full_dataset.csv"
print(f"正在加载数据：{csv_path}")

df = pd.read_csv(csv_path)
print("检测到列：", df.columns.tolist())

# 3. 定义特征 & 标签列
features = [
    "cpu_cycles","instructions","cache_misses","branch_instrs","branch_misses",
    "L1_icache_miss","L1_dcache_miss","ITLB_misses","L2_cache_miss","DTLB_misses"
]
label = "LoadType"

# 4. 使用已有的保存目录（无需创建）
out_dir = PROJECT_ROOT / "results" / "monitor"

# 5. 箱线图（每类随机抽样不超过1000条）
cn_names = {
    "cpu_cycles":      "CPU 周期",
    "instructions":    "指令数",
    "cache_misses":    "缓存未命中",
    "branch_instrs":   "分支指令",
    "branch_misses":   "分支未命中",
    "L1_icache_miss":  "L1 指令缓存未命中",
    "L1_dcache_miss":  "L1 数据缓存未命中",
    "ITLB_misses":     "iTLB 未命中",
    "L2_cache_miss":   "L2 缓存未命中",
    "DTLB_misses":     "dTLB 未命中"
}

plt.figure(figsize=(18, 14))
for idx, feat in enumerate(features, 1):
    ax = plt.subplot(4, 3, idx)
    sampled = df.groupby(label, group_keys=False).sample(n=1000, random_state=42)
    sns.boxplot(
        x=label, y=feat, hue=label, data=sampled,
        palette="Set2", dodge=False, ax=ax
    )
    ax.set_title(cn_names[feat], fontproperties=zh_font)
    ax.set_xlabel("")
    ax.set_ylabel(cn_names[feat], fontproperties=zh_font)
    ax.set_xticklabels(
        ax.get_xticklabels(),
        rotation=45, ha='right', fontproperties=zh_font
    )
    if ax.get_legend():
        ax.get_legend().remove()

plt.subplots_adjust(top=0.92, bottom=0.18, hspace=0.4, wspace=0.3)
fig1 = plt.gcf()
fig1.savefig(out_dir / "boxplots.png", dpi=300, bbox_inches="tight")
print("已保存箱线图到 results/monitor/boxplots.png")
plt.close(fig1)

# 6. PCA 降维 & 主成分载荷输出
X = df[features].values
le = LabelEncoder()
y = le.fit_transform(df[label])

X_scaled = StandardScaler().fit_transform(X)
pca = PCA(n_components=2)
X2 = pca.fit_transform(X_scaled)

loadings = pd.DataFrame(pca.components_.T, index=features, columns=["PC1", "PC2"])
print("主成分载荷（coefficients）：")
print(loadings.round(4), "\n")

for comp in ["PC1", "PC2"]:
    coefs = loadings[comp]
    terms = [f"{coefs[f]:+.4f}×{cn_names[f]}" for f in features]
    expr = "\n    ".join(terms)
    print(f"{comp} =\n    {expr}\n")

plt.figure(figsize=(8, 6))
sns.scatterplot(
    x=X2[:,0], y=X2[:,1],
    hue=df[label], palette="Set1", s=60, alpha=0.8
)
plt.title("PCA 2D 可视化：负载类型可区分性", fontproperties=zh_font, fontsize=16)
plt.xlabel("主成分 1", fontproperties=zh_font)
plt.ylabel("主成分 2", fontproperties=zh_font)
plt.legend(loc="best", title="负载类型", prop=zh_font)

fig2 = plt.gcf()
fig2.savefig(out_dir / "pca_scatter.png", dpi=300, bbox_inches="tight")
print("已保存 PCA 散点图到 results/monitor/pca_scatter.png")
plt.close(fig2)

# 7. 简单分类器验证
X_train, X_test, y_train, y_test = train_test_split(
    X_scaled, y, test_size=0.3, random_state=42, stratify=y
)
clf = LogisticRegression(max_iter=2000)
clf.fit(X_train, y_train)
y_pred = clf.predict(X_test)

print("=== 分类报告 ===")
print(classification_report(y_test, y_pred, target_names=le.classes_), "\n")

cm = confusion_matrix(y_test, y_pred)
plt.figure(figsize=(6, 5))
sns.heatmap(
    cm, annot=True, fmt="d", cmap="Blues",
    xticklabels=le.classes_, yticklabels=le.classes_
)
plt.title("混淆矩阵", fontproperties=zh_font, fontsize=16)
plt.xlabel("预测类别", fontproperties=zh_font)
plt.ylabel("真实类别", fontproperties=zh_font)

fig3 = plt.gcf()
fig3.savefig(out_dir / "confusion_matrix.png", dpi=300, bbox_inches="tight")
print("已保存混淆矩阵到 results/monitor/confusion_matrix.png")
plt.close(fig3)
