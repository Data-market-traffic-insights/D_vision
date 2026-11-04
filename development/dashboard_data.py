"""대시보드용 읽기 전용 집계와 군집 결과 검증. 행정동/법정동은 코드로 구분한다."""
from datetime import datetime
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pydeck as pdk

BASE_DIR = Path(__file__).resolve().parent
ADMIN_KEYS = ['시군구명', '행정동코드', '행정동명']
LEGAL_KEYS = ['시군구명', '법정동코드', '법정동명']
TYPES = {0: '소규모 음식·소매 비중형', 1: '수리·개인·시설관리·과학기술 상대 비중형', 2: '대규모 복합형'}
COLORS = ['#127C80', '#D98C40', '#526BB3']
SHOP_COLUMNS = ['상가업소번호', '상호명', '시군구명', '행정동코드', '행정동명',
                '법정동코드', '법정동명', '상권업종대분류명', '상권업종중분류명', '경도', '위도', '도로명주소']
REQUIRED_RUN = ['clustered_dongs.csv', 'cluster_summary.csv', 'silhouette_scores.csv', 'run_metadata.json']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def data_signature(base=BASE_DIR):
    """파일이 바뀌면 Streamlit 캐시도 갱신한다. 기존 결과는 수정하지 않는다."""
    files = list((base / 'data').glob('*.csv'))
    for directory in (base / 'results').iterdir():
        if directory.is_dir():
            files.extend(directory / name for name in REQUIRED_RUN if (directory / name).is_file())
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(files))


def region_table(shops, basis='행정동'):
    keys = ADMIN_KEYS if basis == '행정동' else LEGAL_KEYS
    table = shops.groupby(keys, dropna=False).size().rename('전체상가수').reset_index()
    table['지역표시'] = table['시군구명'] + ' · ' + table[keys[-1]]
    return table.sort_values(['시군구명', keys[-1]]).reset_index(drop=True)


def industry_profile(shops, industries):
    counts = shops.groupby('상권업종대분류명').size().reindex(industries, fill_value=0)
    result = counts.rename('상가수').rename_axis('업종').reset_index()
    result['비율'] = result['상가수'] / len(shops) if len(shops) else 0.0
    result['비율(%)'] = result['비율'] * 100
    return result


def entropy(profile):
    p = profile['비율'].to_numpy()
    positive = p[p > 0]
    return float(-(positive * np.log(positive)).sum())


def select_shops(shops, gu='전체', dong='전체', industry='전체', medium='전체'):
    mask = pd.Series(True, index=shops.index)
    for column, value in [('시군구명', gu), ('행정동코드', dong),
                           ('상권업종대분류명', industry), ('상권업종중분류명', medium)]:
        if value != '전체':
            mask &= shops[column].eq(value)
    return shops.loc[mask]


def exploration_table(shops, admin, industry, medium='전체', min_shops=0, gu='전체'):
    selected = select_shops(shops, gu=gu, industry=industry, medium=medium)
    counts = selected.groupby('행정동코드').size()
    result = admin.copy()
    if gu != '전체':
        result = result[result['시군구명'].eq(gu)].copy()
    result['선택업종상가수'] = result['행정동코드'].map(counts).fillna(0).astype(int)
    result['선택업종비율(%)'] = result['선택업종상가수'] / result['전체상가수'] * 100
    return result[result['전체상가수'].ge(min_shops)].copy()


def map_points(shops, limit):
    lon = pd.to_numeric(shops['경도'], errors='coerce')
    lat = pd.to_numeric(shops['위도'], errors='coerce')
    valid = np.isfinite(lon) & np.isfinite(lat) & lon.between(-180, 180) & lat.between(-90, 90)
    located = shops.loc[valid].copy()
    located['경도'], located['위도'] = lon[valid], lat[valid]
    points = located.sample(n=limit, random_state=42) if len(located) > limit else located
    return points, int((~valid).sum()), len(located)


def make_map(points):
    # 작은 표시 전용 데이터만 브라우저로 보낸다. 원본 상가명은 HTML 대신 텍스트로 표시한다.
    plotted = points[['상호명', '행정동명', '상권업종대분류명', '경도', '위도']].rename(
        columns={'상호명': 'name', '행정동명': 'dong', '상권업종대분류명': 'industry', '경도': 'lon', '위도': 'lat'})
    center = plotted[['lat', 'lon']].median()
    layer = pdk.Layer('ScatterplotLayer', plotted, id='shops', get_position='[lon, lat]',
                      get_fill_color=[18, 124, 128, 160], get_radius=24, radius_min_pixels=3,
                      radius_max_pixels=10, pickable=True, auto_highlight=True)
    return pdk.Deck(layers=[layer], map_provider='carto', map_style='light',
                    initial_view_state=pdk.ViewState(latitude=float(center['lat']), longitude=float(center['lon']), zoom=11.5),
                    tooltip={'text': '{name}\n{dong} · {industry}', 'style': {'backgroundColor': '#142C3D', 'color': 'white'}})


def validate_run(directory, shops, admin, industries, source_hashes):
    require(all((directory / f).is_file() for f in REQUIRED_RUN), '필수 군집 결과 파일 누락')
    metadata = json.loads((directory / 'run_metadata.json').read_text(encoding='utf-8'))
    require(metadata['selected_k'] == 3, '현재 대시보드는 검증된 K=3 결과가 필요합니다.')
    require(np.isclose(metadata['composition_weight'], .8) and np.isclose(metadata['size_weight'], .2), '특징 가중치가 80:20이 아닙니다.')
    for filename, digest in source_hashes.items():
        recorded = [v for k, v in metadata['validation']['source_sha256'].items() if Path(k).name == filename]
        require(recorded == [digest], f'현재 {filename}과 분석 입력 해시가 다릅니다.')
    clusters = pd.read_csv(directory / 'clustered_dongs.csv', dtype={'행정동코드': str})
    require(len(clusters) == len(admin) and not clusters.duplicated(['시군구명', '행정동명']).any(), '군집 행정동 중복/누락')
    require(set(clusters['군집']) == set(TYPES), '군집 번호가 0/1/2가 아닙니다.')
    numeric_cols = ['전체상가수', '업종다양성', 'PCA1', 'PCA2', '실루엣'] + [f'{i}_비율' for i in industries]
    require(np.isfinite(clusters[numeric_cols].to_numpy(dtype=float)).all(), '군집 특징에 결측/무한대')
    # 코드가 없는 이전 결과도 구+행정동명과 실제 코드표의 일대일 대응을 검증한 후 연결한다.
    if '행정동코드' not in clusters:
        require(not admin.duplicated(['시군구명', '행정동명']).any(), '이름만으로 동을 특정할 수 없습니다.')
        clusters = clusters.merge(admin[ADMIN_KEYS], on=['시군구명', '행정동명'], validate='one_to_one')
    joined = admin.merge(clusters, on=ADMIN_KEYS, suffixes=('_actual', ''), how='left', validate='one_to_one')
    require(joined['군집'].notna().all(), '현재 상가 데이터에 대응하지 않는 군집 결과')
    require(np.array_equal(joined['전체상가수_actual'], joined['전체상가수']), '현재 상가 수와 군집 결과가 다릅니다.')
    count_matrix = pd.crosstab(shops['행정동코드'], shops['상권업종대분류명']).reindex(index=joined['행정동코드'], columns=industries, fill_value=0)
    p = count_matrix.to_numpy() / joined[['전체상가수']].to_numpy()
    require(np.allclose(p, joined[[f'{i}_비율' for i in industries]], atol=1e-10, rtol=0), '군집 업종 비율 불일치')
    require(np.allclose(-(p*np.log(np.clip(p, 1e-12, None))).sum(axis=1), joined['업종다양성']), '군집 다양성 불일치')
    summary = pd.read_csv(directory / 'cluster_summary.csv')
    require(set(summary['군집']) == set(TYPES) and summary['군집'].is_unique, '군집 요약 번호 오류')
    cols = ['전체상가수', '업종다양성'] + [f'{i}_비율' for i in industries]
    require(np.allclose(summary.set_index('군집').sort_index()[cols], clusters.groupby('군집')[cols].mean().sort_index()), '군집 평균 요약 불일치')
    require(np.array_equal(summary.set_index('군집').sort_index()['행정동수'], clusters.groupby('군집').size()), '군집 동 수 불일치')
    scores = pd.read_csv(directory / 'silhouette_scores.csv')
    require(scores['K'].is_unique and set(scores['K']) == set(range(2, 9)), 'K=2~8 점수 누락')
    require(np.isfinite(scores['silhouette_score']).all() and scores['silhouette_score'].between(-1, 1).all(), '실루엣 점수 범위 오류')
    require(np.isclose(scores.loc[scores.K.eq(3), 'silhouette_score'].iloc[0], clusters['실루엣'].mean()), 'K=3 실루엣 요약 불일치')
    explained = np.array(metadata['pca_explained_variance_ratio'])
    require(explained.shape == (2,) and np.isfinite(explained).all() and (explained >= 0).all() and explained.sum() <= 1.000001, 'PCA 설명 분산 오류')
    joined['군집'] = joined['군집'].astype(int)
    joined['잠정유형'] = joined['군집'].map(TYPES)
    return joined.drop(columns='전체상가수_actual'), summary, scores, metadata


def load_dashboard_data(base=BASE_DIR):
    base = Path(base)
    shops = pd.read_csv(base / 'data/daejeon_clean.csv', usecols=SHOP_COLUMNS,
                        dtype={'상가업소번호': str, '행정동코드': str, '법정동코드': str}, encoding='utf-8-sig')
    require(not shops[ADMIN_KEYS + LEGAL_KEYS + ['상권업종대분류명']].isna().any().any(), '지역 코드/명칭 또는 업종에 결측값이 있습니다.')
    admin = region_table(shops)
    legal = region_table(shops, '법정동')
    require(admin['행정동코드'].is_unique and legal['법정동코드'].is_unique, '지역 코드에 복수 명칭이 있습니다.')
    industries = sorted(shops['상권업종대분류명'].unique())
    require(shops['상가업소번호'].is_unique, '중복 상가 번호가 있습니다.')
    hashes = {name: file_hash(base / 'data' / name) for name in ['daejeon_clean.csv', 'ml_features.csv']}
    candidates, skipped = [], []
    for directory in (base / 'results').iterdir():
        if directory.is_dir() and (directory / 'run_metadata.json').is_file():
            try:
                metadata = json.loads((directory / 'run_metadata.json').read_text(encoding='utf-8'))
                stamp = datetime.fromisoformat(metadata['run_at']).timestamp()
                candidates.append((stamp, directory))
            except (ValueError, KeyError, TypeError, OSError) as exc:
                skipped.append(f'{directory.name}: 실행 정보 오류 ({exc})')
    for _, directory in sorted(candidates, key=lambda item: (item[0], item[1].name), reverse=True):
        try:
            joined, summary, scores, metadata = validate_run(directory, shops, admin, industries, hashes)
            from demand_data import admin_population
            return {'shops': shops, 'admin': joined, 'legal': legal, 'industries': industries,
                    'population': admin_population(shops),
                    'summary': summary, 'scores': scores, 'metadata': metadata,
                    'run_dir': directory, 'skipped_runs': skipped}
        except (ValueError, KeyError, TypeError, OSError, pd.errors.ParserError) as exc:
            skipped.append(f'{directory.name}: {exc}')
    raise ValueError('현재 데이터와 일치하는 유효한 K=3 군집 결과가 없습니다. clustering.py를 실행하세요. ' + ' / '.join(skipped))
