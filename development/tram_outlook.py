"""관측 변화와 추세 외삽을 분리한 정거장 상권 설명용 집계."""
import numpy as np
import pandas as pd
from tram_forecast import forecast_series


def change_percent(before, after):
    """기준이 0이면 증가율 대신 결측을 반환한다. 신규 점포 수는 따로 표시한다."""
    return (after/before-1)*100 if before > 0 else np.nan


def industry_outlook(history, station_id, radius, year):
    frame = history.loc[(history.station_id == station_id) & (history.radius_m == radius)]
    if frame.empty:
        raise ValueError('정거장과 반경에 해당하는 관측이 없습니다.')
    first_date, last_date = frame.date.min(), frame.date.max()
    first_total = float(frame.loc[frame.date == first_date, 'shop_count'].sum())
    last_total = float(frame.loc[frame.date == last_date, 'shop_count'].sum())
    rows = []
    for industry, series in frame.groupby('industry', sort=True):
        series = series.sort_values('date')
        first, latest = series.iloc[0], series.iloc[-1]
        previous = series.iloc[-2]
        trend = forecast_series(series, f'{year}-09-30', 'trend')['count']
        # 마지막 시점은 학습에서 제외한 뒤 과거 예측을 재현한다.
        check = forecast_series(series.iloc[:-1], latest.date, 'trend')
        trend_error = abs(check['share_per_10000'] - float(latest.share_per_10000)) / 10000 * int(latest.city_count)
        maintain_error = abs(float(previous.share_per_10000) - float(latest.share_per_10000)) / 10000 * int(latest.city_count)
        rows.append({'industry':industry, 'first_count':int(first.shop_count),
                     'latest_count':int(latest.shop_count), 'count_change':int(latest.shop_count-first.shop_count),
                     'local_change_pct':change_percent(first.shop_count,latest.shop_count),
                     'city_change_pct':change_percent(first.city_count,latest.city_count),
                     'relative_change_pct':change_percent(first.share_per_10000,latest.share_per_10000),
                     'recent_change':int(latest.shop_count-previous.shop_count),
                     'mix_share_pct':float(latest.shop_count/last_total*100) if last_total else 0.,
                     'mix_change_pp':(float(latest.shop_count/last_total*100) if last_total else 0.) -
                                     (float(first.shop_count/first_total*100) if first_total else 0.),
                     'persistence_count':float(latest.shop_count), 'trend_count':trend,
                     'trend_delta':trend-int(latest.shop_count), 'trend_error_count':trend_error,
                     'persistence_error_count':maintain_error,
                     'collection_break':industry in {'교육','보건의료'}})
    return pd.DataFrame(rows)


def station_outlook(history, stations, demand, radius, industry, year):
    rows = []
    median = float(demand.total_2030.median())
    for station in stations.itertuples(index=False):
        stats = industry_outlook(history, str(station.station_id), radius, year)
        selected = stats.loc[stats.industry == industry].iloc[0]
        planned = demand.loc[demand.station_no == str(station.station_id)].iloc[0]
        rows.append({'station_id':str(station.station_id),'station_name':station.station_name,
                     'latest_count':int(selected.latest_count),'count_change':int(selected.count_change),
                     'relative_change_pct':selected.relative_change_pct,
                     'trend_count':selected.trend_count,'trend_delta':selected.trend_delta,
                     'planned_total':int(planned.total_2030),
                     'planned_rank':int((demand.total_2030 > planned.total_2030).sum()+1),
                     'planned_vs_median':float(planned.total_2030/median),
                     'plan_name':planned.plan_name})
    return pd.DataFrame(rows)


def describe_industry(row):
    direction = '늘었' if row.count_change > 0 else '줄었' if row.count_change < 0 else '같았'
    first = f"{row.industry} 등록 점포는 {int(row.first_count):,}개에서 {int(row.latest_count):,}개로 {direction}습니다."
    if pd.isna(row.relative_change_pct):
        relative = '첫 시점 점포가 없어 상대 증가율은 계산하지 않습니다.'
    elif row.relative_change_pct > 0:
        relative = f"대전 전체 동일 업종에서 이 주변이 차지하는 비중은 {row.relative_change_pct:.1f}% 커졌습니다."
    elif row.relative_change_pct < 0:
        relative = f"대전 전체 동일 업종에서 이 주변이 차지하는 비중은 {abs(row.relative_change_pct):.1f}% 작아졌습니다."
    else:
        relative = '대전 전체 동일 업종에서 이 주변이 차지하는 비중은 유지됐습니다.'
    if row.count_change > 0 and row.relative_change_pct < 0:
        interpretation = '점포 수는 늘었지만 대전 전체의 증가 속도보다 느렸습니다.'
    elif row.count_change < 0 and row.relative_change_pct > 0:
        interpretation = '점포 수는 줄었지만 대전 전체 동일 업종보다는 덜 줄었습니다.'
    elif row.count_change > 0:
        interpretation = '과거 관측에서는 이 업종의 점포 확대가 나타났습니다.'
    elif row.count_change < 0:
        interpretation = '과거 관측에서는 이 업종의 점포 축소가 나타났습니다.'
    else:
        interpretation = '첫 시점과 마지막 시점의 점포 수가 같습니다.'
    if row.collection_break:
        interpretation += ' 교육·보건의료는 시 전체 수집 범위 변화 가능성이 있어 별도 확인이 필요합니다.'
    return first+' '+relative+' '+interpretation
