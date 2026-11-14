"""같은 출처·공간 단위의 연간 상가자료에 적용하는 도시 간 전이 실험."""
import numpy as np
import pandas as pd

SECTORS = ['음식', '카페', '소매', '수리·개인']
NUMERIC = ['log_count', 'log_total', 'food_share', 'coffee_share', 'retail_share', 'service_share']
FEATURES = NUMERIC + ['sector']
MODEL_NAMES = {'ridge':'릿지 회귀', 'random_forest':'랜덤포레스트',
               'gradient_boosting':'그래디언트 부스팅', 'persistence':'현재 점포 수 유지',
               'sector_drift':'서울 업종별 평균 변화'}


def elapsed_years(origin, target):
    days = (pd.Timestamp(target)-pd.Timestamp(origin)).days
    if days <= 0:
        raise ValueError('예측 대상일은 입력일 뒤여야 합니다.')
    return days / 365.25


def feature_rows(panel):
    rows = []
    for row in panel.to_dict('records'):
        if row['total_count'] < 0:
            raise ValueError('점포 수는 음수일 수 없습니다.')
        for sector, column in zip(SECTORS, ['food_count','coffee_count','retail_count','service_count']):
            count = row[column]
            if count < 0 or count > row['total_count']:
                raise ValueError('업종 점포 수 범위 확인 필요')
            new = dict(row, sector=sector, count=count,
                       log_count=np.log1p(count), log_total=np.log1p(row['total_count']))
            for name, key in [('food','food_count'),('coffee','coffee_count'),('retail','retail_count'),('service','service_count')]:
                new[name+'_share'] = row[key]/row['total_count'] if row['total_count'] else 0.
            rows.append(new)
    return pd.DataFrame(rows)


def paired_rows(features, origin, target):
    keys = ['city','anchor_id','sector']
    left = features.loc[features.date.eq(origin)].copy()
    right = features.loc[features.date.eq(target), keys+['count']].rename(columns={'count':'actual'})
    joined = left.merge(right,on=keys,validate='one_to_one')
    joined['origin_date'] = origin
    joined['target_date'] = target
    joined['elapsed_years'] = elapsed_years(origin,target)
    joined['annual_log_change'] = (np.log1p(joined.actual)-np.log1p(joined['count']))/joined.elapsed_years
    return joined


def restore_counts(count, annual_log_change, years):
    with np.errstate(over='raise', invalid='raise'):
        value = np.maximum(0., np.expm1(np.log1p(np.asarray(count))+np.asarray(annual_log_change)*years))
    if not np.isfinite(value).all():
        raise ValueError('유한하지 않은 예측')
    return value


def outside_training(frame, reference):
    """학습 범위 밖 입력을 알린다. 통계적 신뢰도나 예측구간은 아니다."""
    flags = np.zeros(len(frame),dtype=bool)
    for key in NUMERIC:
        flags |= (frame[key].to_numpy()<reference[key].min()) | (frame[key].to_numpy()>reference[key].max())
    return flags
