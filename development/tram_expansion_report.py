"""전체 도면 검토 기록과 승인 좌표의 실측 집계 저장. 원본 입력을 쓰지 않는다."""
from pathlib import Path
import hashlib
import json
import pandas as pd
from dashboard_data import BASE_DIR, load_dashboard_data
from tram_analysis import load_stations, admin_access, verified_stations
from tram_scenarios import all_profiles, review_inventory, overlap_summary, SCENARIOS, scenario_explanation

OUT=BASE_DIR/'results/tram_expansion'
# 공식 PDF의 도로·교차로·시설 표기를 육안 확인한 기록. 지명으로 경위도를 추정하지 않는다.
PDF_NOTES={
201:'서대전역네거리 동서 간선도로; 삼성전자서비스 중대전·한신휴플러스보르미1단지 인접',
202:'서대전네거리 서쪽 도로; 서대전공원 북쪽·제일가구프라자 남쪽',
203:'하우스토리1차 남동쪽 사선도로; 드림키즈어린이집·대전중앙교회 서측',
204:'충무로; 현대주택 남쪽·한밭수영장 북쪽·남대전지구대 동쪽',
205:'대전로; 인동네거리 북쪽·인동시장 동쪽·신인동행정복지센터 남서측',
206:'대전로; 중앙시장 횡단 구간 남쪽; 기존 지도 대조 기록 재사용',
207:'신안역사공원 예정지 동측 남북도로; 동광장로 교차부 북쪽·대동천 서측',
208:'동대전로; 대동역 북쪽·계족로 분기 동측·대동4/8구역 서측',
209:'동대전로; 우송삼거리 북쪽·우송대학교 동쪽',
210:'동대전로; 가양네거리 북쪽·가양시장 동쪽·상수도사업본부 동부사업소 남서측',
211:'한밭대로 사선구간; CJ제일제당 충청지사 남서측·복합터미널 접속 교차부 남동측',
212:'한밭대로; 중리네거리 남동측·전자랜드/SFG아울렛 남서측',
213:'한밭대로; 중리시장·한남요양병원 북쪽·S-OIL 남쪽',
214:'대전조차장 남동측 동서도로; 다모아백화점·새시온교회 남쪽·운성모터스 북쪽',
215:'오정농수산물도매시장 남쪽 동서 간선도로; 농협 북쪽·시장 접속 횡단부 서측',
216:'수정타운아파트 남쪽 동서도로; 수정5보도육교 인접·둔산가람아파트 북쪽',
217:'샘머리네거리 동쪽 동서도로; 사학연금회관 남쪽·샘머리공원 북쪽',
218:'한밭대로; 둔산지하차도 남측; 기존 지도 대조 기록 재사용',
219:'정부대전청사 서측 남북도로; 만년삼거리 남쪽·스카이아트빌딩 동쪽',
220:'만년네거리 북쪽 남북도로; 초원아파트 동쪽',
221:'과학공원네거리 서측 곡선부; 국립중앙과학관·과학공원 남측·갑천 다리 접근 구간',
222:'과기원삼거리 동쪽 사선도로; KAIST 남쪽·갑천 북쪽',
223:'대학로; 충대농대삼거리 서쪽·유성대교 북쪽',
224:'대학로; GS 주유소 남동측; 기존 지도 대조 기록 재사용',
225:'도안대로; 유성네거리 남쪽·용반들근린공원 서측; 기존 지도 대조 기록 재사용',
226:'도안5단지네거리 북쪽 남북도로; 홈플러스익스프레스 동측; 도면명 상대정거장',
227:'원골네거리 남쪽 사선도로; 트리풀시티9단지 동측',
228:'대전시립박물관 서측 사선도로; 대전IPARKCITY2단지 동쪽·박물관 접근 횡단부 남쪽',
229:'더샵도안트위넌스1/2단지 동측 남북도로; 도면상 동서 교차로 남쪽',
230:'도안2단계 개발계획지구 사이 남북도로; 도면상 동서 교차로 남쪽',
231:'도안3단계 개발계획지구 동쪽 사선도로; 대정공공지원 민간임대주택 공급촉진지구 서쪽',
232:'원앙네거리 북쪽 남북도로; 대전공공어린이재활병원 동쪽·원앙마을주공1단지 서측',
233:'관저네거리 동쪽 동서도로; 관저지하차도 남쪽·파워존쇼핑몰 북쪽',
234:'계백로; 건양대학교병원 남쪽·병원 앞 횡단부 서쪽; 기존 지도 대조 기록 재사용',
235:'계동아파트네거리 동쪽 동서 사선도로; 가수원클리닉 남동쪽·은아3단지 북측',
236:'정림삼거리 동쪽 사선도로; 서울중앙병원 북쪽·남대전농협 정림지점 북동측',
237:'도마삼거리 동북쪽 사선도로; 현대오일뱅크 북쪽·도마변동12구역 남쪽',
238:'도마네거리 북동쪽 사선도로; 아디다스 남쪽·도마e편한세상포레나아파트 북측',
239:'버드내네거리 서쪽 동서 사선도로; 버드내마을1단지 남쪽·힐스테이트유천더와이즈 북측',
240:'서대전농협 동쪽 동서도로; 더좋은아파트 북쪽·도면상 횡단부 서측',
241:'상아유통상가 동쪽 남북도로; 한밭아파트네거리 남쪽·법2동행정복지센터 남서측',
242:'선비마을1단지 서쪽 남북도로; 법동2재건축 동측·대전대덕소방서 북서측',
243:'읍내동현대아파트 동쪽 남북도로; 체육당 서쪽·읍내정거장 지시선 주변',
244:'메르세데스벤츠 대전전시장 동쪽 남북도로; 대전연축도시개발사업 서쪽',
245:'진잠네거리 북동쪽 곡선도로; 대전진잠기요양센터 남쪽·롯데마트 남서측',
}


def build_review():
    OUT.mkdir(exist_ok=True,parents=True)
    stations=load_stations(); table=review_inventory(stations)
    rows=[]
    for _,s in table.iterrows():
        ok=bool(s.analysis_eligible); sid=str(s.station_id)
        rows.append({'station_id':sid,'station_name':s.station_name,
            'latitude':s.latitude if pd.notna(s.latitude) else '', 'longitude':s.longitude if pd.notna(s.longitude) else '',
            '신뢰도':s['신뢰도'] if s['신뢰도'] in ['A','B'] else 'C',
            '공식도면근거':f'공식 정거장 상세위치 PDF {s.source_page}페이지 · {sid}번',
            'PDF위치단서':PDF_NOTES[int(sid)],
            '지도대조근거':s.map_url if ok else '',
            '좌표확보방법':s.verification_method if ok else 'PDF 육안 검토만 완료 · 좌표 미확보',
            '검토상태':'기존 승인 기록 재사용' if ok else 'PDF 위치 단서 확인 · 실제 지도 대조 및 중심점 승인 미완료',
            '분석허용':ok,'남은불확실성':'공식 측량 좌표 아님 · 정량 오차 미산정 · 반경 경계 변동 가능' if ok else '도로 실명·현행 지도·승강장 중심점 대조 필요; 경위도 공란 유지',
            '후속작업':'공식 좌표 공개 시 재검증' if ok else 'PDF→실제 지도 동일 도로/교차로/시설/승강장 구간 확인→근사점 선정→5개 검사 후 승인'})
    result=pd.DataFrame(rows)
    result.to_csv(OUT/'station_review_45.csv',index=False,encoding='utf-8-sig')
    result.loc[~result['분석허용']].to_csv(OUT/'pending_station_reviews.csv',index=False,encoding='utf-8-sig')
    counts=result['신뢰도'].value_counts();approved=verified_stations(stations)
    (OUT/'1단계_중간보고서.md').write_text(
        '# 전체 정거장 검토 중간보고\n\n45개 번호·명칭 및 PDF 위치 단서 검토를 완료했습니다. '
        + ' / '.join(f'{g} {counts.get(g,0)}개' for g in ['A','B','C','D'])
        + '입니다. C는 PDF에서 대략적인 예정 구간만 식별한 상태로 실제 지도 대조 승인이 아닙니다.\n\n'
        + f'분석 가능 {len(approved)}개: '+ '·'.join(approved.station_id)+'. 등록된 승인 기록을 재사용했습니다. 원본 좌표 CSV를 변경하지 않았습니다.\n\n'
        '공개 OSM 일괄 조회는 DNS/보안 연결 실패 및 curl 조회 실패로 좌표 자료를 받지 못했습니다. '
        '브라우저의 서대전네거리·서대전공원 검색에서도 결과를 얻지 못했습니다. 실패한 검색 화면의 지도 중심을 좌표로 사용하지 않았습니다. '
        '일괄 조회 실패가 다른 공개 자료의 부재를 뜻하지 않습니다.\n\n'
        '기존 CAD 13개 검토에서 좌표계가 확인되지 않았으므로 다시 변환하거나 추정하지 않았습니다. '
        '검토표는 station_review_45.csv, 후속 작업은 pending_station_reviews.csv에 저장했습니다. '
        'C/D는 분석에서 제외하며 지도에도 표시하지 않습니다.\n',encoding='utf-8')
    return result


def build_analysis():
    data=load_dashboard_data();stations=load_stations();profiles=all_profiles(data,stations)
    summaries=[]; industries=[]; admins=[]; scenarios=[]; overlaps=[]; repeated=[]
    for (sid,radius),r in profiles.items():
        base={'station_id':sid,'station_name':r['station_name'],'반경(m)':radius}
        summaries.append(dict(base,전체상가수=r['total'],업종다양성=r['diversity'],업종집중도=r['concentration'],
                              주요업종=' / '.join(r['top3']['업종']),좌표제외상가수=r['excluded']))
        industries.extend(r['profile'].assign(**base).to_dict('records'))
        admins.extend(r['admins'].assign(**base).to_dict('records'))
        for industry in data['industries']:
            for scenario in SCENARIOS:
                scenarios.append(dict(base,업종=industry,시나리오=scenario,**scenario_explanation(r,industry,scenario)))
    for radius in [300,500,1000]:
        summary,memberships=overlap_summary(profiles,radius);overlaps.append(summary)
        repeated.extend({'반경(m)':radius,'상가업소번호':shop,'포함정거장':' / '.join(sorted(ids)), '포함수':len(ids)}
                        for shop,ids in memberships.items() if len(ids)>1)
    for name,rows in [('station_radius_summary',summaries),('station_industry_profiles',industries),
                      ('station_admin_clusters',admins),('scenario_explanations',scenarios),('overlap_summary',overlaps)]:
        pd.DataFrame(rows).to_csv(OUT/(name+'.csv'),index=False,encoding='utf-8-sig')
    pd.DataFrame(repeated,columns=['반경(m)','상가업소번호','포함정거장','포함수']).to_csv(OUT/'overlapping_shops.csv',index=False,encoding='utf-8-sig')
    pd.concat([admin_access(data['shops'],stations,r).assign(**{'반경(m)':r}) for r in [300,500,1000]]).to_csv(OUT/'admin_tram_access.csv',index=False,encoding='utf-8-sig')
    preserved=['app.py','data/daejeon_clean.csv','data/ml_features.csv','data/tram_stations.csv']
    preserved.extend(str(p.relative_to(BASE_DIR)) for p in sorted(data['run_dir'].glob('*')) if p.is_file())
    metadata={'shop_count':len(data['shops']),'admin_count':len(data['admin']),'cluster_count':3,
              'approved_station_count':len(profiles)//3,'radius_results':len(profiles),
              'input_sha256':{p:hashlib.sha256((BASE_DIR/p).read_bytes()).hexdigest() for p in preserved},
              'limitations':['정성적 시나리오이며 미래 예측 아님','추정 중심점 · 정량 오차 미산정','직선거리 · 도보시간 아님',f'분석 미허용 {len(stations)-len(profiles)//3}개는 승인 전까지 제외']}
    (OUT/'analysis_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in metadata.items() if k!='input_sha256'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    build_review();build_analysis()
