"""신림선 상권의 매칭 비교. 관측된 차이를 트램의 확정 인과효과로 해석하지 않는다."""
import numpy as np
import pandas as pd

MATCH_QUARTERS = ['20211','20212','20213','20214']
PRE_QUARTERS = MATCH_QUARTERS + ['20221']
POST_QUARTERS = ['20223','20224'] + [f'{y}{q}' for y in (2023,2024,2025) for q in range(1,5)]
SECTORS = {
    '음식': lambda code: code.str.startswith('CS100'),
    '커피·음료': lambda code: code.eq('CS100010'),
    '소매': lambda code: code.str.startswith('CS300'),
    '미용·세탁·수리': lambda code: code.isin(['CS200025','CS200027','CS200028','CS200029','CS200030','CS200031','CS200032']),
}


def evidence_status(result, summaries):
    """탐색 결과를 성장성 점수나 확정 효과로 바꾸지 않는다."""
    if result.get('status')!='estimated':return '비교 가능한 표본 부족'
    if result['pre_check_flag']:return '개통 전 점검에서 차이 발견'
    if result['station_clusters']<6:return '역 단위 비교 표본 부족'
    if result['low_pct']<=0<=result['high_pct']:return '증가·감소 방향 불확실'
    related=[r for r in summaries if r['sector']==result['sector'] and r.get('status')=='estimated']
    if len(related)!=3 or any(r['pre_check_flag'] or r['low_pct']<=0<=r['high_pct'] for r in related):
        return '반경에 따른 결과 차이 확인 필요'
    return '탐색적 차이 관측 · 추가 검증 필요'


def cluster_interval(values, clusters, draws=2000, seed=20261114):
    """역 단위 재표집. 겹친 역세권의 시장들을 독립 표본으로 늘리지 않는다."""
    values=np.asarray(values,dtype=float);clusters=np.asarray(clusters)
    unique=np.unique(clusters)
    if not len(values) or not np.isfinite(values).all():
        raise ValueError('유효한 비교 차이가 필요합니다.')
    if len(unique)<2:
        return float('nan'),float('nan')
    sums=np.array([values[clusters==c].sum() for c in unique])
    counts=np.array([(clusters==c).sum() for c in unique])
    rng=np.random.default_rng(seed)
    picks=rng.integers(0,len(unique),size=(draws,len(unique)))
    samples=sums[picks].sum(axis=1)/counts[picks].sum(axis=1)
    return tuple(float(v) for v in np.quantile(samples,[.025,.975]))


def matched_pairs(panel, geography, radius=500, n_controls=2):
    """2021년만 사용. 같은 상권 유형·기존 역 접근 여부, 비복원 최근접 매칭."""
    required=MATCH_QUARTERS + ['20221'] + POST_QUARTERS
    panel=panel.copy();panel.columns=panel.columns.astype(str)
    complete=panel.reindex(columns=required).dropna()
    geo=geography.set_index('market_code').reindex(complete.index).dropna(subset=['new_distance_m','existing_distance_m'])
    complete=complete.loc[geo.index]
    train=np.log1p(complete[MATCH_QUARTERS].to_numpy(dtype=float))
    total=np.log1p(geo['pre_total'].to_numpy(dtype=float))
    feature=np.column_stack([train.mean(axis=1), train[:,-1]-train[:,0],total])
    scale=feature.std(axis=0);scale[scale<1e-10]=1
    z=(feature-feature.mean(axis=0))/scale
    features=pd.DataFrame(z,index=geo.index)
    treated=geo.loc[geo.new_distance_m.le(radius)]
    controls=geo.loc[geo.new_distance_m.ge(1000)&geo.new_distance_m.le(5000)]
    used=set();pairs=[];excluded=[]
    for market in sorted(treated.index):
        row=geo.loc[market]
        candidates=controls.loc[(controls.market_type==row.market_type)&
            (controls.existing_distance_m.le(500)==(row.existing_distance_m<=500))]
        candidates=candidates.loc[~candidates.index.isin(used)]
        if len(candidates)<n_controls:
            excluded.append({'market_code':market,'reason':'동일 유형·기존 역 접근 조건의 비교군 부족'});continue
        distances=((features.loc[candidates.index]-features.loc[market])**2).mean(axis=1).pow(.5)
        ordered=distances.sort_values(kind='stable').head(n_controls)
        # 극단적으로 다른 상권을 억지로 붙이지 않는다. 사전 고정 RMS z 거리 1.0.
        if float(ordered.max())>1.0:
            excluded.append({'market_code':market,'reason':'개통 전 특성 차이가 사전 허용 거리 초과'});continue
        selected=ordered.index.tolist();used.update(selected)
        pairs.append({'treated':market,'controls':selected,'station_id':str(row.nearest_station),
                      'max_match_distance':float(ordered.max())})
    return pairs,complete,features,excluded


def estimate_comparison(panel, geography, radius=500, draws=2000):
    pairs,complete,features,excluded=matched_pairs(panel,geography,radius)
    if not pairs:
        return {'status':'no_matches','radius_m':radius,'pairs':[],'excluded':excluded},pd.DataFrame(),pd.DataFrame()
    dates=PRE_QUARTERS+POST_QUARTERS
    pair_events=[];pair_summary=[];clusters=[];balance=[]
    for pair in pairs:
        treated=complete.loc[pair['treated']]
        control=complete.loc[pair['controls']].mean(axis=0)
        # 비교 상권별 log 값을 먼저 계산하고 두 상권을 같은 가중치로 평균한다.
        control_log=np.log1p(complete.loc[pair['controls']]).mean(axis=0)
        treated_log=np.log1p(treated)
        gaps=treated_log-control_log
        baseline=float(gaps[PRE_QUARTERS].mean())
        effect=float(gaps[POST_QUARTERS].mean()-baseline)
        placebo=float(gaps['20221']-gaps[MATCH_QUARTERS].mean())
        clusters.append(pair['station_id'])
        # 2025년은 제외하고 2022Q3~2024년의 차이로 마지막 연도 재현을 점검한다.
        train_post=[q for q in POST_QUARTERS if not q.startswith('2025')]
        learned=float(gaps[train_post].mean()-baseline)
        holdout=[q for q in POST_QUARTERS if q.startswith('2025')]
        actual_gap=gaps[holdout]-baseline
        pair_summary.append({'market_code':pair['treated'],'station_id':pair['station_id'],
            'controls':'|'.join(pair['controls']),'effect_log':effect,'placebo_log':placebo,
            'pre_mean_count':float(treated[PRE_QUARTERS].mean()),
            'post_mean_count':float(treated[POST_QUARTERS].mean()),
            'holdout_no_shift_mae':float(actual_gap.abs().mean()),
            'holdout_shift_mae':float((actual_gap-learned).abs().mean())})
        for q in dates:
            pair_events.append({'market_code':pair['treated'],'station_id':pair['station_id'],'quarter':q,
                'treated_count':float(treated[q]),'control_mean_count':float(control[q]),
                'gap_from_pre_log':float(gaps[q]-baseline)})
        balance.append((features.loc[pair['treated']]-features.loc[pair['controls']].mean()).to_numpy())
    details=pd.DataFrame(pair_summary)
    lo,hi=cluster_interval(details.effect_log,clusters,draws)
    plo,phi=cluster_interval(details.placebo_log,clusters,draws)
    effect=float(details.effect_log.mean());placebo=float(details.placebo_log.mean())
    balance_max=float(np.max(np.abs(np.mean(balance,axis=0))))
    events=pd.DataFrame(pair_events)
    event_rows=[]
    for quarter,part in events.groupby('quarter',sort=True):
        elo,ehi=cluster_interval(part.gap_from_pre_log,part.station_id,draws)
        event_rows.append({'quarter':quarter,'effect_pct':float(np.expm1(part.gap_from_pre_log.mean())*100),
            'low_pct':float(np.expm1(elo)*100),'high_pct':float(np.expm1(ehi)*100),
            'treated_mean':float(part.treated_count.mean()),'control_mean':float(part.control_mean_count.mean())})
    summary={'status':'estimated','radius_m':radius,'matched_markets':len(pairs),'control_markets':len(pairs)*2,
        'station_clusters':len(set(clusters)),'effect_pct':float(np.expm1(effect)*100),
        'low_pct':float(np.expm1(lo)*100),'high_pct':float(np.expm1(hi)*100),
        'placebo_pct':float(np.expm1(placebo)*100),'placebo_low_pct':float(np.expm1(plo)*100),
        'placebo_high_pct':float(np.expm1(phi)*100),'max_pre_feature_imbalance':balance_max,
        'pre_check_flag':not (plo<=0<=phi) or balance_max>.25,
        'holdout_no_shift_mae':float(details.holdout_no_shift_mae.mean()),
        'holdout_shift_mae':float(details.holdout_shift_mae.mean()),
        'pairs':pairs,'excluded':excluded}
    return summary,pd.DataFrame(event_rows),details
