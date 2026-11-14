"""미래 상권 페이지: 관측 이력, 검증, 수요 가정, 공사 상권 목록."""
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from tram_analysis import verified_stations
from tram_forecast import (load_forecast_data, evaluate_models, forecast_series,
                           demand_scenario, filter_markets)
from tram_outlook_ui import outlook_sections

BASE = Path(__file__).resolve().parent
LABELS = {'trend': '규제한 비중 추세', 'persistence': '직전 비중 유지'}


def signature():
    paths = sorted((BASE/'data/forecast').glob('*')) + [BASE/'data/tram_stations.csv']
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths if p.is_file())


@st.cache_data(show_spinner=False)
def prepared(sig):
    history, demand, markets, metadata = load_forecast_data(BASE)
    return history, demand, markets, metadata, evaluate_models(history)


def forecast_page(data, stations):
    mode=st.radio('살펴볼 분석',['대전 예정지 분석','신림선 개통 사례','학습 모델 실험','대전 적용 실험'],horizontal=True,key='forecast_evidence')
    if mode=='대전 적용 실험':
        from daejeon_transfer_ui import transfer_page
        transfer_page()
    elif mode=='학습 모델 실험':
        from shop_prediction_ui import prediction_page
        prediction_page()
    elif mode=='신림선 개통 사례':
        from rail_case_ui import case_study_page
        case_study_page()
    else:
        daejeon_forecast_page(data,stations)


def daejeon_forecast_page(data, stations):
    st.header('트램 주변 미래 상권')
    st.write('트램 예정지 주변에서 어떤 업종이 늘고 줄었는지, 대전 전체보다 변화가 빠른지 살펴보고 미래 추세와 계획 수요를 비교합니다.')
    st.caption('실제 개통 사례의 분석 결과는 위의 신림선 개통 사례에서 확인할 수 있습니다. 현재 신림선 비교 차이를 대전 예측에 자동 반영하지 않습니다.')
    history, demand, markets, metadata, evaluation = prepared(signature())
    available = verified_stations(stations)
    available = available.loc[available.station_id.isin(history.station_id)]
    st.caption(f'과거 자료 4개 시점 · 반경 분석 {len(available)}/45개 정거장 · 수요 조회 45개 · 공사 영향 상권 {len(markets)}곳')
    if available.empty:
        st.info('현재 승인된 좌표에 해당하는 과거 집계가 없습니다.')
        return
    labels = available.set_index('station_id').station_name.to_dict()
    a,b,c,d = st.columns(4)
    sid = a.selectbox('정거장',available.station_id.tolist(),format_func=lambda x:f'{x} · {labels[x]}',key='forecast_station')
    radius = b.selectbox('직선 반경(m)',[300,500,1000],index=1,key='forecast_radius')
    industries = sorted(history.industry.unique())
    industry = c.selectbox('살펴볼 업종',industries,index=industries.index('음식'),key='forecast_industry')
    year = d.selectbox('예측 기준 연도',list(range(2027,2036)),index=3,key='forecast_year')
    selected = history.loc[(history.station_id==sid)&(history.radius_m==radius)&(history.industry==industry)].sort_values('date')
    outlook_sections(history,available,demand,sid,radius,industry,year)
    st.divider()
    st.subheader('계획 수요를 추가하면 결과가 어떻게 달라질까?')
    st.write('위의 과거 추세에 계획 수요를 더하는 실험입니다. 수요가 점포 수에 미치는 영향은 아직 학습하지 않았으므로 직접 정한 강도를 사용합니다.')
    recommended = evaluation['selected']
    methods = [recommended] + [k for k in LABELS if k != recommended]
    method = st.selectbox('수요 가정에 사용할 기준',methods,format_func=lambda k:LABELS[k]+(' · 검증에서 선택' if k==recommended else ' · 비교용'),key='forecast_method')
    if recommended == 'persistence':
        st.info('유지 기준에서 현재와 미래가 같은 이유: 전체 검증에서는 추세보다 최근 비중 유지가 더 잘 맞았습니다. 이는 변화가 없다는 증명이 아닙니다. 위의 전망 탭에서 추세와 유지 기준을 함께 비교할 수 있습니다.')
    result = forecast_series(selected,f'{year}-09-30',method)
    a,b = st.columns(2)
    a.metric('현재 관측 점포 수',f"{result['latest_count']:,}개")
    b.metric(f'{year}년 기본 추정',f"{result['count']:,.1f}개")
    st.caption(f"{LABELS[method]} 방법 · 대전 전체 해당 업종 규모를 2026년 9월 {result['city_reference_count']:,}개로 고정해 환산한 값 · 미래 실제 점포 수의 확정 예측이 아닙니다.")
    raw = selected[['date','shop_count','city_count','share_per_10000']].rename(columns={
        'date':'기준일','shop_count':'반경 내 점포 수','city_count':'대전 전체 동일 업종','share_per_10000':'대전 동일 업종 1만 개당 주변 점포 수'})
    with st.expander('검증 결과와 계산 방법',expanded=False):
        st.dataframe(raw,hide_index=True,width='stretch',column_config={
            '기준일':st.column_config.DatetimeColumn(format='YYYY-MM-DD'),
            '대전 동일 업종 1만 개당 주변 점포 수':st.column_config.NumberColumn(format='%.1f')})
        st.write(f"2023·2024·2025년 자료로 마지막 {evaluation['validation_date']}의 비중을 예측했습니다. 전체 {evaluation['validation_series']}개 정거장·반경·업종 조합의 평균 절대오차가 작은 방법을 선택해 4개 시점으로 다시 계산합니다.")
        st.dataframe(pd.DataFrame([{'방법':LABELS[k],'비중 평균 절대오차(1만 개당)':evaluation[k+'_mae']} for k in ['trend','persistence']]),hide_index=True)
        st.caption('추세는 log(1+업종 비중)의 시간 기울기를 규제값 4로 축소하고 마지막 관측에 연결합니다. 직전 비중 유지는 변화가 없다고 보는 비교 기준입니다. 한 번의 검증으로 방법을 선택했으므로 독립적인 최종 성능 평가가 아니며, 반경이 겹치는 조합도 독립 표본이 아닙니다. 확률적 신뢰구간은 산출하지 않습니다.')
    st.subheader('2030년 계획 수요를 넣은 시나리오')
    row = demand.loc[demand.station_no==sid].iloc[0]
    median = float(demand.total_2030.median())
    st.write(f"계획 자료 명칭: **{row.plan_name}** · 승차 {int(row.board_2030):,} · 하차 {int(row.alight_2030):,} · 합계 {int(row.total_2030):,}")
    st.caption('대전광역시 정보공개 답변(2026-11)으로 공유된 계획 예측값입니다. 원표 단위·집계기간·정거장 대응은 원자료 확인 전입니다. 현재 유동인구나 실측 이용객으로 표시하지 않습니다.')
    acknowledged = st.checkbox('정거장 번호로 임시 연결한 계획값을 탐색용 가정에 사용',key='forecast_ack')
    strength = st.slider('수요 규모 반영 강도(%)',0,50,0,step=5,disabled=not acknowledged,key='forecast_strength')
    scenario = demand_scenario(result['count'],float(row.total_2030),median,strength,year,acknowledged)
    st.metric('수요 가정 적용 점포 수',f'{scenario:,.1f}개',delta=f"기본 추정 대비 {scenario-result['count']:+,.1f}개")
    st.caption(f'계산: 기본 추정 × [1 + 강도/100 × (정거장 계획 합계 ÷ 45곳 중앙값 {median:,.0f} − 1)]. 강도는 학습된 계수가 아니며 기본값 0%입니다. 2030년 이전에는 적용하지 않고, 이후에는 같은 2030년 계획값을 유지하는 가정입니다. 이 값으로 수익성이나 성장 순위를 판정하지 않습니다.')
    export = pd.DataFrame([{'정거장번호':sid,'현재정거장명':labels[sid],'계획자료명칭':row.plan_name,'반경_m':radius,'업종':industry,'예측기준일':f'{year}-09-30',
        '현재점포수':result['latest_count'],'기본추정':result['count'],'방법':LABELS[method],
        '대전업종규모고정':result['city_reference_count'],'수요가정적용':acknowledged and year>=2030,'수요반영강도_percent':strength,
        '계획승하차합계_단위미확인':row.total_2030,'수요가정추정':scenario,'해석':'비중 추세·수요 가정 시나리오, 트램 인과효과 아님'}])
    st.download_button('선택 조건과 추정 결과 CSV',export.to_csv(index=False).encode('utf-8-sig'),'tram_forecast.csv','text/csv')
    with st.expander('45개 정거장 계획 수요 조회'):
        st.dataframe(demand.rename(columns={'station_no':'정거장번호','plan_name':'계획자료명칭','lines':'노선','board_2030':'2030 승차 계획값','alight_2030':'2030 하차 계획값','total_2030':'2030 합계 계획값'}),hide_index=True,width='stretch')
    st.subheader('공사 영향 상권 조회')
    st.write('시가 분류한 통제구간 직선 500m 이내 상권 명단입니다. 실제 피해·매출 감소를 측정한 자료는 아닙니다.')
    sections = sorted({p.strip() for value in markets.section for p in value.split(';')})
    section = st.selectbox('공구 또는 구간',['전체']+sections,key='forecast_section')
    shown = filter_markets(markets,section)
    st.dataframe(shown.rename(columns={'market':'상권명','section':'공구·구간','source':'출처'}),hide_index=True,width='stretch')
    st.caption(f'{len(shown)}곳 · 상권 주소·좌표·경계와 공사 시점이 없어 현재 정거장과 자동 연결하거나 예측 감소율로 사용하지 않습니다. 여러 공구에 속한 상권은 각 공구 조회에 포함됩니다.')
    with st.expander('자료 출처와 재현'):
        st.write('소상공인시장진흥공단 대전 상가정보 2023-09-30 / 2024-09-30 / 2025-10-30 / 2026-09-30. 원본은 프로젝트 구성요소에 보존하며 동일한 승인 좌표로 각 시점의 거리를 다시 계산했습니다.')
        st.write('팀 공유: 대전광역시 정보공개 답변(2026-11). 표 전사·공유 출처: Kang Seungwan / Commercial-Area-Analysis. 첨부 LICENSE와 README_공유안내 원문을 함께 보존합니다. 데이터의 이용 조건은 코드·문서 MIT 라이선스와 별도로 확인합니다.')
        st.link_button('공유 자료 원본 저장소','https://github.com/KangSeungWan/Commercial-Area-Analysis')
        st.caption('위치도·이용 조건·수요 단위를 원자료와 대조하기 전의 로컬 개발 기능입니다. station_history.csv와 manifest.json에 집계 및 원본 SHA-256을 기록합니다.')
