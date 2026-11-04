"""후보 저장과 검토 승인을 분리한 로컬 관리 화면."""
import pandas as pd
import hashlib
import streamlit as st
import streamlit.components.v1 as components
from dashboard_data import BASE_DIR
from tram_analysis import load_stations
from coordinate_registry import extend,candidate,approve,save,digest,CHECKS,STATUSES


def coordinate_editor():
    st.subheader('정거장 좌표 등록·검토')
    st.caption('후보 저장만으로 분석을 활성화하지 않습니다. PDF·지도 대조 5개 항목을 확인한 뒤 별도로 승인하세요. 이 화면은 로컬 프로젝트 파일을 수정합니다.')
    path=BASE_DIR/'data/tram_stations.csv'; sha=digest(path); frame=extend(load_stations(path))
    names=frame.set_index('station_id').station_name.to_dict()
    sid=st.selectbox('등록할 정거장',frame.station_id.tolist(),format_func=lambda x:f'{x} · {names[x]}',key='coord_station')
    row=frame.loc[frame.station_id.eq(sid)].iloc[0]; prefix='coord_'+sid
    st.write('현재 상태: '+STATUSES.get(row.coordinate_status,row.coordinate_status))
    a,b=st.columns(2)
    with a:
        st.image(str(BASE_DIR/f'data/tram_reference/station_{sid}.png'),caption=f'공식 상세위치 PDF {row.source_page}페이지',width='stretch')
    with b:
        # 미확보 상태의 지도는 대전 전체를 보며, 입력란에는 임의 중심점을 넣지 않는다.
        if row.coordinate_status!='unavailable':
            url=f'https://www.openstreetmap.org/export/embed.html?bbox={float(row.longitude)-.003}%2C{float(row.latitude)-.002}%2C{float(row.longitude)+.003}%2C{float(row.latitude)+.002}&layer=mapnik&marker={row.latitude}%2C{row.longitude}'
        else: url='https://www.openstreetmap.org/export/embed.html?bbox=127.25%2C36.25%2C127.48%2C36.43&layer=mapnik'
        components.iframe(url,height=300)
        st.markdown('[지도 검색·좌표 선택 열기](https://www.openstreetmap.org/) · © [OpenStreetMap 기여자](https://www.openstreetmap.org/copyright)')
        st.caption('지도에서 우클릭 → 주소 보기로 경위도를 확인한 뒤 아래에 직접 입력하세요. PDF의 승강장 구간을 골라야 하며 시설 대표점을 사용하면 안 됩니다.')
    with st.form(prefix+'_candidate'):
        a,b=st.columns(2)
        lat=a.text_input('위도',value=str(row.latitude),key=prefix+'_lat')
        lon=b.text_input('경도',value=str(row.longitude),key=prefix+'_lon')
        source=st.text_input('지도·좌표 출처',value=row.coordinate_source if row.coordinate_status!='unavailable' else '')
        map_url=st.text_input('대조한 지도 주소',value=row.map_url)
        road=st.text_input('도로명',value=row.road_name)
        junction=st.text_input('인접 교차로',value=row.intersection)
        platform=st.text_input('승강장 예정 구간·주변 시설의 상대 위치',value=row.platform_description)
        method=st.text_input('확인 방법',value=row.verification_method)
        note=st.text_area('검토 메모·PDF와 지도 차이',value=row.reviewer_note)
        uncertainty=st.text_input('추정 오차(m) · 근거 없으면 빈값',value=str(row.estimated_uncertainty_m))
        basis=st.text_input('오차 산정 근거',value=row.uncertainty_basis)
        submitted=st.form_submit_button('후보 좌표 저장 · 재검토 필요 상태')
    if submitted:
        try:
            updated=candidate(frame,sid,lat,lon,source,method,note,map_url,uncertainty,basis,
                              road_name=road,intersection=junction,platform_description=platform)
            save(updated,path,sha,'후보 입력·수정',sid)
            st.success('후보 좌표를 저장했습니다. 아래 검토 단계에서 승인해 주세요.');st.rerun()
        except (ValueError,OSError) as exc: st.error(str(exc))
    revision=hashlib.sha256(row.to_json(force_ascii=False).encode('utf-8')).hexdigest()[:16]
    review_key=prefix+'_review_'+revision
    with st.form(review_key):
        st.markdown('**저장된 후보의 PDF·지도 대조 검토**')
        labels=['도로가 PDF와 일치함','교차로와 도로 구간이 일치함','주요 시설의 상대적 위치가 일치함',
                '점이 실제 도로 위의 승강장 예정 구간에 해당함','PDF와 현재 지도 차이·불확실성을 메모에 기록함']
        checks={key:st.checkbox(label,key=review_key+'_'+key) for key,label in zip(CHECKS,labels)}
        reviewer=st.text_input('검토자',key=review_key+'_reviewer')
        accepted=st.form_submit_button('지도 대조 근사 좌표로 승인',disabled=row.coordinate_status!='manual_review_required')
    if accepted:
        try:
            updated=approve(frame,sid,reviewer,checks);save(updated,path,sha,'지도 대조 승인',sid)
            st.success('검토를 완료했습니다. 반경 분석에 사용할 수 있습니다.');st.rerun()
        except (ValueError,OSError) as exc: st.error(str(exc))
    st.caption('수정 전후 CSV와 변경 기록은 data/tram_coordinate_history에 보관합니다. 수동 등록 화면에서는 공식 좌표로 승격하지 않습니다.')
