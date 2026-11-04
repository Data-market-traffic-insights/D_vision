"""일반 창업자용 D·VISION 최종 시제품 진입점. 기존 app.py와 테스트를 보존한다."""
from pathlib import Path
import html
import numpy as np
import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st
from dashboard_data import load_dashboard_data,data_signature,industry_profile,map_points,COLORS,BASE_DIR
from tram_analysis import load_stations,verified_stations,admin_access,radius_shops,circle_polygon
from map_visualization import build_map,admin_representatives,MODES,INDUSTRY_COLORS
from prototype_logic import FRIENDLY_TYPES,TYPE_NOTES,PRIORITIES,EXPERIENCES,recommendation_table,reasons,experience_note,admin_summary

st.set_page_config(page_title='D·VISION | 내 창업 지역 찾기',page_icon='◈',layout='wide')
PAGES=['대전 상권 지도','상권 상세 분석','내 창업 지역 찾기']

@st.cache_data(show_spinner='대전 상권을 준비하고 있습니다…')
def get_data(signature):return load_dashboard_data()


def station_signature():
    p=BASE_DIR/'data/tram_stations.csv';return (p.stat().st_mtime_ns,p.stat().st_size)

@st.cache_data(show_spinner=False)
def get_stations(signature):return load_stations()

@st.cache_data(show_spinner=False,max_entries=3)
def get_access(signature,station_sig,radius,_data,_stations):return admin_access(_data['shops'],_stations,radius)

@st.cache_data(show_spinner=False,max_entries=1)
def get_reps(signature,_data):return admin_representatives(_data['shops'],_data['admin'],_data['industries'])

@st.cache_data(show_spinner=False,max_entries=12)
def get_points(signature,conditions,_shops):return map_points(_shops,3000)


def go(page,code=None):
    st.session_state['active_page']=page
    if code is not None:
        st.session_state['selected_admin']=str(code)
        st.session_state['map_focus']=str(code)
        st.session_state['map_admin']=str(code)
        st.session_state['detail_admin']=str(code)


def picked():
    objects=st.session_state.get('prototype_deck',{}).get('selection',{}).get('objects',{}).get('admin_clusters',[])
    if objects:
        code=objects[0].get('행정동코드')
        if code in st.session_state.get('allowed_admins',[]):
            st.session_state['selected_admin']=code;st.session_state['map_admin']=code


def sync_admin(key):st.session_state['selected_admin']=st.session_state[key]


def compare_from_card(code,other):
    st.session_state['candidate_a']=code;st.session_state['candidate_b']=other
    st.session_state['compare_open']=True
    st.session_state['pending_comparison']=(code,other)


def focus_from_card(code):go(PAGES[0],code)


def tram_to_finder(industry,radius):
    saved=st.session_state.get('finder_answers',{})
    saved.update(industry=industry,priorities=[PRIORITIES[3]])
    st.session_state['finder_answers']=saved
    st.session_state['finder_industry']=industry
    st.session_state['finder_priorities']=[PRIORITIES[3]]
    st.session_state['access_radius']=radius
    go(PAGES[2])


def legend(mapping):
    badges=''.join(f'<span class="legend-item"><i style="background:{color}"></i>{html.escape(name)}</span>' for name,color in mapping.items())
    st.markdown('<div class="legend">'+badges+'</div>',unsafe_allow_html=True)


def profile_chart(profile):
    fig=px.bar(profile,x='비율(%)',y='업종',color='업종',orientation='h',color_discrete_map=INDUSTRY_COLORS,
               hover_data={'상가수':True,'비율(%)':':.1f'})
    fig.update_layout(showlegend=False,height=320,margin=dict(l=0,r=0,t=5,b=5),paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)')
    fig.update_yaxes(categoryorder='total ascending');st.plotly_chart(fig,config={'displaylogo':False})


def badge(k):st.markdown(f'<span class="type-badge" style="border-color:{COLORS[k]};color:{COLORS[k]}">{html.escape(FRIENDLY_TYPES[k])}</span>',unsafe_allow_html=True)


def focus_layer(deck,reps,code,zoom=False):
    chosen=reps.loc[reps['행정동코드'].eq(code)]
    if chosen.empty:return deck
    item=chosen.iloc[0]
    deck.layers.append(pdk.Layer('ScatterplotLayer',chosen,id='selected_admin',get_position='[lon,lat]',filled=False,
                                stroked=True,get_line_color=[236,178,34],line_width_min_pixels=4,
                                get_radius=1,radius_units='pixels',radius_min_pixels=17,radius_max_pixels=17))
    if zoom:deck.initial_view_state=pdk.ViewState(latitude=float(item.lat),longitude=float(item.lon),zoom=12.5)
    return deck


def current_map(data,stations):
    # 기존 데이터·군집 결과만 읽어 표시하며 지역 선택은 82개 행정동 기준이다.
    a,b,c=st.columns([1.5,1,1.8])
    visual=a.selectbox('지도 표현',['AI 상권 유형 지도','업종별 상가 분포 지도','상가 밀집도 지도'],key='current_visual')
    reps=get_reps(data_signature(),data).copy()
    focus=st.session_state.pop('map_focus',None)
    if focus in set(reps['행정동코드']):
        st.session_state['current_gu']=reps.set_index('행정동코드').loc[focus,'시군구명']
    gu=b.selectbox('자치구',['전체']+sorted(data['admin']['시군구명'].unique()),key='current_gu')
    allowed=reps if gu=='전체' else reps.loc[reps['시군구명'].eq(gu)]
    codes=allowed['행정동코드'].tolist();labels=allowed.set_index('행정동코드')['지역표시'].to_dict()
    selected=st.session_state.get('selected_admin',codes[0])
    if selected not in codes:selected=codes[0]
    if st.session_state.get('map_admin') not in codes:st.session_state['map_admin']=selected
    c.selectbox('관심 있는 행정동',codes,format_func=labels.get,key='map_admin',on_change=sync_admin,args=('map_admin',))
    selected=st.session_state['map_admin'];st.session_state['selected_admin']=selected
    industry=st.session_state.get('interest_industry','음식')
    left,right=st.columns([2.3,1],gap='large')
    with left:
        if visual=='AI 상권 유형 지도':
            legend({FRIENDLY_TYPES[k]:COLORS[k] for k in FRIENDLY_TYPES})
            st.caption('행정동 단위의 참고용 분류입니다. 경계 자료가 없어 실제 상가에서 고른 대표점으로 표시하며, 동 전체가 이 점에 모여 있다는 뜻은 아닙니다.')
            shown=allowed.copy()
            shown['detail']=shown.apply(lambda r:f"{FRIENDLY_TYPES[int(r['군집'])]} · 상가 {int(r['전체상가수']):,}개 · 주요 업종 {r['주요업종']}",axis=1)
            deck=focus_layer(build_map(shown,MODES[2]),shown,selected,focus is not None)
            st.session_state['allowed_admins']=codes
            st.pydeck_chart(deck,height=475,key='prototype_deck',on_select=picked,selection_mode='single-object')
            st.caption('노란 테두리: 선택한 행정동 · 성장성이나 위험도가 아닙니다. 점을 클릭해 지역을 선택할 수 있습니다.')
        else:
            enabled=st.multiselect('지도에 표시할 업종',data['industries'],default=data['industries'],key='prototype_map_industries')
            shops=data['shops']
            if gu!='전체':shops=shops.loc[shops['시군구명'].eq(gu)]
            shops=shops.loc[shops['상권업종대분류명'].isin(enabled)]
            points,excluded,located=get_points(data_signature(),(gu,tuple(enabled)),shops)
            if visual=='업종별 상가 분포 지도':legend({i:INDUSTRY_COLORS[i] for i in enabled})
            else:legend({'상가 위치 · 겹칠수록 진하게':'#127C80'})
            if points.empty:st.info('표시할 상가가 없습니다. 업종을 선택해 주세요.')
            else:
                deck=build_map(points,MODES[1] if visual=='업종별 상가 분포 지도' else MODES[0])
                deck=focus_layer(deck,reps,selected,focus is not None)
                st.pydeck_chart(deck,height=475)
            st.caption(f'필터 전체 {len(shops):,}개 · 지도 {len(points):,}개 · 좌표 제외 {excluded:,}개. 최대 3,000개의 고정 표본이며 전체 집계와 구분합니다.')
    with right:
        row=reps.loc[reps['행정동코드'].eq(selected)].iloc[0]
        with st.container(border=True):
            st.caption('선택한 지역');st.subheader(row['지역표시'])
            badge(int(row['군집']))
            st.metric('등록 상가',f"{int(row['전체상가수']):,}개")
            st.write(f"가장 많은 업종은 **{row['주요업종']}**입니다.")
            st.caption(TYPE_NOTES[int(row['군집'])])
            st.button('이 지역 상세 분석',key='map_to_detail',on_click=go,args=(PAGES[1],selected),use_container_width=True,type='primary')
            st.button('내 조건으로 지역 찾기',key='map_to_finder',on_click=go,args=(PAGES[2],),use_container_width=True)
        st.caption(f"현재 자료: 상가 {len(data['shops']):,}개 · 행정동 {len(data['admin'])}개 · 2026년 9월")


def tram_map(data,stations):
    eligible=verified_stations(stations)
    st.info(f'트램 계획과 현재 상권을 연결한 탐색용 시나리오입니다. 미래 예측 지도가 아닙니다. 45개 중 확인된 근사 좌표 {len(eligible)}개만 사용합니다.')
    if eligible.empty:st.warning('분석 가능한 정거장 좌표가 없습니다.');return
    a,b,c=st.columns([2,1,1])
    names=eligible.set_index('station_id').station_name.to_dict()
    sid=a.selectbox('예정 정거장',eligible.station_id.tolist(),format_func=lambda s:f'{s} · {names[s]}',key='prototype_tram_station')
    radius=b.selectbox('정거장 반경(m)',[300,500,1000],index=1,key='prototype_tram_radius')
    industry=c.selectbox('관심 업종',data['industries'],index=data['industries'].index(st.session_state.get('interest_industry','음식')),key='prototype_tram_industry')
    st.session_state['interest_industry']=industry
    station=eligible.loc[eligible.station_id.eq(sid)].iloc[0]
    shops,excluded=radius_shops(data['shops'],station,radius);points,_,_=map_points(shops,3000)
    reps=get_reps(data_signature(),data)
    deck=build_map(reps,MODES[2],eligible)
    circle=pdk.Layer('PolygonLayer',[{'polygon':circle_polygon(station.latitude,station.longitude,radius),'name':f'{radius}m 분석 범위','detail':'추정 중심점의 지표면 직선거리'}],id='prototype_radius',get_polygon='polygon',get_fill_color=[20,47,64,20],get_line_color=[20,47,64,240],line_width_min_pixels=2,pickable=True)
    shop_layer=build_map(points,MODES[1]).layers[0]
    deck.layers=[deck.layers[0],circle,shop_layer]+deck.layers[1:]
    deck.initial_view_state=pdk.ViewState(latitude=float(station.latitude),longitude=float(station.longitude),zoom=14 if radius<1000 else 13)
    left,right=st.columns([2.3,1],gap='large')
    profile=industry_profile(shops,data['industries']);chosen=profile.loc[profile['업종'].eq(industry)].iloc[0]
    with left:
        legend({FRIENDLY_TYPES[k]:COLORS[k] for k in FRIENDLY_TYPES})
        legend({'예정 정거장 · 표적형 마커':'#142F40','선택한 반경':'#7E91A0'})
        st.pydeck_chart(deck,height=480)
        st.caption(f'추정 중심점 기준 분석 · 지도 {len(points):,}개 / 반경 내 전체 {len(shops):,}개 · 좌표 제외 {excluded}개. 직선거리이며 도보 접근 시간과 다릅니다.')
        st.caption('큰 색 원은 행정동 대표점, 작은 점은 반경 안의 상가입니다.')
        with st.expander('상가 점의 업종별 색상 범례'):
            legend(INDUSTRY_COLORS)
    with right:
        with st.container(border=True):
            st.subheader(station.station_name)
            st.metric(f'{radius:,}m 안의 등록 상가',f'{len(shops):,}개')
            st.metric(f'{industry} 상가',f"{int(chosen['상가수']):,}개",help=f"전체의 {chosen['비율(%)']:.1f}%")
            st.markdown('**주요 업종**')
            for _,r in profile.nlargest(3,'상가수').iterrows():st.write(f"{r['업종']} · {int(r['상가수']):,}개 ({r['비율(%)']:.1f}%)")
            st.button('트램 접근성으로 창업 지역 찾기',key='tram_to_finder',on_click=tram_to_finder,args=(industry,radius),use_container_width=True,type='primary')
    with st.expander('업종 분포와 방문 수요 가정 살펴보기'):
        profile_chart(profile)
        change=st.slider('방문 수요 변화 가정(%)',-20,30,10,key='prototype_demand')
        st.write(f'방문 수요가 {change:+d}% 변한다고 가정할 때, 현재 상가 {len(shops):,}개가 이 공간적 가정의 대상입니다. 변화율을 바꿔도 대상 수는 변하지 않습니다.')
        st.caption('상가 수에 변화율을 곱해 미래 상가 수나 매출을 만들지 않습니다.')
    with st.expander('정거장 위치 근거와 한계'):
        st.write(station.reviewer_note)
        st.markdown(f'[대조 지도 열기]({station.map_url})')
        st.image(str(BASE_DIR/f'data/tram_reference/station_{sid}.png'),caption=f'공식 상세위치 PDF {station.source_page}페이지',width='stretch')
        st.caption('공식 측량 좌표가 아닌 지도 대조 근사점입니다. 정량 오차는 미산정이며 정거장·상가 좌표의 오차로 경계 상가가 달라질 수 있습니다.')


def map_page(data,stations):
    intro,actions=st.columns([3,1],vertical_alignment='center')
    with intro:
        st.markdown('<h1>대전에서 어디에 창업하면 좋을까요?</h1><p class="intro">대전 상권 데이터와 트램 예정 정거장 정보를 함께 살펴보고,<br>나에게 맞는 창업 후보 지역을 찾아보세요.</p>',unsafe_allow_html=True)
    with actions:
        st.button('내 창업 지역 찾기',key='hero_finder',on_click=go,args=(PAGES[2],),type='primary',use_container_width=True)
        st.button('지도에서 상권 살펴보기',key='hero_map',on_click=go,args=(PAGES[0],),use_container_width=True)
    mode=st.radio('살펴볼 정보',['현재 상권','트램 연계 시나리오'],horizontal=True,key='main_map_mode')
    if mode=='현재 상권':current_map(data,stations)
    else:tram_map(data,stations)


def compare_panel(table,codes,industry,priorities,radius,key):
    labels=table.set_index('행정동코드')['지역표시'].to_dict()
    selected=table.loc[table['행정동코드'].isin(codes)]
    if len(selected)<2:st.info('두 지역의 자료가 필요합니다.');return
    a,b=st.columns(2)
    if st.session_state.get(key+'_a') not in codes:st.session_state[key+'_a']=codes[0]
    first=a.selectbox('비교할 지역 A',codes,format_func=labels.get,key=key+'_a')
    options=[v for v in codes if v!=first]
    if st.session_state.get(key+'_b') not in options:st.session_state[key+'_b']=options[0]
    second=b.selectbox('비교할 지역 B',options,format_func=labels.get,key=key+'_b')
    rows=table.set_index('행정동코드').loc[[first,second]]
    cols=['전체상가수','선택업종상가수','선택업종비율(%)','업종다양성','트램접근상가비율(%)','사용자 조건 부합도']
    st.dataframe(rows[['지역표시']+cols].set_index('지역표시').T.rename(index={'트램접근상가비율(%)':f'트램 {radius}m 내 상가 비율(%)'}),width='stretch')
    for column,(idx,r) in zip(st.columns(2),rows.iterrows()):
        with column:
            st.markdown(f"**{r['지역표시']}**")
            for text in reasons(r,industry,priorities,radius):st.write(text)
            opponent=rows.drop(index=idx).iloc[0]
            higher=[p for p in priorities if r['조건점수_'+p]>opponent['조건점수_'+p]]
            lower=[p for p in priorities if r['조건점수_'+p]<opponent['조건점수_'+p]]
            st.write('선택 조건 관점: '+(' · '.join(higher)+' 조건 점수가 비교 지역보다 높습니다.' if higher else '선택한 조건 점수는 비교 지역보다 높지 않습니다. 다른 지표도 함께 살펴보세요.'))
            st.caption(('비교 시 주의: '+' · '.join(lower)+' 조건 점수는 상대 지역보다 낮습니다. ' if lower else '비교 시 주의: 점수 차이만으로 실제 수요를 알 수 없습니다. ')+'임대 조건과 현장 동선을 추가로 확인하세요.')
    st.caption(f'{industry} 기준 · 트램은 확인된 {st.session_state.get("available_station_count",0)}개 정거장만 사용합니다. 조건 부합도는 성공률·매출 전망이 아닙니다.')


def finder_page(data,stations):
    st.markdown('<div class="eyebrow">나에게 맞는 후보를 찾는 세 단계</div><h1>내 창업 지역 찾기</h1><p class="intro">업종과 경험, 중요하게 보는 조건을 고르면<br>현재 데이터로 비교한 후보 지역 5곳을 보여드려요.</p>',unsafe_allow_html=True)
    saved=st.session_state.get('finder_answers',{})
    for key,value in [('finder_industry',saved.get('industry')),('finder_experience',saved.get('experience')),('finder_priorities',saved.get('priorities',[]))]:
        if key not in st.session_state:st.session_state[key]=value
    a,b,c=st.columns([1,1,1.5])
    with a.container(border=True):
        st.caption('STEP 1 · 창업 업종')
        industry=st.selectbox('어떤 업종을 창업하고 싶으신가요?',data['industries'],index=None,placeholder='업종을 선택하세요',key='finder_industry')
    with b.container(border=True):
        st.caption('STEP 2 · 창업 경험')
        experience=st.radio('창업 경험이 있으신가요?',EXPERIENCES,index=None,key='finder_experience')
    with c.container(border=True):
        st.caption('STEP 3 · 중요한 조건')
        priorities=st.multiselect('창업 지역을 선택할 때 무엇이 가장 중요한가요?',PRIORITIES,max_selections=2,key='finder_priorities',placeholder='한두 가지를 선택하세요')
    st.session_state['finder_answers']={'industry':industry,'experience':experience,'priorities':priorities}
    if not industry or not experience or not priorities:
        st.info('위 세 가지 선택을 마치면 별도의 제출 버튼 없이 TOP 5가 나타납니다.')
        st.caption('예산은 임대료·보증금 자료가 없어 점수에 사용하지 않습니다.');return
    st.session_state['interest_industry']=industry
    radius=st.session_state.get('access_radius',500)
    access=get_access(data_signature(),station_signature(),radius,data,stations)
    table=recommendation_table(data,stations,industry,priorities,radius,access)
    st.caption(experience_note(experience))
    st.subheader('선택 조건에 부합하는 TOP 5')
    st.caption('대전 전체 82개 행정동을 같은 기준으로 비교했습니다. 조건 부합도는 창업 성공률이 아닙니다. 경험은 안내 문구만 바꾸며 점수에는 반영하지 않습니다.')
    if PRIORITIES[3] in priorities:
        st.caption(f'트램 조건을 선택해 확인된 정거장 {radius}m 안에 실제 상가가 있는 {len(table)}개 동을 후보로 남겼습니다. 나머지 조건의 정규화 기준은 82개 동입니다.')
    top=table.head(5)
    for rank,(_,row) in enumerate(top.iterrows(),1):
        with st.container(border=True):
            a,b=st.columns([3,1])
            a.markdown(f"### {rank:02d} · {row['지역표시']}")
            a.caption(f"{FRIENDLY_TYPES[int(row['군집'])]} · {industry} {int(row['선택업종상가수']):,}개 / 전체 {int(row['전체상가수']):,}개")
            b.metric('사용자 조건 부합도',f"{row['사용자 조건 부합도']:.1f} / 100")
            st.markdown('**이 지역이 조건에 부합하는 이유**')
            for text in reasons(row,industry,priorities,radius):st.write(text)
            st.caption('창업 전에 확인할 점: 낮은 점포 비율이 경쟁이 약하다는 뜻은 아닙니다. 실제 수요·임대 조건·보행 동선은 현장에서 확인하세요.')
            a,b,c=st.columns(3);code=row['행정동코드'];other=next((i for i in top['행정동코드'] if i!=code),None)
            a.button('지도에서 확인하기',key='finder_map_'+code,on_click=focus_from_card,args=(code,),use_container_width=True)
            b.button('상세 분석',key='finder_detail_'+code,on_click=go,args=(PAGES[1],code),use_container_width=True)
            c.button('다른 지역과 비교하기',key='finder_compare_'+code,on_click=compare_from_card,args=(code,other),use_container_width=True,disabled=other is None)
    with st.expander('추천 지역 두 곳 비교하기',expanded=st.session_state.get('compare_open',False)):
        codes=top['행정동코드'].tolist()
        pending=st.session_state.pop('pending_comparison',None)
        if pending:
            st.session_state['finder_compare_a']=pending[0] if pending[0] in codes else codes[0]
            options=[i for i in codes if i!=st.session_state['finder_compare_a']]
            st.session_state['finder_compare_b']=pending[1] if pending[1] in options else options[0]
        compare_panel(table,codes,industry,priorities,radius,'finder_compare')
    with st.expander('점수 계산·전체 후보·데이터의 한계'):
        st.write('동일 업종 비율은 낮을수록, 상가 수와 업종 다양성은 높을수록 82개 동의 최소·최대 기준으로 0~100점으로 바꿉니다. 모든 값이 같으면 50점입니다. 트램은 동 전체 상가 중 확인된 정거장 반경 내 상가 비율을 그대로 점수로 사용합니다. 선택한 한두 조건의 동일 가중 평균입니다.')
        st.caption(f'동일 점수는 행정동 코드 순으로 정렬합니다. 접근성 반경 {radius}m · {len(verified_stations(stations))}/45개 정거장 기준. 트램 조건 선택 시 반경 내 상가가 없는 동은 후보에서 제외합니다. 점수가 높은 이유는 선택 조건과의 부합이며 유망도·위험도·예측 점수가 아닙니다.')
        st.info('예산 맞춤 추천은 향후 확장 기능입니다. 현재 임대료·보증금·매출·유동인구 데이터가 없어 예산·수요를 추정하지 않습니다.')
        st.dataframe(table[['지역표시','전체상가수','선택업종상가수','선택업종비율(%)','업종다양성','트램접근상가비율(%)','사용자 조건 부합도']],hide_index=True,width='stretch')
        st.download_button('조건별 전체 비교 결과 다운로드',table.to_csv(index=False).encode('utf-8-sig'),'내창업_조건부합도.csv','text/csv')


def detail_page(data,stations):
    st.markdown('<div class="eyebrow">숫자를 읽기 쉬운 지역 이야기로</div><h1>상권 상세 분석</h1>',unsafe_allow_html=True)
    labels=data['admin'].set_index('행정동코드')['지역표시'].to_dict();codes=list(labels)
    if st.session_state.get('detail_admin') not in codes:st.session_state['detail_admin']=st.session_state.get('selected_admin',codes[0])
    a,b=st.columns([2,1])
    code=a.selectbox('살펴볼 행정동',codes,format_func=labels.get,key='detail_admin',on_change=sync_admin,args=('detail_admin',))
    industry=b.selectbox('비교할 창업 업종',data['industries'],index=data['industries'].index(st.session_state.get('interest_industry','음식')),key='detail_industry')
    st.session_state['selected_admin']=code;st.session_state['interest_industry']=industry
    radius=500;access=get_access(data_signature(),station_signature(),radius,data,stations)
    summary=admin_summary(data,stations,code,industry,radius,access);row=summary['row']
    st.subheader(row['지역표시'])
    a,b,c=st.columns(3)
    with a.container(border=True):
        st.markdown('**이 지역은 어떤 상권인가요?**');badge(int(row['군집']));st.write(TYPE_NOTES[int(row['군집'])]);st.caption('유형 간 경계가 뚜렷하지 않은 참고용 분류입니다.')
    with b.container(border=True):
        st.markdown('**상가가 얼마나 있나요?**');st.metric('전체 등록 상가',f"{int(row['전체상가수']):,}개")
        st.write(f"대전 82개 행정동 중 상가 수가 많은 순으로 {summary['size_rank']}위입니다. 규모 순위는 입지의 우열이 아닙니다.")
    with c.container(border=True):
        st.markdown('**어떤 업종이 많나요?**')
        for _,r in summary['top3'].iterrows():st.write(f"{r['업종']} · {int(r['상가수']):,}개 ({r['비율(%)']:.1f}%)")
    a,b=st.columns(2)
    with a.container(border=True):
        st.markdown('**같은 업종은 얼마나 있나요?**');st.metric(f'{industry} 상가',f"{int(summary['selected']['상가수']):,}개")
        st.write(summary['share_note']);st.caption('비율이 낮다는 사실만으로 경쟁이 약하다고 판단할 수는 없습니다.')
    with b.container(border=True):
        st.markdown('**트램과 가까운 지역인가요?**');r=summary['access']
        if pd.notna(r['접근상가수']):
            st.metric('정거장 500m 내 상가',f"{int(r['접근상가수']):,}개")
            st.write(f"이 동 상가의 {r['트램접근상가비율(%)']:.1f}%가 확인된 정거장 500m 이내에 있습니다.")
            if not r['접근상가수']:st.caption('현재 확인된 5곳 기준입니다. 전체 트램 노선과 멀다는 뜻은 아닙니다.')
        else:st.write('분석 가능한 정거장 자료가 없습니다.')
        st.caption(f"45개 중 {summary['available_stations']}곳의 근사점 기준 · 직선거리 · 동 전체의 접근 시간을 뜻하지 않습니다.")
    a,b,c=st.columns(3)
    a.button('지도에서 이 지역 확인',on_click=go,args=(PAGES[0],code),key='detail_to_map',use_container_width=True)
    b.button('내 조건으로 후보 찾기',on_click=go,args=(PAGES[2],),key='detail_to_finder',type='primary',use_container_width=True)
    with st.expander('다른 행정동과 비교하기'):
        other=st.selectbox('비교할 다른 행정동',[i for i in codes if i!=code],format_func=labels.get,key='detail_other')
        table=recommendation_table(data,stations,industry,[PRIORITIES[0]],radius,access)
        compare_panel(table,[code,other],industry,[PRIORITIES[0]],radius,'detail_compare')
        st.caption('이 비교의 부합도는 동일 업종 비율이 낮은 조건 한 가지 기준입니다.')
    with st.expander('전체 업종 분포·다양성·군집 정보'):
        profile_chart(summary['profile'])
        st.caption(f"업종 다양성 {row['업종다양성']:.3f} · 군집 {int(row['군집'])} · 실루엣 {row['실루엣']:.3f}. 다양성은 자연로그 Shannon entropy이며 성공 가능성이 아닙니다.")
        st.dataframe(summary['profile'][['업종','상가수','비율(%)']],hide_index=True,width='stretch')


def auxiliary(data,stations):
    with st.expander('데이터 출처와 분석 방법'):
        st.write('소상공인시장진흥공단 2026년 9월 대전 상가 79,691개와 82개 행정동의 기존 K=3 결과를 사용합니다. 행정동 코드로 연결하며 원본 데이터와 군집 결과를 변경하지 않습니다.')
        st.caption('트램은 공식 상세위치 PDF와 지도를 대조한 5개 근사점만 사용합니다. 정량 위치 오차는 미산정이며 경계 포함 상가가 달라질 수 있습니다. 경계 GeoJSON은 검증하지 못해 대표점을 사용합니다. 배경 지도 © OpenStreetMap 기여자 / CARTO.')
        st.caption('매출·유동인구·임대료·창업 성공률을 예측하지 않습니다. 원본 지역 자료를 보존하고 주요 사용자 분석은 행정동 기준으로 제공합니다.')
    with st.expander('보조 서비스 · 통계와 시연용 커뮤니티'):
        service=st.selectbox('보조 기능',['전체 상권 통계','시연용 창업 커뮤니티'],key='prototype_aux')
        if service=='전체 상권 통계':
            a,b,c=st.columns(3);a.metric('상가',f"{len(data['shops']):,}개");b.metric('행정동',len(data['admin']));c.metric('업종',len(data['industries']))
            profile_chart(industry_profile(data['shops'],data['industries']))
            st.dataframe(data['admin'][['지역표시','전체상가수','군집']],hide_index=True,width='stretch')
        else:
            from community import load_examples,filter_examples,POST_TYPES
            st.info('모든 게시글·작성자·일자는 시연을 위한 가상 콘텐츠입니다. 실제 창업 경험이나 성과 자료가 아닙니다.')
            posts=load_examples(data['legal'])
            a,b=st.columns(2)
            industry=a.selectbox('시연글 업종',['전체']+sorted(posts.industry.unique()),key='prototype_post_industry')
            kind=b.selectbox('시연글 유형',['전체']+POST_TYPES,key='prototype_post_kind')
            query=st.text_input('시연글 검색',key='prototype_post_query')
            matches=filter_examples(posts,industry=industry,post_type=kind,query=query)
            st.caption(f'검색 결과 {len(matches)}개 · 전체 가상 게시글 {len(posts)}개')
            if matches.empty:st.info('조건에 맞는 시연글이 없습니다.')
            else:
                titles=matches.set_index('id').title.to_dict()
                selected=st.selectbox('살펴볼 시연글',matches.id.tolist(),format_func=titles.get,key='prototype_post')
                post=matches.loc[matches.id.eq(selected)].iloc[0]
                with st.container(border=True):st.markdown('**[가상] '+post.title+'**');st.write(post.body)
    with st.expander('관리자용 상세 영역 · 트램 좌표 등록'):
        from coordinate_ui import coordinate_editor
        coordinate_editor()


def main():
    st.markdown('''<style>
    .stApp {background:#F6F8FA;color:#1E3446}
    .block-container{padding-top:1.8rem;padding-bottom:2rem;max-width:1480px}
    h1{font-size:2.2rem!important;letter-spacing:-.06em;font-weight:750!important;line-height:1.35!important}
    h2,h3{letter-spacing:-.04em}.intro{font-size:1rem;color:#647888;line-height:1.65;margin-bottom:8px}
    .eyebrow{font-size:.78rem;color:#127C80;font-weight:700;letter-spacing:.12em;margin-top:14px}
    .brand{display:flex;align-items:center;gap:12px;margin-bottom:12px}.brand-mark{background:#142F40;color:white;padding:10px 14px;border-radius:12px;font-weight:800;font-size:1.2rem;letter-spacing:.06em}
    .brand-copy{font-size:.85rem;color:#526978}.type-badge{display:inline-block;border-left:4px solid;padding:8px 12px;background:white;border-radius:4px;font-size:.94rem;font-weight:700;margin-bottom:8px}
    .legend{display:flex;flex-wrap:wrap;gap:8px 16px;margin:6px 0 12px}.legend-item{display:flex;align-items:center;gap:6px;font-size:.78rem;color:#526978}.legend i{width:11px;height:11px;border-radius:50%;display:inline-block}
    [data-testid="stMetricValue"]{font-size:1.7rem;color:#146B71;font-weight:700}
    [data-testid="stVerticalBlockBorderWrapper"]>div{border-radius:16px;background:#FFF}
    div[data-testid="stRadio"]>div[role="radiogroup"]{gap:12px;flex-wrap:wrap}
    div[data-testid="stRadio"] div[role="radiogroup"] label{background:#FFF;border:1px solid #DDE6EB;padding:8px 14px;border-radius:12px}
    @media(max-width:760px){h1{font-size:1.65rem!important}.block-container{padding:1rem}.brand{align-items:flex-start;flex-direction:column}.intro br{display:none}}
    </style>''',unsafe_allow_html=True)
    st.markdown('<div class="brand"><div class="brand-mark">D·VISION</div><div class="brand-copy">트램이 바꿀 대전 상권, 계약 전에 미리 봅니다.</div></div>',unsafe_allow_html=True)
    page=st.radio('핵심 서비스',PAGES,horizontal=True,key='active_page',label_visibility='collapsed')
    try:
        data=get_data(data_signature());stations=get_stations(station_signature())
        st.session_state['available_station_count']=len(verified_stations(stations))
        if page==PAGES[0]:map_page(data,stations)
        elif page==PAGES[1]:detail_page(data,stations)
        else:finder_page(data,stations)
        st.divider();auxiliary(data,stations)
    except (ValueError,KeyError,OSError) as exc:
        st.error(f'분석 자료를 확인해 주세요: {exc}')
    st.caption('D·VISION · 현재 상권을 이해하고 후보 지역을 비교하는 창업 준비 도구 · 2026년 9월 상가 자료')

if __name__=='__main__':main()
