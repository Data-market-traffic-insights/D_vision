"""82개 대전 행정동 상권 군집화. 입력과 기존 결과를 덮어쓰지 않는다."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile
import unicodedata

os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'daejeon-mpl'))
# 작은 데이터에서는 작업자 1개면 충분하고 macOS 물리 코어 탐색도 피한다.
os.environ.setdefault('LOKY_MAX_CPU_COUNT', '1')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd
import sklearn
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_samples
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

BASE_DIR = Path(__file__).resolve().parent
KEYS = ['시군구명', '행정동명']
SEED, N_INIT, SIZE_WEIGHT = 42, 50, 0.2


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load_and_validate():
    path = BASE_DIR / 'data/ml_features.csv'
    df = pd.read_csv(path, encoding='utf-8-sig')
    ratios = [c for c in df if c.endswith('_비율')]
    require(len(df) == 82 and len(ratios) == 10, '82개 행정동/10개 업종인지 확인하세요.')
    require(not df[KEYS].isna().any().any() and not df.duplicated(KEYS).any(), '행정동 키 결측/중복')
    numeric = df[['전체상가수', '업종다양성'] + ratios].to_numpy(dtype=float)
    require(np.isfinite(numeric).all(), '입력 특징에 결측치 또는 무한대가 있습니다.')
    p = df[ratios].to_numpy()
    require(((p >= 0) & (p <= 1)).all(), '비율 범위 오류')
    require(np.allclose(p.sum(axis=1), 1, atol=1e-10, rtol=0), '비율 합 오류')
    require((df['전체상가수'] > 0).all(), '상가 수는 양수여야 합니다.')
    require((df[ratios].std() > 0).all(), '분산이 0인 업종이 있습니다.')
    entropy = -(p * np.log(np.clip(p, 1e-12, None))).sum(axis=1)
    require(np.allclose(entropy, df['업종다양성'], atol=1e-10, rtol=0), '다양성 재계산 불일치')
    clean_path = BASE_DIR / 'data/daejeon_clean.csv'
    clean = pd.read_csv(clean_path, encoding='utf-8-sig', low_memory=False)
    require(clean.shape == (79691, 39), '전처리 CSV 크기가 인수인계 내용과 다릅니다.')
    require(clean['시도명'].eq('대전광역시').all(), '대전 외 데이터가 있습니다.')
    require(clean['상가업소번호'].notna().all() and clean['상가업소번호'].is_unique, '상가 ID 결측/중복')
    code_map = clean[KEYS + ['행정동코드']].drop_duplicates()
    require(code_map['행정동코드'].notna().all(), '행정동 코드 결측')
    require(len(code_map) == 82 and code_map['행정동코드'].is_unique, '행정동 코드/명칭 대응 오류')
    counts = pd.crosstab([clean[k] for k in KEYS], clean['상권업종대분류명'])
    counts = counts.reindex(pd.MultiIndex.from_frame(df[KEYS]))
    industries = [c.removesuffix('_비율') for c in ratios]
    require(set(counts.columns) == set(industries), '업종 목록 불일치')
    require(np.array_equal(counts.sum(axis=1), df['전체상가수']), '행정동 상가 수 불일치')
    require(np.allclose(counts[industries].to_numpy() / df[['전체상가수']].to_numpy(), p,
                        atol=1e-10, rtol=0), '비율 재계산 불일치')
    sources = [f for f in BASE_DIR.parent.rglob('*.csv')
               if '상가' in unicodedata.normalize('NFC', f.name)
               and '대전' in unicodedata.normalize('NFC', f.name)]
    require(len(sources) == 1, '대전 원본 CSV를 하나로 특정할 수 없습니다.')
    raw = pd.read_csv(sources[0], encoding='utf-8-sig', low_memory=False)
    pd.testing.assert_frame_equal(raw, clean, check_dtype=False)
    for filename, keys in [('gu_counts.csv', ['시군구명']), ('dong_counts.csv', KEYS),
                           ('industry_counts.csv', ['상권업종대분류명'])]:
        saved = pd.read_csv(BASE_DIR / 'results' / filename).set_index(keys)['상가수'].sort_index()
        pd.testing.assert_series_equal(saved, clean.groupby(keys).size().sort_index(), check_names=False)
    saved = pd.read_csv(BASE_DIR / 'results/dong_industry.csv').set_index(KEYS)
    pd.testing.assert_frame_equal(saved[industries].sort_index(), counts[industries].sort_index(), check_names=False)
    require(np.array_equal(saved['전체상가수'], saved[industries].sum(axis=1)), '동별 집계 총계 오류')
    df = df.merge(code_map, on=KEYS, how='left', validate='one_to_one', sort=False)
    info = {'행정동수': len(df), '상가수': len(clean), '업종수': len(ratios),
            '비율합_최대오차': float(np.abs(p.sum(axis=1) - 1).max()),
            '원본과_전처리_일치': True, '기존요약CSV_일치': True,
            'source_sha256': {str(f.relative_to(BASE_DIR.parent)): sha256(f)
                              for f in [path, clean_path, sources[0]]}}
    return df, ratios, info


def transform(df, ratios, size_weight=SIZE_WEIGHT):
    rs = StandardScaler().fit(df[ratios])
    ss = StandardScaler().fit(np.log1p(df[['전체상가수']]))
    # 총분산: 업종 구성 0.8, 규모 0.2. 다양성은 중복 입력하지 않는다.
    x = np.column_stack([rs.transform(df[ratios]) * np.sqrt((1-size_weight)/len(ratios)),
                         ss.transform(np.log1p(df[['전체상가수']])) * np.sqrt(size_weight)])
    require(np.isfinite(x).all(), '변환 특징 오류')
    return x, rs, ss


def distances(x):
    # 현재 NumPy/BLAS 조합의 행렬곱 경고를 피하는 동일한 유클리드 거리 계산.
    d = np.sqrt(np.square(x[:, None, :] - x[None, :, :]).sum(axis=2))
    require(np.isfinite(d).all(), '거리 행렬 오류')
    return d


def fit(x, k, seed=SEED, n_init=N_INIT):
    return KMeans(n_clusters=k, random_state=seed, n_init=n_init).fit(x)


def compare(x):
    distance = distances(x)
    rows, models, samples, stability = [], {}, {}, []
    for k in range(2, 9):
        model = fit(x, k)
        models[k] = model
        s = silhouette_samples(distance, model.labels_, metric='precomputed')
        samples[k] = s
        sizes = np.bincount(model.labels_, minlength=k)
        aris = []
        for seed in range(10):
            ari = adjusted_rand_score(model.labels_, fit(x, k, seed).labels_)
            aris.append(ari)
            stability.append({'K': k, 'seed': seed, 'ARI_vs_seed42': ari})
        rows.append({'K': k, 'silhouette_score': float(s.mean()),
                     'min_cluster_size': int(sizes.min()), 'max_cluster_size': int(sizes.max()),
                     'cluster_sizes': json.dumps(sizes.tolist()),
                     'negative_silhouette_count': int((s < 0).sum()), 'inertia': model.inertia_,
                     'seed_ARI_mean': float(np.mean(aris)), 'seed_ARI_min': float(np.min(aris))})
    return pd.DataFrame(rows), models, samples, pd.DataFrame(stability)


def save_csv(df, output, filename):
    df.to_csv(output / filename, index=False, encoding='utf-8-sig')


def plot_results(df, scores, summary, ratios, pca, output, selected_k):
    fonts = {f.name for f in font_manager.fontManager.ttflist}
    korean = next((f for f in ['AppleGothic', 'NanumGothic', 'Malgun Gothic'] if f in fonts), None)
    if korean:
        plt.rcParams['font.family'] = korean
    plt.rcParams['axes.unicode_minus'] = False
    fig, ax = plt.subplots(figsize=(10, 7))
    for label, group in df.groupby('군집'):
        ax.scatter(group.PCA1, group.PCA2, s=55, alpha=.8, label=f'Cluster {label} (n={len(group)})')
    ax.set(xlabel=f'PC1 ({pca.explained_variance_ratio_[0]:.1%})',
           ylabel=f'PC2 ({pca.explained_variance_ratio_[1]:.1%})',
           title=f'Daejeon commercial districts | K={selected_k}')
    ax.legend()
    ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(output / 'cluster_pca.png', dpi=200)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(scores.K, scores.silhouette_score, marker='o')
    ax.axvline(selected_k, color='tab:orange', linestyle='--', label=f'Selected K={selected_k}')
    ax.set(xlabel='Number of clusters (K)', ylabel='Mean silhouette',
           title='Silhouette comparison | composition 80%, size 20%', xticks=scores.K)
    ax.legend()
    ax.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(output / 'silhouette_scores.png', dpi=200)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(12, 4.5))
    values = summary[ratios].to_numpy() * 100
    im = ax.imshow(values, cmap='YlGnBu', aspect='auto')
    labels = [c.removesuffix('_비율') for c in ratios] if korean else [f'Industry {i+1}' for i in range(10)]
    ax.set_xticks(range(10), labels, rotation=30, ha='right')
    ax.set_yticks(range(len(summary)), [f'Cluster {c}' for c in summary['군집']])
    ax.set_title('Mean industry share by district (%)')
    for i in range(values.shape[0]):
        for j in range(10):
            ax.text(j, i, f'{values[i,j]:.1f}', ha='center', va='center',
                    color='white' if values[i,j] > values.max()*.6 else 'black')
    fig.colorbar(im, ax=ax, label='%')
    fig.tight_layout()
    fig.savefig(output / 'cluster_profile.png', dpi=200)
    plt.close(fig)


def write_report(output, scores, summary, ratios, comparison, metadata):
    lines = ['# 대전광역시 상권 군집화 검증 보고서', '',
             '원본 79,691행·39열, 상가 ID 79,691개, 행정동 코드 82개를 확인했다. 원본과 전처리 CSV가 일치하며 기존 구/동/업종/동별 업종 집계도 재계산 결과와 일치한다.',
             '입력은 82행·14열이다. 행정동 키 중복, 수치 결측·무한대는 없고 업종 비율 합은 허용오차 1e-10 이내에서 1이다. 다양성도 재계산해 확인했다.', '',
             '## 특징 설계', '',
             '업종 비율 10개를 각각 표준화한 뒤 sqrt(0.8/10), log1p(전체상가수)를 표준화한 뒤 sqrt(0.2)를 곱한다. 업종 구성과 규모의 총분산을 80:20으로 설정한 탐색적 설계이며 정답 가중치를 뜻하지 않는다.',
             '비율 합이 1이므로 독립 변수 10개가 아니다. K-means는 독립성을 요구하지 않으므로 합 제약을 유지한 유클리드 거리로 비교한다. 한 업종을 임의로 제거하지 않는다. 로그비 기반 조성자료 분석과는 다르다. 업종별 표준화는 희소 업종에도 같은 분산을 부여하므로 소규모 동의 극단 비율에 민감할 수 있다.',
             '업종다양성은 비율의 함수이므로 입력에서 제외하고 해석용으로 저장했다. 지리 좌표·인구는 입력에 사용하지 않았다. 원안 12개 특징과 규모 가중치 10/20/30% 비교는 feature_comparison.csv에 저장했다. 서로 다른 거리 공간의 실루엣 점수를 직접 성능 순위로 해석하지 않는다.', '',
             '## K 비교', '', '|K|실루엣|최소/최대 동 수|초기값 ARI 평균|음수 실루엣 동 수|', '|---|---|---|---|---|']
    for row in scores.itertuples():
        lines.append(f'|{row.K}|{row.silhouette_score:.6f}|{row.min_cluster_size}/{row.max_cluster_size}|{row.seed_ARI_mean:.4f}|{row.negative_silhouette_count}|')
    lines += ['', f"이번 실행 K={metadata['selected_k']}. 기본 K=3은 수동 검토한 탐색 후보이다. K=2는 실루엣이 가장 높지만 규모에 따른 2분할 성격이 강하다. K=3은 22/25/35개로 분포하며 초기값 0~9와 기준 42 간 ARI 평균 약 0.99로 이번 후보 중 안정적이었다. K=4/5는 초기값 안정성이 낮아지고 K=6~8은 1개 동 군집이 나타났다. K=3의 실루엣은 약 0.119로 낮아 경계가 겹친다. 명확한 자연적 유형이 발견됐다고 주장하지 않는다.",
              'ARI는 동일 데이터의 초기값 변경 안정성만 평가한다. 시간/표본 변화 검증은 아니다. --k로 다른 후보를 실행할 수 있으며 그 경우 아래 통계는 해당 K의 결과다.', '',
              '## 군집 해석', '', '비율은 행정동별 비율의 단순 평균이며 군집 전체 상가를 합산한 가중 비율과 다르다. 번호는 평균 상가 수 오름차순이다. 명칭은 관측 통계를 요약한 잠정 설명이다.', '']
    descriptions = {0: '소규모 음식·소매 비중형', 1: '수리·개인·시설관리·과학기술 상대 비중형', 2: '대규모 복합형'}
    for _, row in summary.iterrows():
        label = int(row['군집'])
        title = descriptions[label] if metadata['selected_k'] == 3 else '통계 요약'
        top = row[ratios].sort_values(ascending=False).head(4)
        lines.append(f"- 군집 {label} — {title}: {int(row['행정동수'])}개 동, 평균 상가 {row['전체상가수']:.1f}개. " + ', '.join(f"{c.removesuffix('_비율')} {v:.1%}" for c, v in top.items()) + '.')
    lines += ['', '## 가중치 민감도', '']
    for row in comparison[comparison.K.eq(metadata['selected_k'])].itertuples():
        lines.append(f'- {row.method}: 실루엣 {row.silhouette_score:.6f}, 기본 방법과 ARI {row.ARI_vs_main_same_K:.4f}.')
    lines += ['', '규모 가중치 10%에서 기본 20% 대비 ARI가 약 0.20으로 낮다. 초기값에 대한 안정성과 특징 가중치에 대한 안정성은 다르다. 이번 분류는 80:20 설계에 의존하므로 유형명을 확정된 사실로 제시하지 않는다. 원안 결과도 비교 후보로 보존한다.']
    lines += ['', '## PCA 및 한계', '',
              f"PCA는 군집화에 사용한 가중 공간을 사후 시각화한다. PC1 {metadata['pca_explained_variance_ratio'][0]:.1%}, PC2 {metadata['pca_explained_variance_ratio'][1]:.1%}의 분산을 설명한다. 2차원 그림의 겹침과 고차원 거리를 동일시하지 않는다.",
              "현재 NumPy 환경에서 sklearn의 거리 계산용 행렬곱에 RuntimeWarning이 발생했다. 경고를 숨기는 대신 유클리드 거리를 좌표 차이로 직접 계산하고 silhouette_samples(metric='precomputed')에 전달한다. K-means 목적함수는 유지한다.",
              '2026년 9월 등록 상가 구성 분석이다. 매출·유동인구·임대료·폐업률을 사용하지 않았으므로 창업 성공률이나 수익성을 예측하지 않는다. 인구와 행정동/법정동 이름을 임의로 연결하지 않았다.', '',
              '## 실행 및 재현', '', '프로젝트 상위 작업 폴더에서:', '```sh', 'd_vision_project/.venv/bin/python d_vision_project/clustering.py --k 3', '```', '',
              f"Python {metadata['python']}, scikit-learn {metadata['versions']['sklearn']}. 기존 프로젝트 .venv를 사용했고 추가 설치는 없다. 난수 42, n_init=50, 초기값 0~9 비교. 입력/코드 SHA-256, 버전, 특징 목록은 run_metadata.json, 모델 중심 및 변환 파라미터는 model_parameters.npz, 실제 입력 좌표는 transformed_features.csv에 저장했다.",
              '기존 clustering.py는 results/code_before_review/clustering.py에 보존했다. data_preprocessing.py, app.py, 원본/전처리 데이터와 기존 결과 파일은 변경하지 않았다. 실행마다 results/clustering_실행시각/에 저장한다. 지정한 --output-dir가 이미 존재하면 덮어쓰지 않고 실패한다.', '',
              '## 다음 단계', '', '군집 검토 후 행정동·법정동 코드 대응을 확인하여 주요 지역 비교 범위를 확정하고 Streamlit 전체 현황·군집·업종 탐색·지도 기능을 구현한다. 이번에는 대시보드를 구현하지 않았다.', '',
              '방법 참고: https://scikit-learn.org/stable/auto_examples/cluster/plot_kmeans_silhouette_analysis.html', '']
    (output / 'analysis_report.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--k', type=int, default=3, choices=range(2, 9), help='안정성과 해석성을 검토한 기본 후보는 3입니다.')
    parser.add_argument('--output-dir', type=Path, help='새 폴더만 허용합니다.')
    args = parser.parse_args()
    if args.output_dir and args.output_dir.exists():
        parser.error('--output-dir가 이미 존재합니다. 새 폴더를 지정하세요.')
    df, ratios, validation = load_and_validate()
    x, rs, ss = transform(df, ratios)
    scores, models, samples, stability = compare(x)
    print('검증 통과: 79,691개 상가 / 82개 행정동 / 원본 및 기존 요약 CSV 일치')
    print(scores.to_string(index=False))
    model = models[args.k]
    order = df.assign(label=model.labels_).groupby('label')['전체상가수'].mean().sort_values().index
    mapping = {int(old): new for new, old in enumerate(order)}
    df['로그상가수'] = np.log1p(df['전체상가수'])
    df['군집'] = [mapping[int(label)] for label in model.labels_]
    df['실루엣'] = samples[args.k]
    pca = PCA(n_components=2, svd_solver='full')
    xy = pca.fit_transform(x)
    df['PCA1'], df['PCA2'] = xy[:, 0], xy[:, 1]
    summary = df.groupby('군집')[['전체상가수', '업종다양성'] + ratios].mean()
    summary.insert(0, '행정동수', df.groupby('군집').size())
    summary['전체상가수_합계'] = df.groupby('군집')['전체상가수'].sum()
    summary['평균실루엣'] = df.groupby('군집')['실루엣'].mean()
    summary = summary.reset_index()
    comparisons = []
    methods = [('original_12_features', StandardScaler().fit_transform(df[ratios + ['로그상가수', '업종다양성']])),
               ('size_weight_0.1', transform(df, ratios, .1)[0]), ('size_weight_0.2', x),
               ('size_weight_0.3', transform(df, ratios, .3)[0])]
    for name, other in methods:
        dist = distances(other)
        for k in range(2, 9):
            m = fit(other, k, n_init=20 if name == 'original_12_features' else N_INIT)
            comparisons.append({'method': name, 'K': k,
                                'silhouette_score': float(silhouette_samples(dist, m.labels_, metric='precomputed').mean()),
                                'ARI_vs_main_same_K': adjusted_rand_score(models[k].labels_, m.labels_),
                                'min_cluster_size': int(np.bincount(m.labels_).min())})
    comparison = pd.DataFrame(comparisons)
    candidate_profiles = []
    for k, candidate in models.items():
        profile = df.assign(candidate_cluster=candidate.labels_).groupby('candidate_cluster')[['전체상가수', '업종다양성'] + ratios].mean()
        profile.insert(0, '행정동수', np.bincount(candidate.labels_, minlength=k))
        profile.insert(0, 'K', k)
        candidate_profiles.append(profile.reset_index())
    output = (args.output_dir or BASE_DIR / 'results' / datetime.now().astimezone().strftime('clustering_%Y%m%d_%H%M%S_%f')).resolve()
    output.mkdir(parents=True, exist_ok=False)
    for name, data in [('clustered_dongs.csv', df), ('cluster_summary.csv', summary),
                       ('silhouette_scores.csv', scores.assign(selected=scores.K.eq(args.k))),
                       ('seed_stability.csv', stability), ('feature_comparison.csv', comparison),
                       ('candidate_profiles.csv', pd.concat(candidate_profiles, ignore_index=True))]:
        save_csv(data, output, name)
    save_csv(pd.concat([df[KEYS], pd.DataFrame(x, columns=ratios + ['로그상가수_가중표준화'])], axis=1), output, 'transformed_features.csv')
    save_csv(pd.DataFrame(pca.components_.T, index=ratios + ['로그상가수'], columns=['PC1', 'PC2']).rename_axis('feature').reset_index(), output, 'pca_loadings.csv')
    np.savez(output / 'model_parameters.npz', centers=model.cluster_centers_[list(order)],
             ratio_mean=rs.mean_, ratio_scale=rs.scale_, log_size_mean=ss.mean_, log_size_scale=ss.scale_,
             size_weight=SIZE_WEIGHT, ratio_columns=np.array(ratios), pca_components=pca.components_, pca_mean=pca.mean_)
    metadata = {'selected_k': args.k, 'random_state': SEED, 'n_init': N_INIT,
                'composition_weight': 1-SIZE_WEIGHT, 'size_weight': SIZE_WEIGHT,
                'feature_columns': ratios + ['로그상가수'], 'validation': validation,
                'pca_explained_variance_ratio': pca.explained_variance_ratio_.tolist(),
                'python_executable': os.sys.executable, 'python': platform.python_version(),
                'versions': {'numpy': np.__version__, 'pandas': pd.__version__, 'sklearn': sklearn.__version__, 'matplotlib': matplotlib.__version__},
                'script_sha256': sha256(Path(__file__)), 'run_at': datetime.now().astimezone().isoformat()}
    (output / 'run_metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    plot_results(df, scores, summary, ratios, pca, output, args.k)
    write_report(output, scores, summary, ratios, comparison, metadata)
    print('\n군집별 평균 특징:\n', summary.to_string(index=False))
    print('\n결과 저장:', output)


if __name__ == '__main__':
    with threadpool_limits(limits=1):
        main()
