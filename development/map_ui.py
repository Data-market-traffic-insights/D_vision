"""3종 지도 UI. 입력 파일과 선택 조건 기준 캐싱, 분석 값은 전체 필터 기준."""
import html
import pandas as pd
import streamlit as st
import plotly.express as px
from dashboard_data import data_signature,select_shops,map_points,industry_profile,COLORS,TYPES
from map_visualization import INDUSTRY_COLORS,MODES,admin_representatives,build_map


@st.cache_data(show_spinner=False,max_entries=1)
def representatives(signature,_shops,_admin,industries):
    return admin_representatives(_shops,_admin,industries)


@st.cache_data(show_spinner=False,max_entries=12)
def preview(signature,conditions,limit,_filtered):
    return map_points(_filtered,limit)


def legend(colors):
    badges=' '.join('<span style="display:inline-block;margin:4px 12px 4px 0"><span style="display:inline-block;width:12px;height:12px;border:1px solid #526574;background:'+color+'"></span> '+html.escape(str(name))+'</span>' for name,color in colors.items())
    st.markdown(badges,unsafe_allow_html=True)


def open_admin(code,gu):
    st.session_state['navigation']='지역별 상세 분석'
    st.session_state['detail_basis']='행정동'
    st.session_state['region_gu']=gu
    st.session_state['region_dong_'+gu]=code


def pick_admin():
    objects=st.session_state.get('map_cluster_deck',{}).get('selection',{}).get('objects',{}).get('admin_clusters',[])
    if objects:
        code=objects[0].get('행정동코드')
        if code in st.session_state.get('map_allowed_admins',[]):
            st.session_state['map_admin_choice']=code


def render(data,gu,dong):
    st.subheader('상가 분포 지도')
    mode=st.radio('지도 유형',MODES,horizontal=True,key='map_mode')
    if mode==MODES[2]:
        st.caption('82개 행정동의 업종 구성과 상가 규모를 기반으로 분류한 기존 K=3 상권 유형을 표시합니다.')
        cluster_map(data,gu,dong)
        return
    st.caption('상가가 많이 분포한 지역을 같은 색 점의 겹침과 진하기로 표현합니다. 정량적인 밀도 추정값은 아닙니다.' if mode==MODES[0] else '업종별 상가 위치를 서로 다른 고정 색상으로 표시합니다.')
    a,b,c=st.columns(3)
    industry=a.selectbox('지도 업종 대분류',['전체']+data['industries'],key='map_industry')
    possible=data['shops'] if industry=='전체' else data['shops'].loc[data['shops']['상권업종대분류명'].eq(industry)]
    medium=b.selectbox('지도 업종 중분류',['전체']+sorted(possible['상권업종중분류명'].dropna().unique()),key='map_medium_'+industry)
    limit=c.selectbox('지도 표시 상한',[1000,3000,5000,10000],index=1,key='map_limit')
    enabled=st.multiselect('표시할 업종 선택·해제',data['industries'],default=data['industries'],key='map_enabled_industries')
    st.caption('왼쪽 자치구·행정동, 대분류·중분류와 선택한 업종을 함께 적용합니다. 업종을 모두 해제하면 빈 결과를 표시합니다.')
    filtered=select_shops(data['shops'],gu,dong,industry,medium)
    filtered=filtered.loc[filtered['상권업종대분류명'].isin(enabled)]
    points,excluded,located=preview(data_signature(),(gu,dong,industry,medium,tuple(enabled)),limit,filtered)
    a,b,c=st.columns(3)
    a.metric('조건에 맞는 전체 상가',f'{len(filtered):,}개')
    b.metric('지도 표시 점',f'{len(points):,}개')
    c.metric('좌표 제외',f'{excluded:,}개')
    st.caption(f'전체 집계 {len(filtered):,}개 · 좌표 유효 {located:,}개 · 지도 표시 {len(points):,}개. 상한 초과 시 난수 42 고정 표본이며, 희소 업종이 표본에 없을 수 있습니다. 표·그래프·다운로드는 전체 필터 결과입니다.')
    if mode==MODES[1]: legend({i:INDUSTRY_COLORS[i] for i in data['industries'] if i in enabled and (industry=='전체' or i==industry)})
    else:
        legend({'상가 위치 · 겹칠수록 진하게 표시':'#127C80'})
    show_tram=st.checkbox('확인된 트램 정거장 표시',value=False,key='map_show_tram')
    stations=None
    if show_tram:
        from stage3_ui import get_stations
        from tram_analysis import verified_stations
        stations=verified_stations(get_stations())
        st.caption(f'◎ 흰색·짙은 테두리의 표적형 마커: 전체 45곳 중 확인된 {len(stations)}곳만 표시합니다. 지도 대조 근사 좌표이며 공식 측량 좌표가 아닙니다. 지역·업종 필터와 별도의 참고 계층입니다.')
    if points.empty: st.info('선택한 지역과 업종에 해당하는 유효한 상가 좌표가 없습니다. 필터를 변경해 주세요.')
    if len(points) or stations is not None:
        st.pydeck_chart(build_map(points,mode,stations),height=520)
        st.caption('CARTO / OpenStreetMap · 인터넷 연결 필요 · 확대·축소 가능 · 점에 마우스를 올리면 상가명과 업종이 표시됩니다.')
    profile=industry_profile(filtered,data['industries'])
    fig=px.bar(profile,x='상가수',y='업종',color='업종',orientation='h',color_discrete_map=INDUSTRY_COLORS)
    fig.update_layout(showlegend=False,height=380,margin=dict(l=0,r=0,t=20,b=10))
    st.subheader('현재 조건의 업종별 상가 수')
    st.plotly_chart(fig,config={'displaylogo':False})
    st.caption('지도 표본이 아닌 전체 필터 결과입니다.')
    cols=['상호명','시군구명','행정동명','상권업종대분류명','상권업종중분류명','도로명주소']
    st.subheader('현재 조건의 상가 목록')
    st.dataframe(filtered[cols].head(200),hide_index=True,width='stretch')
    st.caption(f'화면 목록 최대 200개 · 전체 다운로드 {len(filtered):,}개')
    st.download_button('지도조건 전체 상가 CSV 다운로드',filtered[cols].to_csv(index=False).encode('utf-8-sig'),'지도조건_전체상가.csv','text/csv',key='map_download')


def cluster_map(data,gu,dong):
    st.info('K-means는 개별 상가가 아닌 행정동 단위 분석입니다. 점 색은 해당 행정동의 기존 군집이며, 개별 상가의 군집을 뜻하지 않습니다.')
    st.caption('검증된 행정동 경계 GeoJSON이 없어 대표점 방식을 사용합니다. 동별 상가 좌표 중앙값에 가장 가까운 실제 상가 점을 택했습니다. 공식 중심점·행정동 영역·상가 집중 지점을 뜻하지 않습니다. 업종 필터는 군집·대표점 위치를 바꾸지 않습니다.')
    table=representatives(data_signature(),data['shops'],data['admin'],tuple(data['industries']))
    shown=table.copy()
    if gu!='전체': shown=shown.loc[shown['시군구명'].eq(gu)]
    if dong!='전체': shown=shown.loc[shown['행정동코드'].eq(dong)]
    a,b,c=st.columns(3)
    a.metric('전체 분석 행정동',f'{len(table)}개');b.metric('지역 필터 행정동',f'{len(shown)}개')
    c.metric('대표점 표시',f'{shown.lat.notna().sum()}개')
    legend({f'군집 {k} · {TYPES[k]}':COLORS[k] for k in TYPES})
    st.session_state['map_allowed_admins']=shown['행정동코드'].tolist()
    st.pydeck_chart(build_map(shown,MODES[2]),height=520,key='map_cluster_deck',on_select=pick_admin,selection_mode='single-object')
    st.caption('동일한 크기의 점으로 표시합니다. 점에 마우스를 올리면 행정동명·군집·전체 상가 수·주요 업종을 확인할 수 있습니다. 점을 클릭하거나 아래 목록에서 행정동을 선택해 상세 분석으로 이동하세요.')
    if shown.empty: st.info('선택한 지역에 해당하는 행정동이 없습니다.');return
    labels=shown.set_index('행정동코드')['지역표시'].to_dict()
    code=st.selectbox('지도에서 살펴볼 행정동',shown['행정동코드'].tolist(),format_func=labels.get,key='map_admin_choice')
    row=shown.loc[shown['행정동코드'].eq(code)].iloc[0]
    st.write(f"{row['지역표시']} · 군집 {int(row['군집'])} · 상가 {int(row['전체상가수']):,}개 · 주요 업종 {row['주요업종']}")
    st.button('선택 행정동 상세 분석으로 이동',on_click=open_admin,args=(code,row['시군구명']),key='map_admin_detail')
    st.dataframe(shown[['행정동코드','지역표시','군집','잠정유형','전체상가수','주요업종']],hide_index=True,width='stretch')
