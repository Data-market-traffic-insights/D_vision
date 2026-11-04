"""실제 등록 좌표와 원본 상가로 시범 결과를 재생성한다. 좌표를 생성하지 않는다."""
from pathlib import Path
import json
import hashlib
import pandas as pd
from dashboard_data import BASE_DIR,load_dashboard_data,industry_profile,entropy
from tram_analysis import load_stations,verified_stations,radius_shops,covered_shop_ids,admin_access


def build():
    out=BASE_DIR/'results/tram_pilot_20261103';out.mkdir(exist_ok=True)
    data=load_dashboard_data();all_stations=load_stations();stations=verified_stations(all_stations)
    summaries=[];profiles=[]
    for _,station in stations.iterrows():
        for radius in [300,500,1000]:
            shops,excluded=radius_shops(data['shops'],station,radius);profile=industry_profile(shops,data['industries'])
            for _,p in profile.iterrows():
                profiles.append({'station_id':station.station_id,'station_name':station.station_name,'반경(m)':radius,
                                 '업종':p['업종'],'상가수':p['상가수'],'비율(%)':p['비율(%)'],
                                 '밀집도(개/km²)':p['상가수']/(3.141592653589793*(radius/1000)**2)})
            summaries.append({'station_id':station.station_id,'station_name':station.station_name,'좌표상태':station.coordinate_status,
                              '분석기준':'추정 중심점 기준 분석' if station.coordinate_status=='map_verified_approx' else '공식 좌표 기준 분석',
                              '반경(m)':radius,'전체상가수':len(shops),'업종다양성':entropy(profile),
                              '상위5업종':' / '.join(f"{p['업종']} {int(p['상가수'])}개" for _,p in profile.nlargest(5,'상가수').iterrows()),'좌표제외상가수':excluded})
    pd.DataFrame(summaries).to_csv(out/'station_radius_summary.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(profiles).to_csv(out/'station_industry_profiles.csv',index=False,encoding='utf-8-sig')
    stations.to_csv(out/'coordinate_review.csv',index=False,encoding='utf-8-sig')
    pd.concat([admin_access(data['shops'],all_stations,r).assign(**{'반경(m)':r})
               for r in [300,500,1000]],ignore_index=True).to_csv(out/'admin_tram_access.csv',index=False,encoding='utf-8-sig')
    summary={'shop_count':len(data['shops']),'status_counts':{key:int(all_stations.coordinate_status.eq(key).sum()) for key in ['official','map_verified_approx','manual_review_required','unavailable']},
             'eligible_stations':stations.station_id.tolist(),'union_counts':{str(r):len(covered_shop_ids(data['shops'],all_stations,r) or []) for r in [300,500,1000]},
             'inputs_sha256':{name:hashlib.sha256((BASE_DIR/name).read_bytes()).hexdigest() for name in ['data/daejeon_clean.csv','data/tram_stations.csv']},
             'limitations':['지도 대조 근사점은 공식 측량 좌표가 아님','정량 위치 오차 미산정: 민감도 수치 미계산','직선거리이며 보행 경로 아님','상가 좌표 오차 및 반경 경계 불확실성','매출·성공 가능성·트램 효과의 예측 아님']}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    source_path=BASE_DIR/'data/tram_sources.json';sources=json.loads(source_path.read_text())
    sources.update(verified_coordinates=len(stations),missing_coordinates=int(all_stations.coordinate_status.eq('unavailable').sum()),coordinate_status_counts=summary['status_counts'],phase4_review='results/tram_pilot_20261103/coordinate_review.csv')
    sources.pop('verified_coordinate_count',None);sources.pop('missing_coordinate_count',None)
    sources['map_sources']=['https://www.openstreetmap.org/','https://www.openstreetmap.org/copyright']
    sources['coordinate_policy']='공식 좌표 또는 PDF·실제 지도 대조 근사 좌표만 분석. 정량 오차는 산정 근거가 있을 때만 기록. 시설 대표점 대체 금지.'
    source_path.write_text(json.dumps(sources,ensure_ascii=False,indent=2))
    print(pd.DataFrame(summaries)[['station_id','station_name','반경(m)','전체상가수']].to_string(index=False))
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':build()
