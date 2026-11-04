"""트램·가정 시나리오·가상 커뮤니티 화면. 기존 대시보드와 분리한다."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard_data import BASE_DIR, industry_profile, entropy, select_shops, data_signature
from tram_analysis import (load_stations, station_status, verified_stations, radius_shops,
                           station_summary, admin_access, preference_scores, scenario_exposure,
                           station_map, covered_shop_ids)
from community import load_examples,filter_examples,DEMO_NOTICE,POST_TYPES

TRAM_PAGE='트램 역세권 상권 분석'
SCENARIO_PAGE='트램 개통 영향 시나리오'
COMMUNITY_PAGE='창업 경험 커뮤니티'
ALL_STATIONS_NOTE='정거장 명칭과 위치는 제공 PDF의 표기·예정 위치입니다. 향후 조정될 수 있으며 최신 확정 명칭과 다를 수 있습니다.'


def go_to(page,legal_code=None):
    st.session_state['navigation']=page
    if legal_code:
        st.session_state['focused_legal_code']=legal_code
        st.session_state['detail_basis']='법정동'
    if page==COMMUNITY_PAGE and legal_code:
        st.session_state['community_region_code']=legal_code


def station_signature():
    files=[BASE_DIR/'data/tram_stations.csv',BASE_DIR/'data/tram_sources.json']
    return tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in files)


@st.cache_data(show_spinner=False)
def cached_stations(signature):
    return station_status(load_stations())


def get_stations():
    return cached_stations(station_signature())


@st.cache_data(show_spinner='검증된 좌표로 집계 중…')
def cached_station_summary(signature,_shops,stations,industries,radius,industry):
    return station_summary(_shops,stations,industries,radius,industry)


@st.cache_data(show_spinner=False)
def cached_admin_access(signature,_shops,stations,radius):
    return admin_access(_shops,stations,radius)


def plot(fig,height=350):
    fig.update_layout(template='plotly_white',height=height,margin=dict(l=15,r=15,t=30,b=25),
                      font=dict(family='Arial, Apple SD Gothic Neo, sans-serif'),
                      colorway=['#127C80','#D98C40','#526BB3'],legend_title_text='')
    st.plotly_chart(fig,config={'displaylogo':False})


def csv_button(frame,name):
    st.download_button('CSV 다운로드',frame.to_csv(index=False).encode('utf-8-sig'),name,'text/csv',key='download_'+name)


def status_panel(stations):
    valid=stations.analysis_eligible.sum()
    missing=stations[['latitude','longitude']].isna().any(axis=1).sum()
    c1,c2,c3=st.columns(3)
    c1.metric('PDF 정거장 목록',f'{len(stations)}개')
    c2.metric('반경 분석 가능한 검증 좌표',f'{valid}개')
    c3.metric('좌표 미확보',f'{missing}개')
    st.caption(ALL_STATIONS_NOTE)
    st.caption(f'분석 가능 {valid}/{len(stations)}개 · '+ (' / '.join(f'{ {"official":"공식 좌표","map_verified_approx":"지도 대조 근사 좌표","manual_review_required":"사용자 확인 필요","unavailable":"미확보"}.get(k,k)}: {v}개' for k,v in stations.coordinate_status.value_counts().items()) if 'coordinate_status' in stations else '기존 검증 상태'))
    if not valid:
        st.warning('현재 검증 완료된 정거장 좌표가 없습니다. 정거장 지도·반경 상권 수치는 자료 확인 전까지 표시하지 않습니다. 0개라는 분석 결과가 아닙니다.')


def station_picker(stations,key,label='예정 정거장 선택'):
    stations=stations.sort_values('analysis_eligible',ascending=False,kind='stable')
    ids=stations.station_id.tolist();names=stations.set_index('station_id').station_name.to_dict()
    selected=st.selectbox(label,ids,format_func=lambda n:f'{n} · {names[n]} · 예정 위치',key=key)
    return stations.loc[stations.station_id.eq(selected)].iloc[0]


def source_view(station):
    st.markdown(f"#### {station.station_id} · {station.station_name} — 예정 위치")
    st.write(f"PDF 주변 위치 설명: {station.nearby_landmark}")
    st.caption(f"출처: 제공 정거장 상세위치 PDF {int(station.source_page)}페이지 · 명칭은 PDF 표기")
    st.write(f"좌표 상태: **{station.verification_status}** · {station.coordinate_accuracy}")
    if station.analysis_eligible: coordinate_notice(station)
    if not station.analysis_eligible:
        st.caption(station.analysis_reason)
    image=BASE_DIR/'data/tram_reference'/f'station_{station.station_id}.png'
    if image.is_file():
        st.image(str(image),caption='제공 PDF의 정거장 예정 위치도 · 지리참조된 지도 데이터가 아닙니다.',width='stretch')
    else:
        st.info('해당 정거장의 위치도 이미지가 없습니다. 원본 PDF에서 확인해 주세요.')


def coordinate_notice(station=None):
    status=station.get('coordinate_status','map_verified_approx') if station is not None else 'mixed'
    label='공식 좌표 기준 분석' if status=='official' else '추정 중심점 기준 분석'
    st.info(label+' · 지도 대조 근사 좌표는 공식 측량 좌표가 아닙니다. 정거장과 상가 좌표의 오차에 따라 반경 경계의 포함 상가가 바뀔 수 있습니다. 현재 업종 구조이며 매출·창업 성공 가능성의 예측이 아닙니다.')
    if station is not None:
        st.caption(f"좌표 상태: {'공식 좌표' if status=='official' else '지도 대조 근사 좌표'} · 출처: {station.coordinate_source}")
        if str(station.get('estimated_uncertainty_m',''))=='': st.caption('정량 위치 오차 미산정 · 근거 없는 오차 범위와 민감도 수치는 계산하지 않습니다.')
    else: st.caption('지도 대조 근사 좌표와 공식 좌표는 각 정거장 출처 표에서 구분합니다. 현재 근사 좌표의 정량 오차는 미산정입니다.')


def current_profile(data,subset,industry,key,radius=None):
    p=industry_profile(subset,data['industries'])
    if subset.empty:
        st.info('검증 좌표를 기준으로 계산한 이 반경에는 등록 상가가 없습니다. 업종 비율과 다양성은 해석하지 않습니다.')
        return
    c1,c2,c3=st.columns(3)
    chosen=p.loc[p['업종'].eq(industry)].iloc[0]
    c1.metric('반경 내 전체 상가',f'{len(subset):,}개')
    c2.metric(f'{industry} 상가',f"{int(chosen['상가수']):,}개",help=f"전체 상가 중 {chosen['비율(%)']:.2f}%")
    c3.metric('업종 다양성',f'{entropy(p):.3f}',help='자연로그 Shannon entropy. 입지의 우열이 아닙니다.')
    if radius is not None:
        st.caption(f'동일 업종 밀집도: {int(chosen["상가수"])/(np.pi*(radius/1000)**2):,.2f}개/km² · 반경 {radius:,}m 원 면적 기준')
    if len(subset)<100:
        st.warning('반경 내 상가가 100개 미만입니다. 소수 상가의 변화로 비율이 크게 달라질 수 있습니다. 100개는 화면 안내용 기준입니다.')
    st.caption('표와 그래프는 반경 내 전체 상가 집계입니다. 행정동 군집을 이 원형 범위의 군집으로 지정하지 않습니다.')
    a,b=st.columns(2)
    with a:
        st.markdown('**업종 대분류별 상가 수**')
        plot(px.bar(p,x='업종',y='상가수',hover_data={'비율(%)':':.2f'},labels={'상가수':'상가 수(개)'}))
    with b:
        st.markdown('**대분류 구성 비율**')
        plot(px.bar(p,x='업종',y='비율(%)',hover_data={'상가수':':,'}))
    st.markdown('**주요 업종 상위 5개**')
    st.dataframe(p.nlargest(5,'상가수')[['업종','상가수','비율(%)']],hide_index=True,width='stretch')
    middle=subset.groupby(['상권업종대분류명','상권업종중분류명']).size().rename('상가수').reset_index().sort_values('상가수',ascending=False)
    with st.expander('모든 대분류·중분류 집계 및 다운로드'):
        st.dataframe(p[['업종','상가수','비율(%)']],hide_index=True,width='stretch')
        st.dataframe(middle,hide_index=True,width='stretch')
        csv_button(middle,f'{key}_중분류.csv')
        csv_button(p[['업종','상가수','비율(%)']],f'{key}_대분류.csv')


def same_radius_comparison(data,stations,radius,industry):
    eligible=verified_stations(stations)
    st.subheader('같은 반경으로 정거장 비교')
    if len(eligible): coordinate_notice()
    st.caption(f'공통 분석 반경 {radius:,}m · 밀집도는 업종 상가 수 ÷ 원 면적(km²)입니다. 반경이 같으면 상가 수와 밀집도 순서는 같습니다.')
    if len(eligible)<2:
        st.info('정거장 A·B 비교에는 검증 완료된 정거장 좌표가 최소 2개 필요합니다.')
        return
    table=cached_station_summary((data_signature(),station_signature()),data['shops'],stations,data['industries'],radius,industry)
    ids=table.station_id.tolist(); names=table.set_index('station_id').station_name.to_dict()
    a,b=st.columns(2)
    first=a.selectbox('비교 정거장 A',ids,format_func=names.get,key='tram_compare_a')
    second=b.selectbox('비교 정거장 B',[i for i in ids if i!=first],format_func=names.get,key='tram_compare_b')
    chosen=table.loc[table.station_id.isin([first,second])]
    st.dataframe(chosen,hide_index=True,width='stretch')
    profiles=[]
    selected_stations=stations.loc[stations.station_id.isin([first,second])]
    for _,station in selected_stations.iterrows():
        shops,_=radius_shops(data['shops'],station,radius)
        profiles.append(industry_profile(shops,data['industries']).assign(정거장=f'{station.station_id} {station.station_name}'))
    plot(px.bar(pd.concat(profiles),x='업종',y='비율(%)',color='정거장',barmode='group'))
    union=covered_shop_ids(data['shops'],selected_stations,radius)
    st.caption(f'두 정거장 반경의 중복 제거 상가: {len(union):,}개. 정거장별 수를 단순 합산하지 않았습니다.')
    csv_button(chosen,'정거장_동일반경비교.csv')


def tram_page(data):
    st.subheader(TRAM_PAGE)
    st.caption('실제 현재 상가 자료와 검증된 예정 위치만으로 주변 업종 구조를 살펴봅니다.')
    try: stations=get_stations()
    except (ValueError,OSError,KeyError) as exc:
        st.error(f'정거장 자료를 확인해 주세요: {exc}');return
    status_panel(stations)
    a,b=st.columns([2,1])
    with a: selected=station_picker(stations,'tram_station')
    radius=b.selectbox('분석 반경(m)',[300,500,1000],index=1,key='tram_radius')
    industry=st.selectbox('관심 업종',data['industries'],index=data['industries'].index('음식'),key='tram_industry')
    if selected.analysis_eligible:
        coordinate_notice(selected)
        subset,excluded=radius_shops(data['shops'],selected,radius)
        st.pydeck_chart(station_map(stations,selected,subset,radius),height=480)
        st.caption(f'모든 정거장 표시는 검증된 예정 위치입니다. 상가 점은 최대 3,000개 표본이며 통계는 전체 {len(subset):,}개입니다. 좌표 제외 상가 {excluded:,}개.')
        st.caption('Haversine 지표면 직선거리로 계산하며 도보 경로·출입구 접근 시간이 아닙니다. 위치 오차로 경계 부근 포함 여부가 바뀔 수 있습니다.')
        current_profile(data,subset,industry,f'tram_{selected.station_id}_{radius}',radius)
    else:
        st.info('선택한 정거장은 좌표 미검증 상태로 반경 집계를 실행하지 않았습니다. 아래 PDF 예정 위치를 확인할 수 있습니다.')
    with st.expander('선택 정거장의 PDF 예정 위치 확인',expanded=not selected.analysis_eligible): source_view(selected)
    same_radius_comparison(data,stations,radius,industry)
    with st.expander('전체 정거장 목록·출처·검증 상태',expanded=False):
        cols=['station_id','station_name','nearby_landmark','source_page','latitude','longitude','verification_status','coordinate_source','coordinate_accuracy','coordinate_status','verification_method','reviewed_at','estimated_uncertainty_m','reviewer_note','map_url','analysis_reason']
        st.dataframe(stations[[c for c in cols if c in stations]],hide_index=True,width='stretch')
        csv_button(stations,'트램_정거장_검증상태.csv')
    with st.expander('전체 노선 참고 이미지 · 정확한 GIS 노선 아님'):
        image=BASE_DIR/'data/tram_reference/route_reference.png'
        if image.is_file(): st.image(str(image),caption='제공 PDF 2페이지 · 예정 노선 참고용. 실제 GIS 선형으로 사용하지 않습니다.',width='stretch')
        st.caption('정거장 사이를 임의의 선으로 연결하지 않았습니다.')
    with st.expander('관리: 좌표 후보 등록·수정·PDF 지도 대조 승인'):
        from coordinate_ui import coordinate_editor
        coordinate_editor()
    with st.expander('좌표 검증 기준 및 미확보 이유'):
        st.write('예정 정거장 중심점의 출처·대조 근거·검증자·검증일·좌표계(EPSG:4326)가 있어야 합니다. 4단계에서는 공식 좌표와 PDF·실제 지도의 도로·교차로·주변 시설·승강장 구간 대조를 마친 근사 좌표만 허용합니다. 정량 오차 근거가 없으면 값을 비워 두고 불확실성을 안내합니다.')
        st.write('현재 PDF에는 좌표와 지리참조 정보가 없습니다. 부근 시설·도로명만 지오코딩한 점은 승강장 중심과 같지 않아 분석에 사용할 수 없습니다. 검증된 좌표를 CSV에 보완하면 자동으로 반경 분석이 활성화됩니다.')
        st.markdown('[대전시 공식 노선·정거장 자료](https://daejeon.go.kr/djTram/contentView.do?menuSeq=7702)')


def scenario_page(data):
    st.subheader(SCENARIO_PAGE)
    st.warning('사용자 가정에 해당하는 공간 범위를 살펴보는 시연입니다. 실제 유동인구·매출 변화나 미래 효과를 예측하지 않습니다.')
    stations=get_stations()
    selected=station_picker(stations,'scenario_station','가정을 적용할 예정 정거장')
    a,b=st.columns(2)
    radius=a.selectbox('가정 범위 반경(m)',[300,500,1000],index=1,key='scenario_radius')
    industry=b.selectbox('관심 업종',data['industries'],key='scenario_industry')
    change=st.slider('가정한 방문 수요 변화율(%)',-20,30,10,key='scenario_change')
    st.metric('사용자가 설정한 가정',f'{change:+d}%')
    st.caption('-20~+30%는 시연용 입력 범위입니다. 대전 트램의 예상 효과를 뜻하지 않으며 상가 수나 매출에 곱하지 않습니다.')
    if not selected.analysis_eligible:
        st.info('선택 정거장의 좌표 검증 전입니다. 가정에 노출되는 상가 수와 공간 범위는 아직 계산할 수 없습니다. 0개로 표시하지 않습니다.')
        with st.expander('해당 정거장의 PDF 예정 위치'): source_view(selected)
        return
    coordinate_notice(selected)
    exposure=scenario_exposure(data['shops'],selected,radius,change,industry,data['industries'])
    st.write(f"방문 수요가 {change:+d}% 변한다고 가정할 때, {selected.station_name} 예정 위치 반경 {radius:,}m의 현재 상가 {exposure['exposed_shops']:,}개가 가정의 분석 대상에 포함됩니다. 관심 업종은 {exposure['selected_industry_shops']:,}개입니다.")
    st.caption('변화율을 바꿔도 대상 상가 수는 바뀌지 않습니다. 실제 수요·매출의 기준값과 인과 효과 자료가 없기 때문입니다.')
    st.pydeck_chart(station_map(stations,selected,exposure['shops'],radius),height=450)
    current_profile(data,exposure['shops'],industry,f'scenario_{selected.station_id}_{radius}',radius)
    same_radius_comparison(data,stations,radius,industry)


def station_explore(data):
    st.subheader('정거장 기반 창업 입지 탐색')
    stations=get_stations()
    status_panel(stations)
    a,b=st.columns(2)
    industry=a.selectbox('창업 희망 업종',data['industries'],index=data['industries'].index('음식'),key='station_explore_industry')
    radius=b.selectbox('정거장 분석 반경(m)',[300,500,1000],index=1,key='station_explore_radius')
    if verified_stations(stations).empty:
        st.info('검증된 정거장 좌표가 확보되면 동일 반경 내 현재 상가 수·업종 비율·다양성·밀집도를 비교할 수 있습니다. 행정동 탐색은 계속 사용할 수 있습니다.')
        return
    coordinate_notice()
    table=cached_station_summary((data_signature(),station_signature()),data['shops'],stations,data['industries'],radius,industry)
    st.dataframe(table,hide_index=True,width='stretch')
    st.caption('정거장 반경은 행정동과 다른 공간 단위입니다. 행정동 군집과 점수를 섞지 않으며, 상가가 적다는 이유로 유리하다고 판단하지 않습니다.')
    plot(px.bar(table,x='station_name',y='선택업종상가수',hover_data=['전체상가수','선택업종비율(%)']))
    csv_button(table,'정거장기반_관심업종탐색.csv')


def apply_preferences(data,table,minimum,gu):
    with st.expander('창업 조건 설정 · 조건 부합도 계산',expanded=False):
        a,b,c=st.columns(3)
        maximum=a.number_input('행정동 전체 상가 수 최댓값',min_value=0,max_value=100000,value=int(data['admin']['전체상가수'].max()),key='explore_maximum')
        same=b.selectbox('동일 업종 분포 선호',['무관','높은 비율','낮은 비율'],key='explore_same_preference')
        diversity=c.selectbox('업종 다양성 선호',['무관','높은 다양성','낮은 다양성'],key='explore_diversity')
        stations=get_stations()
        available=bool(stations.analysis_eligible.any())
        st.caption(f'분석 가능한 자료: {int(stations.analysis_eligible.sum())}/{len(stations)} 정거장 · 미확보 정거장은 제외')
        if available: coordinate_notice()
        access=st.selectbox('트램 예정 정거장 접근성',['거리 무관','300m 이내','500m 이내','1km 이내'],disabled=not available,key='explore_tram_access')
        if not available: st.caption('검증된 정거장 좌표가 없어 접근성 조건은 비활성화했습니다. 접근성을 0으로 가정하지 않습니다.')
        st.caption('상권 규모는 최소·최대 전체 상가 수로 필터링합니다. 활성화한 비율·다양성 선호를 조회 자치구의 모든 행정동 기준으로 최소-최대 정규화하고 동등 가중 평균×100으로 계산합니다. 무관 항목은 제외하며, 선호가 모두 무관이면 점수를 표시하지 않습니다.')
        st.caption('접근성은 해당 동의 전체 상가 중 검증된 예정 정거장 반경 안에 있는 상가의 비율입니다. 여러 정거장과 가까운 상가도 한 번만 셉니다. 일부 정거장만 검증된 경우 전체 45개 기준 접근성이 아닙니다. 좌표가 없는 상가는 분자에서 제외합니다.')
        st.caption('사용자 조건 부합도는 선호를 정렬하는 참고 값이며 창업 성공률·매출 전망이 아닙니다. 낮은 동일 업종 비율을 선호해도 유리한 입지라는 뜻은 아닙니다.')
    # 정규화 기준은 규모 필터 전, 조회 자치구 전체로 유지한다.
    from dashboard_data import exploration_table
    current_industry=st.session_state['explore_industry']
    current_medium=st.session_state.get(f'explore_medium_{current_industry}','전체')
    reference=exploration_table(data['shops'],data['admin'],current_industry,current_medium,0,gu)
    use_access=available and access!='거리 무관'
    if use_access:
        radius={'300m 이내':300,'500m 이내':500,'1km 이내':1000}[access]
        access_table=cached_admin_access((data_signature(),station_signature()),data['shops'],stations,radius)
        reference=reference.merge(access_table[['행정동코드','접근상가수','트램접근상가비율(%)']],on='행정동코드',validate='one_to_one')
    scored=preference_scores(reference,same,diversity,use_access)
    keep=(scored['전체상가수']>=minimum)&(scored['전체상가수']<=maximum)
    if use_access: keep &= scored['접근상가수'].gt(0)
    result=scored.loc[keep].copy()
    if result['사용자 조건 부합도'].notna().any():
        st.subheader('선택 조건에 따른 탐색 결과')
        st.dataframe(result[['지역표시','전체상가수','선택업종비율(%)','업종다양성','사용자 조건 부합도']].sort_values('사용자 조건 부합도',ascending=False),hide_index=True,width='stretch')
    return result


def related_posts(data,legal_codes):
    try: posts=load_examples(data['legal'])
    except (ValueError,OSError,KeyError): return
    related=posts.loc[posts.region_code.isin(list(legal_codes))]
    if related.empty: return
    with st.expander('이 지역 이름으로 살펴보는 시연용 가상 게시글'):
        st.caption(DEMO_NOTICE)
        st.caption('게시글은 법정동 기준입니다. 선택 행정동 전체를 대표하는 경험 자료가 아닙니다.')
        for _,p in related.head(3).iterrows():
            st.write(f"[가상] {p.title} · {p.region}")
        st.button('해당 법정동의 가상 커뮤니티 보기',key='related_community_'+'_'.join(sorted(legal_codes)),on_click=go_to,args=(COMMUNITY_PAGE,related.iloc[0].region_code))


def legal_detail(data):
    regions=data['legal']; options=regions['법정동코드'].tolist();labels=regions.set_index('법정동코드')['지역표시'].to_dict()
    focus=st.session_state.pop('focused_legal_code',None)
    if focus in options: st.session_state['detail_legal_code']=focus
    code=st.selectbox('분석할 법정동',options,format_func=labels.get,key='detail_legal_code')
    sub=data['shops'].loc[data['shops']['법정동코드'].eq(code)]
    profile=industry_profile(sub,data['industries'])
    st.markdown(f'### {labels[code]} · 법정동 기준')
    st.caption(f'법정동코드 {code} · 행정동 기준 K-means 군집을 하나로 부여하지 않습니다.')
    a,b,c=st.columns(3)
    a.metric('전체 상가',f'{len(sub):,}개');b.metric('주요 업종',profile.loc[profile['상가수'].idxmax(),'업종']);c.metric('업종 다양성',f'{entropy(profile):.3f}')
    plot(px.bar(profile,x='업종',y='상가수',hover_data={'비율(%)':':.2f'}))
    st.dataframe(profile[['업종','상가수','비율(%)']],hide_index=True,width='stretch')
    related_posts(data,[code])


def community_page(data):
    st.subheader(COMMUNITY_PAGE)
    st.warning(DEMO_NOTICE)
    st.caption('실제 회원가입·게시글 작성·개인정보 수집은 제공하지 않습니다. 작성일과 별명도 시연용 설정입니다.')
    try: posts=load_examples(data['legal'])
    except (ValueError,OSError,KeyError) as exc:
        st.error(f'가상 콘텐츠 파일을 확인해 주세요: {exc}');return
    a,b,c=st.columns(3)
    regions=['전체']+sorted(posts.region.unique())
    focus=st.session_state.pop('community_region_code',None)
    if focus in set(posts.region_code): st.session_state['community_region']=posts.loc[posts.region_code.eq(focus),'region'].iloc[0]
    region=a.selectbox('게시글 지역 · 법정동',regions,key='community_region')
    industry=b.selectbox('게시글 업종',['전체']+sorted(posts.industry.unique()),key='community_industry')
    kind=c.selectbox('게시글 유형',['전체']+POST_TYPES,key='community_type')
    query=st.text_input('가상 게시글 검색',key='community_search',placeholder='제목·본문·별명 검색')
    matches=filter_examples(posts,region,industry,kind,query)
    st.caption(f'조건에 맞는 가상 게시글 {len(matches)}개')
    if matches.empty:
        st.info('조건에 맞는 시연용 가상 게시글이 없습니다.');return
    st.dataframe(matches[['title','region','industry','post_type','nickname','created_at']].rename(columns={'title':'가상 게시글 제목','region':'법정동','industry':'업종','post_type':'유형','nickname':'가상 별명','created_at':'예시 작성일'}),hide_index=True,width='stretch')
    titles=matches.set_index('id').title.to_dict()
    selected=st.selectbox('상세히 볼 가상 게시글',matches.id.tolist(),format_func=lambda i:'[시연용 가상] '+titles[i],key='community_post')
    post=matches.loc[matches.id.eq(selected)].iloc[0]
    with st.container(border=True):
        st.markdown(f'#### [시연용 가상] {post.title}')
        st.caption(f'{post.region} · 법정동코드 {post.region_code} | {post.industry} | {post.post_type} | {post.nickname} | 예시 일자 {post.created_at}')
        st.write(post.body)
        st.caption(DEMO_NOTICE)
        st.button('이 법정동의 실제 상권 분석으로 이동',on_click=go_to,args=('지역별 상세 분석',post.region_code),key='community_to_analysis')
