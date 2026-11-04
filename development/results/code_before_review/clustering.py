from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


# ==========================================
# 1. 경로 설정
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RESULT_DIR = BASE_DIR / "results"

RESULT_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================
# 2. 머신러닝 데이터 불러오기
# ==========================================

data_path = DATA_DIR / "ml_features.csv"

if not data_path.exists():
    raise FileNotFoundError(
        "ml_features.csv가 없습니다. "
        "data_preprocessing.py를 먼저 실행하세요."
    )

df = pd.read_csv(data_path, encoding="utf-8-sig")

print("전체 행정동 수:", len(df))


# ==========================================
# 3. 머신러닝 특징 선택
# ==========================================

ratio_columns = [
    col for col in df.columns
    if col.endswith("_비율")
]

# 상권 규모와 업종 다양성도 반영
df["로그상가수"] = np.log1p(df["전체상가수"])

feature_columns = (
    ratio_columns
    + ["로그상가수", "업종다양성"]
)

X = df[feature_columns].copy()

print("\n사용할 특징:")
print(feature_columns)


# ==========================================
# 4. 데이터 표준화
# ==========================================

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

print("\n데이터 표준화 완료")


# ==========================================
# 5. 적절한 군집 개수 탐색
# ==========================================

k_values = range(2, 9)
silhouette_scores = []

for k in k_values:
    model = KMeans(
        n_clusters=k,
        random_state=42,
        n_init=20
    )

    labels = model.fit_predict(X_scaled)

    score = silhouette_score(
        X_scaled,
        labels
    )

    silhouette_scores.append(score)

    print(f"K={k}, 실루엣 점수={score:.4f}")


# ==========================================
# 6. 최적 K 선택
# ==========================================

best_index = int(np.argmax(silhouette_scores))
best_k = list(k_values)[best_index]

print("\n최적 군집 개수:", best_k)


# ==========================================
# 7. 최종 K-means 모델
# ==========================================

final_model = KMeans(
    n_clusters=best_k,
    random_state=42,
    n_init=20
)

df["군집"] = final_model.fit_predict(X_scaled)

print("\n군집별 행정동 수:")
print(df["군집"].value_counts().sort_index())


# ==========================================
# 8. 군집별 특징 분석
# ==========================================

cluster_summary = (
    df.groupby("군집")[
        ["전체상가수", "업종다양성"]
        + ratio_columns
    ]
    .mean()
    .round(4)
)

print("\n========== 군집별 평균 특징 ==========")
print(cluster_summary)


# ==========================================
# 9. PCA 2차원 시각화
# ==========================================

pca = PCA(n_components=2)
X_pca = pca.fit_transform(X_scaled)

df["PCA1"] = X_pca[:, 0]
df["PCA2"] = X_pca[:, 1]

plt.figure(figsize=(10, 7))

scatter = plt.scatter(
    df["PCA1"],
    df["PCA2"],
    c=df["군집"],
    cmap="tab10",
    s=65,
    alpha=0.8
)

plt.xlabel("PCA 1")
plt.ylabel("PCA 2")
plt.title("Daejeon Commercial District Clustering")

plt.colorbar(scatter, label="Cluster")

plt.tight_layout()

plt.savefig(
    RESULT_DIR / "cluster_pca.png",
    dpi=200
)

plt.close()


# ==========================================
# 10. 실루엣 점수 그래프
# ==========================================

plt.figure(figsize=(9, 5))

plt.plot(
    list(k_values),
    silhouette_scores,
    marker="o"
)

plt.xlabel("Number of Clusters (K)")
plt.ylabel("Silhouette Score")
plt.title("K-means Silhouette Analysis")

plt.xticks(list(k_values))
plt.grid(alpha=0.3)

plt.tight_layout()

plt.savefig(
    RESULT_DIR / "silhouette_scores.png",
    dpi=200
)

plt.close()


# ==========================================
# 11. 결과 저장
# ==========================================

df.to_csv(
    RESULT_DIR / "clustered_dongs.csv",
    index=False,
    encoding="utf-8-sig"
)

cluster_summary.to_csv(
    RESULT_DIR / "cluster_summary.csv",
    encoding="utf-8-sig"
)

pd.DataFrame({
    "K": list(k_values),
    "silhouette_score": silhouette_scores
}).to_csv(
    RESULT_DIR / "silhouette_scores.csv",
    index=False,
    encoding="utf-8-sig"
)


# ==========================================
# 12. 완료
# ==========================================

print("\n======================================")
print("K-means 군집화 완료!")
print("======================================")

print("\n최적 K:", best_k)

print("\n생성된 파일:")
print("results/clustered_dongs.csv")
print("results/cluster_summary.csv")
print("results/silhouette_scores.csv")
print("results/cluster_pca.png")
print("results/silhouette_scores.png")