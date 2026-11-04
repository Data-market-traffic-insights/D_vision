# -*- coding: utf-8 -*-
"""실제 브라우저에서 고른 좌표 후보·대조 자료만 저장한다. 운영 승인 없음."""
import json
import pandas as pd
from dashboard_data import BASE_DIR
from coordinate_registry import candidate
from tram_analysis import load_stations,verified_stations

OUT=BASE_DIR/'results/station_final_review_20261104'
# 좌표는 OSM 화면 우클릭→주소 보기에서 읽었다. 시설/상가 좌표는 초기 지도 이동에만 사용.
POINTS=[
    ('217',36.357694,127.388427,'한밭대로','샘머리네거리 동쪽~모정네거리 서쪽',
     '샘머리공원 북측, 캠코캐피탈타워·주차타워와 사학연금회관 사이 북측 진입로에 대응하는 상대식 승강장 두 구간의 통합 근사 중심',
     '기존 후보 재검토. 도면 p19의 서쪽 교차로·동쪽 교차로·공원·북측 블록 및 중앙 진입로 상대 위치를 대조. 기존 후보를 유지하되 자동 승인하지 않음.'),
    ('202',36.322062,127.411387,'계백로','서대전네거리 서쪽 · 공원 북측 횡단부 서측',
     '서대전공원 북측·제일가구프라자 남측, 도면 중앙 횡단부 서쪽의 양방향 상대식 승강장 근사 중심',
     '교차로 중심이 아닌 서쪽 중간 구간을 선택. 북측 제일가구프라자, 남측 공원과 남서측 CBS·공원 진입로의 상대 위치를 대조.'),
    ('233',36.301257,127.335545,'계백로','관저네거리 동쪽, 관저지하차도 남측',
     '관저지하차도 본선 남쪽·파워존쇼핑몰 북측, 북쪽에서 돌아오는 트램 선로가 직선으로 바뀐 뒤의 상대식 두 승강장 통합 근사 중심',
     '도면 p35의 북→동 곡선·지하차도·남동쪽 쇼핑몰 블록을 대조. 원앙네거리와 구분. 지도 주소 결과의 지하차도 피처 위치와 직접 클릭한 도로 남쪽 후보점을 구분함.'),
    ('238',36.313984,127.381904,'계백로','도마네거리 북동쪽, 도마2길 접속부 동쪽',
     '북측 아디다스 남서쪽·원셀프안경 인접, 남측 도마e편한세상포레나아파트 북쪽, 도면 횡단부 남서측 승강장 구간 근사 중심',
     '교차로 이름이나 아디다스 시설 좌표 대신 계백로 도로 위를 선택. 북측 골목망·남측 아파트·남서측 백제금산인삼농협 블록을 도면과 대조.'),
    ('220',36.368256,127.379587,'대덕대로','도면 만년들네거리 북쪽, 초원아파트 동측',
     '초원아파트 103·105동 동쪽 진입부/보도교 남쪽과 동측 만년로67번길 접속부 사이, 남북 상대식 승강장 통합 근사 중심',
     '교차로 중심을 사용하지 않음. 도면의 아파트 동측 진입로·맞은편 골목과 남쪽 교차로 관계를 대조. OSM의 교차로 명칭과 도면/네이버 명칭 차이는 번호·도로 구조·아파트로 구분함.')
]


def build():
    stations=load_stations();rows=[]
    for sid,lat,lon,road,junction,platform,note in POINTS:
        url=f'https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=18/{lat:.6f}/{lon:.6f}'
        staged=candidate(stations,sid,lat,lon,'공식 정거장 상세위치 PDF + OpenStreetMap 실제 도로 지도',
            '공식 도면 승강장 구간·교차로·건물/공원 대조 후 도로 위 점을 수동 선택하고 OSM 주소 보기 경위도를 읽음',
            note+' 예정 위치 변경·지도 표현·도면 지리참조 부재에 따른 불확실성은 남음. 정량 오차 미산정. 사용자 검토·승인 전 분석 제외.',
            url,road_name=road,intersection=junction,platform_description=platform)
        row=staged.loc[staged.station_id.eq(sid)].iloc[0].to_dict()
        row.update(신뢰도='C',분석허용=False,기록일='2026-11-04',기록자='코드 에이전트 · 지도 대조와 후보 기록만 수행',
                   승인상태='사용자 요청으로 후보 유지 · 추가 검토 필요 · 승인 이력 미생성',지도증빙=f'{sid}_map.png' if sid!='217' else '217_map_recheck.png')
        rows.append(row)
    frame=pd.DataFrame(rows)
    assert verified_stations(frame).empty
    frame.to_csv(OUT/'coordinate_candidates.csv',index=False,encoding='utf-8-sig')
    (OUT/'candidate_review.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    text='# 정거장 좌표 후보 검토 자료\n\n'
    text+='**아래 5개는 아직 C·미승인입니다.** 기존 승인 5개와 운영 좌표 CSV는 변경하지 않았습니다. 217번은 기존 후보 재검토, 나머지 4개는 이번에 새로 선정한 후보입니다.\n\n'
    text+='사용자 검토 결정: **“추가 검토가 필요하니 후보로 유지”**. 이 결정에 따라 5개 모두 운영 분석에서 제외하고 승인자·승인일·승인 증거를 비워 두었습니다.\n\n'
    text+='승인을 위해서는 각 점의 ①도로 ②교차로/구간 ③시설 상대 위치 ④예정 승강장 구간 ⑤현재 지도와 도면 차이 기록을 검토자가 확인해야 합니다. 도로·시설 대조와 수동 점 선정은 수행했지만, 이것이 사용자 승인 이력을 대신하지 않습니다.\n\n'
    text+='공식 측량 좌표가 아닌 지도 대조 근사점 후보입니다. 정량 오차는 산정하지 않았습니다. 검색 결과의 파란 피처 핀은 주변 주소일 수 있으며, 경위도 검색란과 직접 클릭한 점(빨간 핀)을 구별해야 합니다. 아래 지도 링크는 후보 좌표를 핀으로 직접 표시합니다.\n\n'
    for row in rows:
        sid=row['station_id'];page=row['source_page']
        text+=f"## {sid} {row['station_name']}\n\n"
        text+=f"- 후보: **{row['latitude']:.6f}, {row['longitude']:.6f}** · 공식 PDF {page}페이지\n"
        text+=f"- 도로/교차로: {row['road_name']} / {row['intersection']}\n"
        text+=f"- 예정 구간: {row['platform_description']}\n- 대조·차이: {row['reviewer_note']}\n"
        text+=f"- [후보점을 실제 지도에서 확인]({row['map_url']})\n\n"
        image='217_map_recheck.png' if sid=='217' else sid+'_map.png'
        pdf='../final_improvement_20261104/pdf217_detail.png' if sid=='217' else sid+'_pdf_detail.png'
        text+=f'![공식 도면의 예정 승강장 구간]({pdf})\n\n![실제 지도에서 선택한 후보점]({image})\n\n'
    (OUT/'후보좌표_검토자료.md').write_text(text,encoding='utf-8')
    print('미승인 후보 5개(기존 1 + 신규 4), 운영 CSV 변경 없음')


if __name__=='__main__':build()
