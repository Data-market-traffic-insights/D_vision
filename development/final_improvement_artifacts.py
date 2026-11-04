# -*- coding: utf-8 -*-
"""보완 단계의 실제 추천 예시·현재값 강조 카드·보존 지문을 저장한다."""
import hashlib
import json
import pandas as pd
from dashboard_data import BASE_DIR,load_dashboard_data
from tram_analysis import load_stations,verified_stations
from prototype_logic import scoped_recommendations,TRAM_SCOPES,PRIORITIES
from tram_scenarios import radius_profile,scenario_visuals,SCENARIOS


def build():
    out=BASE_DIR/'results/final_improvement_20261104'
    data=load_dashboard_data();stations=load_stations()
    for scope,name in zip(TRAM_SCOPES,['selected_225_500m_food','global_500m_food']):
        result=scoped_recommendations(data,stations,'음식',[PRIORITIES[3]],500,scope,'225')
        result.to_csv(out/(name+'.csv'),index=False,encoding='utf-8-sig')
        print(name+': '+str(len(result))+'개 후보, 최대 5개 표시')
    station=stations.loc[stations.station_id.eq('225')].iloc[0]
    result=radius_profile(data,station,500)
    cards=[dict(시나리오=s,**scenario_visuals(result,'음식',s)) for s in SCENARIOS]
    (out/'scenario_current_cards.json').write_text(json.dumps(cards,ensure_ascii=False,indent=2),encoding='utf-8')
    baseline=json.loads((out/'baseline_manifest.json').read_text(encoding='utf-8'))
    checks={f:hashlib.sha256((BASE_DIR/f).read_bytes()).hexdigest()==sha for f,sha in baseline.items()}
    previous=json.loads((BASE_DIR/'results/tram_expansion/analysis_metadata.json').read_text(encoding='utf-8'))
    cluster_checks={f:hashlib.sha256((BASE_DIR/f).read_bytes()).hexdigest()==sha
                    for f,sha in previous['input_sha256'].items() if f.startswith('results/')}
    audit={'baseline_unchanged':checks,'previous_cluster_outputs_unchanged':cluster_checks,
           'shop_count':len(data['shops']),'admin_count':len(data['admin']),
           'approved_stations':verified_stations(stations).station_id.tolist(),
           'separate_pending_candidate_ids':['217'],
           'input_sha256':{f:hashlib.sha256((BASE_DIR/f).read_bytes()).hexdigest() for f in baseline}}
    (out/'preservation_check.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':build()
