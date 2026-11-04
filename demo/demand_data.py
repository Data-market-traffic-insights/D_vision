"""행정동별 배후 주민 수. 법정동 주민등록 인구를 상가 분포로 행정동에 배분한 근사값이다."""
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
POPULATION_FILE = BASE_DIR / 'data/daejeon_resident_population_20260930.csv'  # 행정안전부 2026-09-30 기준
POPULATION_BASIS = '주민등록 인구(2026-09-30, 법정동→행정동 상가 비율 배분 근사)'


def admin_population(shops, path=POPULATION_FILE):
    """법정동 인구를 그 법정동 상가가 속한 행정동별 상가 비율로 나눈다.

    법정동 하나가 여러 행정동에 걸칠 때만 배분이 생긴다. 상가가 없는 법정동 인구는 제외하고 기록한다.
    """
    pop = pd.read_csv(path, dtype={'법정동코드': str}, encoding='utf-8-sig')
    if not pop['시도명'].eq('대전광역시').all() or pop['법정동코드'].duplicated().any():
        raise ValueError('대전 법정동 인구 자료가 아니거나 법정동 코드가 중복됩니다.')
    pairs = shops.groupby(['법정동코드', '행정동코드']).size().rename('상가수').reset_index()
    pairs['배분비율'] = pairs['상가수'] / pairs.groupby('법정동코드')['상가수'].transform('sum')
    pairs['분할'] = pairs.groupby('법정동코드')['행정동코드'].transform('size').gt(1)
    joined = pairs.merge(pop[['법정동코드', '계']], on='법정동코드', how='left')
    joined['배분인구'] = joined['계'].fillna(0) * joined['배분비율']
    result = joined.groupby('행정동코드').agg(주민등록인구=('배분인구', 'sum'), 배분포함=('분할', 'any')).reset_index()
    result['주민등록인구'] = result['주민등록인구'].round().astype(int)
    result.attrs['제외인구'] = int(pop.loc[~pop['법정동코드'].isin(pairs['법정동코드']), '계'].sum())
    return result
