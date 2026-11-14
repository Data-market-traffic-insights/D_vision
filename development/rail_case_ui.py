"""실제 개통 사례의 근거와 한계를 창업자에게 보여 주는 화면."""
from pathlib import Path
import json
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from rail_case_study import evidence_status

BASE=Path(__file__).resolve().parent


@st.cache_data(show_spinner=False)
def load_study(signature):
    folder=BASE/'data/sillim_study'
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    results=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    events=pd.read_csv(folder/'events.csv',dtype={'quarter':str})
    geography=pd.read_csv(folder/'geography.csv',dtype={'market_code':str,'nearest_station':str})
    matches=pd.read_csv(folder/'matched_markets.csv',dtype={'market_code':str,'station_id':str})
    traffic=pd.read_csv(folder/'station_ridership.csv',dtype={'station_id':str})
    mapping=pd.read_csv(folder/'industry_mapping.csv')
    return manifest,results,events,geography,matches,traffic,mapping


def case_study_page():
    st.header('신림선 개통 전후, 상권은 어떻게 달라졌을까?')
    folder=BASE/'data/sillim_study'
    if not folder.exists():
        st.info('신림선 비교 자료가 준비되지 않았습니다.');return
    signature=tuple((p.name,p.stat().st_mtime_ns,p.stat().st_size) for p in sorted(folder.iterdir()) if p.is_file())
    manifest,results,events,geo,matches,traffic,mapping=load_study(signature)
    st.write('2022년 5월 개통한 신림선 주변 상권을, 개통 전 규모와 추세가 비슷했던 서울의 다른 상권과 비교했습니다.')
    st.caption('2021~2025년 20개 분기 원자료 · 2022년 2분기 제외 · 개통 전 5개 / 개통 후 14개 분기 · 매출이 아닌 원표 점포 수 분석')
    a,b=st.columns(2)
    sector=a.selectbox('개통 사례 업종',['음식','커피·음료','소매','미용·세탁·수리'],key='sillim_sector')
    radius=b.selectbox('역과 상권 대표점 사이 거리(m)',[300,500,700],index=1,key='sillim_radius')
    result=next(r for r in results if r['sector']==sector and r['radius_m']==radius)
    if result['status']!='estimated':
        st.info('이 조건에는 비교 가능한 상권 쌍이 없습니다.');return
    status=evidence_status(result,results)
    st.subheader(status)
    if result['pre_check_flag']:
        st.warning('개통 전인 2022년 1분기에도 두 집단의 차이가 달라졌거나, 매칭 후 특성 차이가 사전 기준을 초과했습니다. 아래 증가·감소 수치를 신림선 효과로 해석하지 마세요.')
    elif result['low_pct']<=0<=result['high_pct']:
        st.info('관측된 비교 차이의 구간에 0이 포함됩니다. 이 자료와 비교 조건으로 개통 후 추가 증가 또는 감소를 뚜렷하게 구분하지 못했습니다. 효과가 없음을 입증한 것도 아닙니다.')
    a,b,c=st.columns(3)
    a.metric('관측된 개통 전후 비교 차이',f"{result['effect_pct']:+.1f}%",delta_color='off')
    b.metric('역 단위 재표집 95% 구간',f"{result['low_pct']:+.1f} ~ {result['high_pct']:+.1f}%")
    c.metric('주변 / 비교 상권',f"{result['matched_markets']} / {result['control_markets']}곳")
    st.caption(f"{result['station_clusters']}개 역 군집 · log(1+점포 수)의 이중 차이를 expm1으로 환산한 값이며 실제 점포 수 증가율·예측 정확도·인과효과 확정값이 아닙니다. 재표집 구간은 누락 변수나 잘못된 비교군 선택을 해결하지 않습니다.")
    st.write('**창업자가 읽을 수 있는 내용:** '+(
        '커피·음료의 개통 후 증가 차이가 보이더라도, 이미 개통 전부터 비교 상권과 다르게 움직인 흔적이 있어 트램 주변 카페 증가율로 가져올 근거가 부족합니다.' if sector=='커피·음료' and result['pre_check_flag'] else
        f'{sector} 업종은 이번 비교에서 개통 후 일관된 추가 증가·감소가 확인됐다고 말하기 어렵습니다. 대전에서도 무조건 점포가 늘어난다는 전제보다 현재 상권·임대료·보행 동선을 함께 확인해야 합니다.' if result['low_pct']<=0<=result['high_pct'] else
        '이번 조건에서 차이가 관측됐지만 다른 반경·개통 전 점검과 누락 요인을 함께 확인해야 합니다. 성장성 순위나 대전의 증가율로 사용하지 않습니다.'))
    st.subheader('개통 전부터 두 집단이 다르게 움직였는가?')
    series=events.loc[(events.sector==sector)&(events.radius_m==radius)].copy()
    series['시점']=series.quarter.str[:4]+' Q'+series.quarter.str[-1]
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=series['시점'],y=series.effect_pct,mode='lines+markers',name='비교 차이',
        error_y={'type':'data','symmetric':False,'array':series.high_pct-series.effect_pct,
                 'arrayminus':series.effect_pct-series.low_pct},line={'color':'#127C80'}))
    fig.add_hline(y=0,line_dash='dash',line_color='#999999')
    fig.update_layout(yaxis_title='개통 전 평균 대비 비교 차이(%)',xaxis_title='분기',height=380,margin=dict(l=0,r=0,t=20,b=0))
    st.plotly_chart(fig,key='sillim_event_chart',config={'displaylogo':False})
    st.caption('2022 Q1까지 개통 전, 2022 Q3부터 개통 후입니다. 개통이 걸친 2022 Q2는 제외했습니다. 점과 막대는 분기별 탐색 결과로, 0 포함 여부만으로 개통 효과를 확정하지 않습니다.')
    st.write(f"2021년으로 비교군을 고른 뒤 남겨 둔 2022 Q1의 비교 차이: **{result['placebo_pct']:+.1f}%** "
             f"(재표집 구간 {result['placebo_low_pct']:+.1f}~{result['placebo_high_pct']:+.1f}%). "
             '개통 전 점검 한 분기를 통과해도 두 집단이 같은 추세였다는 보장은 없습니다.')
    comparison, sensitivity, demand_tab = st.tabs(['주변 상권과 비교군','반경·업종별 결과','실제 승하차와 대전 적용'])
    with comparison:
        indexed=series[['시점','treated_mean','control_mean']].copy()
        for column in ['treated_mean','control_mean']:
            baseline=float(series.loc[series.quarter.isin(manifest['pre_quarters']),column].mean())
            indexed[column]=indexed[column]/baseline*100
        indexed=indexed.rename(columns={'treated_mean':'신림선 주변 상권','control_mean':'매칭 비교 상권'})
        index_long=indexed.melt(id_vars='시점',var_name='집단',value_name='개통 전 평균=100')
        st.plotly_chart(px.line(index_long,x='시점',y='개통 전 평균=100',color='집단',markers=True),key='sillim_group_chart',config={'displaylogo':False})
        names=geo.set_index('market_code').market_name.to_dict()
        rows=[]
        for pair in result['pairs']:
            rows.append({'주변 상권':names[pair['treated']],'비교 상권 1':names[pair['controls'][0]],
                         '비교 상권 2':names[pair['controls'][1]],'가까운 신림선 역 번호':pair['station_id']})
        st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
        st.caption('상권 대표점으로 거리를 분류합니다. 상권 전체의 점포 수를 사용하며 실제 반경 안의 개별 점포를 센 값은 아닙니다. 비교군은 신림선 역 1~5km, 같은 상권 유형·다른 노선 역 접근 조건의 시장에서 개통 전 자료로만 선정했습니다.')
    with sensitivity:
        report=pd.DataFrame([{k:r[k] for k in ['sector','radius_m','matched_markets','station_clusters','effect_pct','low_pct','high_pct','pre_check_flag']}|
                             {'해석':evidence_status(r,results)} for r in results if r['status']=='estimated'])
        report=report.rename(columns={'sector':'업종','radius_m':'반경(m)','matched_markets':'주변 상권 수',
            'station_clusters':'역 군집 수','effect_pct':'비교 차이(%)','low_pct':'구간 하한(%)',
            'high_pct':'구간 상한(%)','pre_check_flag':'개통 전 점검 주의'})
        st.dataframe(report,hide_index=True,width='stretch',column_config={c:st.column_config.NumberColumn(format='%.1f') for c in report.columns if '(%)' in c})
        st.caption('같은 자료의 4개 업종·3개 반경을 탐색했습니다. 다중 비교 보정된 유의성 검정이 아니며, 유리한 한 결과만 선택하면 안 됩니다.')
        st.download_button('전체 비교 결과 CSV',report.to_csv(index=False).encode('utf-8-sig'),'sillim_comparison_results.csv','text/csv')
    with demand_tab:
        st.write('**2022년 실제 승하차 기록은 확보했습니다. 수요가 점포 수를 얼마나 바꾸는지의 계수는 아직 검증되지 않았습니다.**')
        st.dataframe(traffic[['station_name','days','daily_board_alight']].rename(columns={
            'station_name':'신림선 역','days':'개통 후 관측 일수','daily_board_alight':'일평균 승차+하차(건)'}),
            hide_index=True,width='stretch',column_config={'일평균 승차+하차(건)':st.column_config.NumberColumn(format='%.1f')})
        st.caption('2022-05-28~12-31, 218일. 승하차 합계는 고유 방문객 수가 아니며 개통 초기 수요입니다. 2023~2025년 승하차 시계열은 현재 학습자료에 없습니다.')
        st.info('대전 점포 수에 이 비교 차이를 자동으로 적용하지 않습니다. 신림선은 지하 경전철이고 대전은 노면 트램이며, 업종·공간 집계 기준과 도시 조건의 대응도 검증되지 않았습니다.')
        st.write('다음 연결에 필요한 근거: 비교 노선·도시 추가, 역별 수요 시계열, 인구·개발사업 요인, 서울 세부 업종과 대전 업종 정의의 대응입니다.')
    with st.expander('2025년을 남겨 둔 재현 점검과 재현 방법'):
        st.write('2022 Q3~2024년에 관측된 상권별 차이를 사용해 2025년의 차이를 재현했습니다. 비교 상권의 실제 2025년 값을 알고 계산하는 조건부 점검이므로 미래 사전 예측 성능은 아닙니다.')
        st.dataframe(pd.DataFrame([{'기준':'비교군 변화만 사용','log 차이 평균 절대오차':result['holdout_no_shift_mae']},
                                  {'기준':'2022~2024년 상권별 추가 차이 사용','log 차이 평균 절대오차':result['holdout_shift_mae']}]),hide_index=True)
        st.write('2021년 업종 규모·연내 변화·전체 제공업종 규모를 표준화해 최근접 비교군 2곳을 비복원 매칭합니다. 사전 RMS 거리 제한은 1.0, 평균 특성 불균형 주의 기준은 0.25입니다. 효과 계산은 개통 전 평균 격차와 개통 후 평균 격차의 차이입니다.')
        st.dataframe(mapping.loc[mapping.sector==sector].rename(columns={'sector':'분석 묶음','source_code':'원표 업종코드','source_name':'원표 업종명'}),hide_index=True)
        st.write('원표 점포_수(stor_co)를 사용하고 프랜차이즈 수를 임의로 더하지 않습니다. 제공 행이 없는 상권·분기를 0으로 채우지 않으며, 분석기간에 모두 관측된 상권만 사용합니다. 이 선택에도 편향이 있을 수 있습니다.')
        for note in manifest['limitations']:st.caption('• '+note)
        st.link_button('점포 원자료·정의','https://data.seoul.go.kr/dataList/OA-15577/S/1/datasetView.do')
        st.link_button('경계 원자료','https://data.seoul.go.kr/dataList/OA-15560/S/1/datasetView.do')
        st.caption('출처: 서울특별시·서울신용보증재단 상권분석서비스, 서울특별시 교통카드 자료, 국가철도공단 표준데이터 역사정보. 분석 방법·기간·원본 SHA-256은 data/sillim_study/manifest.json에 기록합니다.')
