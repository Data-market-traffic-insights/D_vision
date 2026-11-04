"""신규 접근권 메뉴. 기존 지도·추천 흐름과 분리하며 서버 파일을 쓰지 않는다."""
import hashlib
import html
import numpy as np
import pydeck as pdk
import streamlit as st
from ui_labels import TABLE_LABELS
from dashboard_data import BASE_DIR,data_signature,map_points
from tram_analysis import circle_polygon,verified_stations
from tram_access_change import load_metro_stations,distance_index,access_summary,TITLE,CATEGORIES,ACCESS_COLORS

@st.cache_data(show_spinner='1호선과 트램 정거장까지의 직선거리를 비교하고 있습니다…',max_entries=2)
def cached_distances(signature,metro_digest,station_digest,_shops,_metro,_stations):
    return distance_index(_shops,_metro,_stations)


def access_change_page(data,stations):
    st.subheader(TITLE)
    st.caption('계획 노선 기준 분석입니다. 승인된 트램 근사점의 반경 안에 있으면서 기존 1호선 모든 역의 같은 반경 밖에 있는 현재 상가를 찾습니다. 행정동 전체를 신규 접근권으로 분류하지 않습니다.')
    try:
        metro,meta=load_metro_stations()
        index=cached_distances(data_signature(),meta['csv_sha256'],hashlib.sha256(stations.to_csv(index=False).encode()).hexdigest(),data['shops'],metro,stations)
    except (OSError,ValueError,KeyError) as exc:
        st.warning('1호선 전체 역 좌표 또는 승인된 트램 좌표를 확인할 수 없습니다. 신규 접근권 비교는 잠시 이용할 수 없으며, 현재 상권·트램 분석·추천 메뉴는 계속 이용할 수 있습니다.')
        return
    radius=st.radio('1호선·트램에 함께 적용할 반경(m)',[300,500],index=1,horizontal=True,key='access_change_radius')
    result=access_summary(data['shops'],index,radius,data['industries'])
    counts=result['counts'];new=result['candidates']
    columns=st.columns(3)
    columns[0].metric('신규 접근권 편입 후보 상가',f'{len(new):,}개')
    columns[1].metric('기존 1호선 접근권 상가',f'{counts.iloc[0]+counts.iloc[1]:,}개')
    columns[2].metric('승인된 트램 접근권 상가',f'{counts.iloc[1]+counts.iloc[2]:,}개')
    st.caption(f'기존 1호선 {len(metro)}개 역 · 트램 {len(index["station_ids"])}개 정거장 · 트램 {radius}m 이내 · 기존 1호선 {radius}m 초과 · 업소번호 기준 중복 제거 · 좌표 제외 {counts.iloc[4]:,}개')
    st.info('현재 상가와 계획된 교통망의 공간적 관계를 비교합니다. 직선거리 반경은 실제 보행거리·시간이나 경제적 영향 범위가 아닙니다. 버스 등 다른 교통수단은 반영하지 않았으며 미래 매출·유동인구·창업 성공을 예측하지 않습니다. 트램은 전체 45개 중 검토된 5개 근사점만 사용합니다.')
    selection=st.multiselect('지도에 표시할 접근권 구분',CATEGORIES[:3],default=CATEGORIES[:3],key='access_change_categories')
    show_rings=st.checkbox('역·정거장의 직선거리 반경 표시',value=True,key='access_change_rings')
    selected=result['shops'].loc[result['shops']['접근권구분'].isin(selection)]
    points,_,_=map_points(selected,3000)
    rows=[]
    for row in points.to_dict('records'):
        rows.append({'position':[float(row['경도']),float(row['위도'])],'name':html.escape(str(row['상호명'])),'detail':html.escape(f"{row['상권업종대분류명']} · {row['접근권구분']}"),'color':ACCESS_COLORS[row['접근권구분']]})
    layers=[]
    tram=verified_stations(stations)
    if show_rings:
        for frame,color,key in [(metro,[38,105,190],'metro'),(tram,[137,80,170],'tram')]:
            rings=[{'polygon':circle_polygon(r.latitude,r.longitude,radius),'name':html.escape(str(r.station_name)),'detail':f'{"기존 1호선 공식 대표점" if key=="metro" else "계획 트램 지도 대조 근사점"} · {radius}m 직선거리'} for r in frame.itertuples(index=False)]
            layers.append(pdk.Layer('PolygonLayer',rings,id=f'access_{key}_rings',get_polygon='polygon',get_fill_color=color+[12],get_line_color=color+[180],line_width_min_pixels=1,pickable=True))
    layers.append(pdk.Layer('ScatterplotLayer',rows,id='access_shops',get_position='position',get_fill_color='color',get_radius=6,radius_min_pixels=2,radius_max_pixels=5,pickable=True))
    for frame,color,key in [(metro,[38,105,190],'metro'),(tram,[137,80,170],'tram')]:
        markers=[{'position':[float(r.longitude),float(r.latitude)],'name':html.escape(str(r.station_name)),'detail':'1호선 공식 대표점' if key=='metro' else '계획 트램 · 지도 대조 근사점'} for r in frame.itertuples(index=False)]
        layers.append(pdk.Layer('ScatterplotLayer',markers,id=f'access_{key}_stations',get_position='position',get_fill_color=[255,255,255],get_line_color=color,stroked=True,line_width_min_pixels=3,get_radius=8,radius_units='pixels',pickable=True))
    st.markdown(' · '.join(f'<span style="color:rgb({",".join(map(str,ACCESS_COLORS[key]))})">● {html.escape(key)}</span>' for key in CATEGORIES[:3]),unsafe_allow_html=True)
    st.pydeck_chart(pdk.Deck(layers=layers,initial_view_state=pdk.ViewState(latitude=36.35,longitude=127.38,zoom=11),map_style='https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',tooltip={'text':'{name}\n{detail}'}),height=480)
    st.caption(f'지도 표시 {len(points):,}개 / 선택 구분 전체 {len(selected):,}개 · 3,000개를 넘으면 같은 표본을 골라 표시합니다. 지도 필터는 표시할 점만 바꿉니다. 상단 통계와 아래 표는 표본이 아닌 전체 데이터로 계산합니다. 원은 반경, 작은 점은 상가, 테두리 표식은 역·정거장입니다. 접근권 면적을 잘라 계산한 지도는 아닙니다.')
    if selected.empty:st.info('선택한 구분에 표시할 상가가 없습니다. 지도에 표시할 접근권 구분을 선택해 주세요.')
    if new.empty:st.info('선택 반경에서 신규 접근권 편입 후보 상가가 없습니다.')
    a,b=st.columns(2)
    with a:
        st.markdown('**신규 접근권 후보의 현재 업종 구성**')
        st.bar_chart(result['industry'].set_index('업종')['상가수'])
        st.dataframe(result['industry'][['업종','상가수','비율(%)']],hide_index=True,width='stretch',column_config=TABLE_LABELS)
    with b:
        st.markdown('**트램 정거장별 신규 후보 상가 수**')
        st.dataframe(result['stations'].sort_values('신규 후보 상가수',ascending=False),hide_index=True,width='stretch',column_config=TABLE_LABELS)
        st.caption('여러 정거장 반경에 속하는 상가는 각 정거장에 함께 집계됩니다. 상단 전체 후보 수에서는 중복을 제외하므로 정거장별 수의 합과 다를 수 있습니다.')
        st.markdown('**행정동별 신규 후보 상가 수**')
        st.dataframe(result['admin'],hide_index=True,width='stretch',column_config=TABLE_LABELS)
    with st.expander('후보 상가·업종·관련 정거장 확인'):
        st.dataframe(new[['상호명','상권업종대분류명','행정동명','관련 트램 정거장']],hide_index=True,width='stretch',column_config=TABLE_LABELS)
    with st.expander('1호선 좌표 출처·검증과 해석 범위'):
        st.markdown(f'[국가철도공단 철도산업정보센터 공식 역사정보]({meta["source_url"]}) · [대전교통공사 운영 역 수 대조]({meta["operator_check_url"]}) · [행정안전부 좌표 표준]({meta["standard_url"]})')
        st.write(f'{meta["title"]} / 개별 역 기준일 {meta["record_date"]} / WGS84(EPSG:4326) / 101~122번 22개 역의 번호·명칭·중복·누락과 경위도 범위 검사. 원본 경위도를 그대로 사용합니다.')
        st.caption(meta['coordinate_basis'])
        st.caption('1호선은 공식 대표점, 트램은 지도 대조 근사점으로 위치 기준과 정확도가 다릅니다. 특히 반경 경계 상가는 좌표 오차에 따라 포함 여부가 달라질 수 있습니다. 실제 보행 경로와 개통 후 효과는 검증하지 않았습니다.')
