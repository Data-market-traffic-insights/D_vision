"""정거장 주변 업종 비중의 추세 추정. 교통 효과는 별도 사용자 가정이다."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

MODEL_VERSION = 'share-trend-v1'
RIDGE_ALPHA = 4.0  # 연 단위 시간축의 기울기를 0 방향으로 축소하는 고정 규제값
KEYS = ['station_id', 'radius_m', 'industry']


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_forecast_data(base):
    base = Path(base)
    folder = base / 'data' / 'forecast'
    metadata = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if metadata['station_sha256'] != file_hash(base / 'data/tram_stations.csv'):
        raise ValueError('정거장 좌표가 변경됐습니다. 과거 반경 집계를 다시 생성해 주세요.')
    history = pd.read_csv(folder / 'station_history.csv', dtype={'station_id': str})
    history['date'] = pd.to_datetime(history['date'])
    if history.duplicated(KEYS + ['date']).any():
        raise ValueError('과거 집계 키가 중복됩니다.')
    if (history.city_count <= 0).any() or (history.shop_count < 0).any() or (history.shop_count > history.city_count).any():
        raise ValueError('과거 상가 집계 범위를 확인해 주세요.')
    history['share_per_10000'] = history.shop_count / history.city_count * 10000
    demand = pd.read_csv(folder / 'tram_demand_2030_plan.csv', dtype={'station_no': str})
    if demand.station_no.duplicated().any() or set(demand.station_no) != set(map(str, range(201,246))):
        raise ValueError('수요 자료는 중복 없이 45개 정거장이어야 합니다.')
    numeric = demand[['board_2030', 'alight_2030', 'total_2030']]
    if numeric.isna().any().any() or (numeric < 0).any().any() or not demand.total_2030.eq(demand.board_2030 + demand.alight_2030).all():
        raise ValueError('수요 자료 합계 또는 결측을 확인해 주세요.')
    markets = pd.read_csv(folder / 'construction_city_markets.csv')
    return history, demand, markets, metadata


def predict_share(series, target_date, model='trend'):
    """실제 경과 연수를 사용해 log(1+비중) 기울기를 추정, 마지막 관측에 고정."""
    series = series.sort_values('date')
    dates = pd.to_datetime(series.date)
    if len(series) < 2 or dates.duplicated().any():
        raise ValueError('서로 다른 날짜의 관측값이 2개 이상 필요합니다.')
    target = pd.Timestamp(target_date)
    if target < dates.iloc[-1]:
        raise ValueError('예측일은 마지막 관측일 이후여야 합니다.')
    values = series.share_per_10000.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any() or (values > 10000).any():
        raise ValueError('업종 비중이 유효하지 않습니다.')
    if model not in ('trend', 'persistence'):
        raise ValueError('알 수 없는 예측 방법입니다.')
    if model == 'persistence':
        return float(values[-1])
    years = (dates - dates.iloc[0]).dt.days.to_numpy(dtype=float) / 365.25
    centered = years - years.mean()
    logs = np.log1p(values)
    slope = float(np.dot(centered, logs - logs.mean()) / (np.dot(centered, centered) + RIDGE_ALPHA))
    horizon = (target - dates.iloc[-1]).days / 365.25
    return float(np.clip(np.expm1(np.clip(logs[-1] + slope*horizon, 0, np.log1p(10000))), 0, 10000))


def evaluate_models(history):
    """마지막 시점은 검증 전용. 겹치는 반경은 독립 표본으로 해석하지 않는다."""
    dates = sorted(history.date.unique())
    if len(dates) < 4:
        raise ValueError('마지막 시점 검증을 위해 4개 이상의 시점이 필요합니다.')
    cutoff = dates[-1]
    rows = []
    for keys, group in history.groupby(KEYS, sort=True):
        train = group.loc[group.date < cutoff]
        test = group.loc[group.date == cutoff]
        if len(train) != len(dates)-1 or len(test) != 1:
            raise ValueError('시점별 정거장·업종 조합이 누락됐습니다.')
        actual = float(test.share_per_10000.iloc[0])
        rows.append(dict(zip(KEYS, keys), actual=actual,
                         trend=predict_share(train, cutoff, 'trend'),
                         persistence=predict_share(train, cutoff, 'persistence')))
    scores = pd.DataFrame(rows)
    trend_mae = float((scores.trend-scores.actual).abs().mean())
    persistence_mae = float((scores.persistence-scores.actual).abs().mean())
    # 동률일 때는 더 단순한 직전 비중 유지 기준을 선택한다.
    selected = 'trend' if trend_mae < persistence_mae else 'persistence'
    return {'selected': selected, 'trend_mae': trend_mae,
            'persistence_mae': persistence_mae, 'validation_date': str(pd.Timestamp(cutoff).date()),
            'validation_series': len(scores), 'scores': scores}


def forecast_series(series, target_date, model):
    latest = series.sort_values('date').iloc[-1]
    share = predict_share(series, target_date, model)
    return {'share_per_10000': share, 'count': share / 10000 * int(latest.city_count),
            'latest_count': int(latest.shop_count), 'city_reference_count': int(latest.city_count)}


def demand_scenario(base_count, total, reference, strength_percent, target_year, acknowledged=False):
    """수요/전 정거장 중앙값의 차이를 사용자가 정한 강도로 적용. 학습계수 아님."""
    inputs = np.asarray([base_count, total, reference, strength_percent], dtype=float)
    if not np.isfinite(inputs).all() or base_count < 0 or total < 0 or reference <= 0 or not 0 <= strength_percent <= 50:
        raise ValueError('시나리오 입력 범위를 확인해 주세요.')
    if not acknowledged or target_year < 2030:
        return float(base_count)
    return float(base_count * (1 + strength_percent/100 * (total/reference - 1)))


def filter_markets(markets, section='전체'):
    if section == '전체':
        return markets.copy()
    return markets.loc[markets.section.apply(lambda value: section in [part.strip() for part in value.split(';')])].copy()
