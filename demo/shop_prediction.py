"""시점 t에 알 수 있는 값으로 t+h 점포 수를 예측하기 위한 특성 구성."""
import numpy as np
import pandas as pd

NUMERIC_FEATURES = [
    'log_count','log_lag1','log_lag2','log_lag3','change_1q','change_3q',
    'mean_4q','std_4q','log_total','food_share','retail_share','service_share','coffee_food_share',
    'log_new_distance','longitude','latitude','quarter_sin','quarter_cos','time_years',
    'sillim_operating','near_sillim_operating',
]
CATEGORICAL_FEATURES = ['sector','market_type','gu_code']
FEATURES=NUMERIC_FEATURES+CATEGORICAL_FEATURES


def quarter_number(value):
    value=str(value)
    if len(value)!=5 or value[-1] not in '1234':raise ValueError('분기 형식은 YYYYQ입니다.')
    return int(value[:4])*4+int(value[-1])-1


def quarter_label(number):
    number=int(number)
    return f'{number//4}{number%4+1}'


def prepare_features(panel, composition, geography):
    """달력의 빈 분기를 유지하고, 과거 4개 분기가 관측된 행만 반환한다."""
    panel=panel.copy()
    panel['quarter']=panel.quarter.astype(str)
    if panel.duplicated(['market_code','sector','quarter']).any():raise ValueError('점포 패널 키 중복')
    if panel['count'].isna().any() or (panel['count']<0).any():raise ValueError('원표 점포 수 누락·음수')
    panel['origin_ord']=panel.quarter.map(quarter_number)
    quarters=range(int(panel.origin_ord.min()),int(panel.origin_ord.max())+1)
    groups=panel[['market_code','sector']].drop_duplicates()
    index=pd.MultiIndex.from_tuples([(row.market_code,row.sector,q) for row in groups.itertuples(index=False) for q in quarters],
                                   names=['market_code','sector','origin_ord'])
    full=panel.set_index(['market_code','sector','origin_ord'])[['count']].reindex(index).reset_index()
    grouped=full.groupby(['market_code','sector'],sort=False)['count']
    for lag in range(1,4):full[f'lag{lag}']=grouped.shift(lag)
    # 각 행의 t, t-1, t-2, t-3 외에는 통계에 포함하지 않는다.
    full=full.dropna(subset=['count','lag1','lag2','lag3']).copy()
    recent=full[['count','lag1','lag2','lag3']]
    full['log_count']=np.log1p(full['count'])
    for lag in range(1,4):full[f'log_lag{lag}']=np.log1p(full[f'lag{lag}'])
    full['change_1q']=full['count']-full.lag1
    full['change_3q']=full['count']-full.lag3
    full['mean_4q']=recent.mean(axis=1)
    full['std_4q']=recent.std(axis=1,ddof=0)
    comp=composition.copy();comp['origin_ord']=comp.quarter.astype(str).map(quarter_number)
    full=full.merge(comp.drop(columns='quarter'),on=['market_code','origin_ord'],validate='many_to_one')
    full['log_total']=np.log1p(full.total_count)
    for field,numerator,denominator in [('food_share','food_count','total_count'),('retail_share','retail_count','total_count'),
                                       ('service_share','service_count','total_count'),('coffee_food_share','coffee_count','food_count')]:
        full[field]=full[numerator]/full[denominator].replace(0,np.nan)
    # 현재 기존역 목록·개통 후 승하차·pre_total은 과거 시점 입력으로 사용하지 않는다.
    geo=geography[['market_code','market_name','market_type','gu_code','new_distance_m','longitude','latitude']].copy()
    for col in ['market_code','gu_code','market_type']:geo[col]=geo[col].astype(str)
    full=full.merge(geo,on='market_code',validate='many_to_one')
    full['log_new_distance']=np.log1p(full.new_distance_m.clip(lower=0))
    quarter=full.origin_ord%4+1
    full['quarter_sin']=np.sin(2*np.pi*quarter/4)
    full['quarter_cos']=np.cos(2*np.pi*quarter/4)
    full['time_years']=(full.origin_ord-quarter_number('20211'))/4
    full['sillim_operating']=(full.origin_ord>=quarter_number('20222')).astype(int)
    full['near_sillim_operating']=full.sillim_operating*(full.new_distance_m<=500).astype(int)
    full['origin_quarter']=full.origin_ord.map(quarter_label)
    return full


def supervised_rows(features, panel, horizon):
    if horizon not in (1,4):raise ValueError('예측 간격은 1분기 또는 4분기입니다.')
    frame=features.copy();frame['target_ord']=frame.origin_ord+horizon
    target=panel[['market_code','sector','quarter','count']].copy()
    target['target_ord']=target.quarter.astype(str).map(quarter_number)
    target=target.rename(columns={'count':'actual'}).drop(columns='quarter')
    frame=frame.merge(target,on=['market_code','sector','target_ord'],validate='many_to_one')
    frame['target_quarter']=frame.target_ord.map(quarter_label)
    frame['log_change_target']=np.log1p(frame.actual)-frame.log_count
    return frame


def time_splits(frame):
    """예측 대상 연도로 분리한다. 2025년 정답은 모델 선택에 쓰지 않는다."""
    train=frame.loc[frame.target_ord<=quarter_number('20234')].copy()
    validation=frame.loc[frame.target_ord.between(quarter_number('20241'),quarter_number('20244'))].copy()
    test=frame.loc[frame.target_ord.between(quarter_number('20251'),quarter_number('20254'))].copy()
    if any(part.empty for part in [train,validation,test]):raise ValueError('학습·검증·최종 평가 기간이 부족합니다.')
    return train,validation,test


def baseline_prediction(frame, horizon, method):
    current=frame['count'].to_numpy(dtype=float)
    if method=='persistence':return current.copy()
    if method=='trend':return np.maximum(0,current+(current-frame.lag3.to_numpy())/3*horizon)
    raise ValueError('알 수 없는 비교 기준')


def count_prediction(model, frame):
    # log1p 점포 수 변화량을 원래 단위로 복원한다. 음수와 지수 오버플로를 방지한다.
    change=model.predict(frame[FEATURES])
    return np.maximum(0,np.expm1(np.clip(frame.log_count.to_numpy()+change,0,20)))


def error_metrics(actual,prediction):
    actual=np.asarray(actual,dtype=float);prediction=np.asarray(prediction,dtype=float)
    if len(actual)==0 or actual.shape!=prediction.shape or not np.isfinite(actual).all() or not np.isfinite(prediction).all():
        raise ValueError('지표 계산에 유효한 예측·관측 쌍이 필요합니다.')
    errors=prediction-actual
    return {'rows':len(actual),'mae':float(np.abs(errors).mean()),'rmse':float(np.sqrt(np.mean(errors**2))),
            'wape_pct':float(np.abs(errors).sum()/np.abs(actual).sum()*100) if np.abs(actual).sum()>0 else None,
            'bias':float(errors.mean())}
