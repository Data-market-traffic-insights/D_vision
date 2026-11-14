"""사전에 시간 분리한 학습 모델의 평가와 저장된 전망을 표시한다."""
from pathlib import Path
import json
import pandas as pd
import plotly.express as px
import streamlit as st
from shop_prediction import error_metrics

BASE=Path(__file__).resolve().parent
MODEL_NAMES={'persistence':'최근 점포 수 유지','trend':'최근 추세 연장','ridge':'규제 선형 회귀',
             'random_forest':'랜덤포레스트','gradient_boosting':'그래디언트 부스팅'}
HORIZONS={1:'다음 분기',4:'1년 뒤 · 4분기 후'}


@st.cache_data(show_spinner=False)
def load_predictions(signature):
    folder=BASE/'data/shop_ml'
    meta=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    test=pd.read_csv(folder/'test_predictions.csv',dtype={'market_code':str,'origin_quarter':str,'target_quarter':str})
    future=pd.read_csv(folder/'latest_predictions.csv',dtype={'market_code':str,'origin_quarter':str,'target_quarter':str})
    metrics=pd.read_csv(folder/'metrics.csv')
    return meta,test,future,metrics


def pretty_quarter(value):
    value=str(value)
    return f'{value[:4]}년 {value[-1]}분기'


def prediction_page():
    st.header('점포 변화를 학습하면 다음 시점을 맞힐 수 있을까?')
    st.write('과거 점포 증감·업종 구성·신림선 역과의 거리로 미래 점포 수를 학습했습니다. 서울 자료의 시간 분리 평가이며 대전의 예측 결과는 아닙니다.')
    folder=BASE/'data/shop_ml'
    if not (folder/'manifest.json').exists():
        st.info('학습 결과를 준비 중입니다.');return
    signature=tuple((p.name,p.stat().st_mtime_ns,p.stat().st_size) for p in sorted(folder.iterdir()) if p.is_file())
    meta,test,future,metrics=load_predictions(signature)
    a,b,c=st.columns(3)
    horizon=a.selectbox('예측 간격',[1,4],format_func=HORIZONS.get,key='ml_horizon')
    scope=b.selectbox('평가 지역',['신림선 500m 주변','서울 전체 관측 상권'],key='ml_scope')
    sector=c.selectbox('평가 업종',['전체','음식','커피·음료','소매','미용·세탁·수리'],key='ml_sector')
    part=test.loc[test.horizon==horizon]
    if scope=='신림선 500m 주변':part=part.loc[part.new_distance_m<=500]
    if sector!='전체':part=part.loc[part.sector==sector]
    if part.empty:st.info('이 조건의 최종 평가 관측이 없습니다.');return
    selection=meta['selections'][str(horizon)]
    model=selection['learned_model'];baseline=selection['baseline']
    learned=error_metrics(part.actual,part.prediction)
    simple=error_metrics(part.actual,part.baseline_prediction)
    gain=(1-learned['mae']/simple['mae'])*100 if simple['mae'] else 0.
    st.subheader('학습에 쓰지 않은 2025년 실제 값과 비교')
    a,b,c,d=st.columns(4)
    a.metric('학습 모델 평균 오차',f"{learned['mae']:.2f}개")
    b.metric('단순 기준 평균 오차',f"{simple['mae']:.2f}개")
    c.metric('기준 대비 오차 감소',f'{gain:+.1f}%')
    d.metric('평가 관측 수',f'{len(part):,}건')
    st.caption(f"학습 모델: {MODEL_NAMES[model]} / 비교 기준: {MODEL_NAMES[baseline]}. 평균 오차(MAE)는 한 상권·업종·시점의 예측과 관측이 평균 몇 개 다른지를 뜻합니다. 오차 감소율은 예측 정확도가 아닙니다. 같은 상권의 여러 분기와 서로 겹치는 음식·커피 관측이 포함됩니다.")
    if gain>0:
        st.success(f'이번 {scope}·{HORIZONS[horizon]} 평가에서는 학습 모델의 평균 오차가 더 작았습니다. 다른 업종·기간·도시에도 같은 성능이 나온다는 보장은 없습니다.')
    else:
        st.info('이 조건에서는 학습 모델이 단순 기준보다 평균 오차를 줄이지 못했습니다. 모델을 만들었다는 사실만으로 실용성이 확보되지는 않습니다.')
    st.write(f"**선택 과정:** 2021~2023년 정답으로 학습하고, 2024년 성적으로 학습 방법을 **{MODEL_NAMES[model]}**로 고정한 뒤 2025년을 평가했습니다. 2024년 전체 관측에서는 **{MODEL_NAMES[selection['recommended']]}**가 더 좋았으며, 2025년 결과를 보고 방법을 다시 고르지 않았습니다.")
    by_sector=[]
    for name,group in part.groupby('sector'):
        lm=error_metrics(group.actual,group.prediction);bm=error_metrics(group.actual,group.baseline_prediction)
        by_sector.append({'업종':name,'평가 건수':len(group),'학습 모델 MAE(개)':lm['mae'],'단순 기준 MAE(개)':bm['mae'],
                          '오차 감소(%)':(1-lm['mae']/bm['mae'])*100 if bm['mae'] else None})
    st.dataframe(pd.DataFrame(by_sector),hide_index=True,width='stretch',column_config={
        '학습 모델 MAE(개)':st.column_config.NumberColumn(format='%.2f'),
        '단순 기준 MAE(개)':st.column_config.NumberColumn(format='%.2f'),
        '오차 감소(%)':st.column_config.NumberColumn(format='%.1f')})
    evaluation,forecast,methodology=st.tabs(['실제 예측과 관측','자료 기준일의 전망','무엇을 학습했나'])
    with evaluation:
        available=part[['market_code','market_name']].drop_duplicates().sort_values('market_name')
        names=available.set_index('market_code').market_name.to_dict()
        options=available.market_code.tolist()
        if st.session_state.get('ml_market') not in options:st.session_state['ml_market']=options[0]
        market=st.selectbox('평가한 상권',options,format_func=names.get,key='ml_market')
        local=part.loc[part.market_code==market]
        sectors=sorted(local.sector.unique())
        if st.session_state.get('ml_market_sector') not in sectors:st.session_state['ml_market_sector']=sectors[0]
        picked=st.selectbox('상권 내 업종',sectors,key='ml_market_sector')
        chosen=local.loc[local.sector==picked].sort_values('target_quarter').copy()
        chosen['평가 시점']=chosen.target_quarter.map(pretty_quarter)
        plot=chosen[['평가 시점','actual','prediction','baseline_prediction']].rename(columns={
            'actual':'실제 관측','prediction':'학습 모델','baseline_prediction':'단순 기준'}).melt(id_vars='평가 시점',var_name='구분',value_name='점포 수')
        st.plotly_chart(px.line(plot,x='평가 시점',y='점포 수',color='구분',markers=True),key='ml_backtest_chart',config={'displaylogo':False})
        display=chosen[['origin_quarter','target_quarter','count','actual','prediction','baseline_prediction']].rename(columns={
            'origin_quarter':'입력 기준 분기','target_quarter':'예측 대상 분기','count':'입력 점포 수','actual':'실제 점포 수',
            'prediction':'학습 모델 예측','baseline_prediction':'단순 기준 예측'})
        st.dataframe(display,hide_index=True,width='stretch',column_config={
            '학습 모델 예측':st.column_config.NumberColumn(format='%.1f'),'단순 기준 예측':st.column_config.NumberColumn(format='%.1f')})
        st.caption('다음 분기 결과는 각 예측 시점까지의 최신 관측을 넣는 순차 평가입니다. 2024년 말에 2025년 전체를 한꺼번에 예측한 그래프가 아닙니다. 자료 공개 지연과 과거판 개정은 재현하지 못했습니다.')
        st.download_button('선택 조건의 최종 평가 CSV',part.to_csv(index=False).encode('utf-8-sig'),'shop_ml_test_2025.csv','text/csv')
    with forecast:
        st.warning('입력 자료의 마지막 시점은 2025년 4분기입니다. 아래는 그 시점 자료로 계산한 전망이며, 2026년 최신 상권을 반영한 전망이 아닙니다.')
        latest=future.loc[(future.horizon==horizon)&(future.market_code==market)&(future.sector==picked)]
        if latest.empty:st.info('선택 상권·업종의 마지막 4개 분기가 연속 관측되지 않아 전망을 표시하지 않습니다.')
        else:
            row=latest.iloc[0]
            st.write(f"**{names[market]} · {picked}** / 입력: {pretty_quarter(row.origin_quarter)} / 대상: {pretty_quarter(row.target_quarter)}")
            a,b,c=st.columns(3)
            a.metric('입력 시점 관측',f'{int(row["count"]):,}개')
            b.metric('학습 모델 전망',f'{row.prediction:,.1f}개',f'{row.prediction-row["count"]:+,.1f}개',delta_color='off')
            c.metric('단순 기준 전망',f'{row.baseline_prediction:,.1f}개')
            st.caption('예측값은 평균적 추정이라 소수점으로 표시합니다. 미래 매출·순이익·트램 개통 효과를 뜻하지 않으며 통계적 예측구간은 아직 산출하지 않았습니다.')
            st.download_button('선택 상권 전망 CSV',latest.to_csv(index=False).encode('utf-8-sig'),'shop_ml_outlook.csv','text/csv')
    with methodology:
        st.write('**입력:** 최근 4개 분기의 점포 수·증감·평균·변동, 같은 시점의 전체 제공업종 규모와 업종 구성, 상권 위치·유형·자치구, 신림선 예정지까지 거리, 계절과 운영 여부입니다. 상권 ID 자체를 학습 입력으로 넣지 않았습니다.')
        st.write('**학습 대상:** 다음 분기 또는 4분기 뒤의 log(1+점포 수) 변화량입니다. 결측 분기를 0으로 채우지 않고 최근 4개 분기가 연속 관측된 경우만 사용합니다. 결측 대체값과 표준화는 학습 기간에서만 계산합니다.')
        st.dataframe(metrics.loc[(metrics.horizon==horizon)&(metrics.split=='validation_2024')][['model','rows','mae','rmse']].assign(
            model=lambda f:f.model.map(MODEL_NAMES)).rename(columns={'model':'2024년 비교 방법','rows':'관측 수','mae':'MAE(개)','rmse':'RMSE(개)'}),hide_index=True)
        check=next(a for a in meta['ablation'] if a['horizon']==horizon)
        st.write(f"특성 추가 진단(2025년 전체): 과거 점포 특성만 사용한 같은 모델의 MAE **{check['history_only_test_mae']:.2f}개**, 업종 구성·위치 등도 사용한 모델 **{check['full_test_mae']:.2f}개**. 이 비교는 추가 특성이 항상 유용하다는 증거나 각 특성의 인과적 효과는 아닙니다.")
        st.write('**기존 팀 공유 자료의 역할:** 대전 2030년 계획 수요는 별도 조회·가정 시나리오에, 공사 영향 상권 52곳은 공구별 조회에 사용합니다. 서울의 과거 정답과 대응하지 않아 이번 학습 입력에서는 제외했습니다. 2022년 실제 승하차도 전체 기간과 대응하지 않아 제외했습니다.')
        for note in meta['limitations']:st.caption('• '+note)
        st.caption('웹은 오프라인에서 학습·평가한 결과를 표시합니다. scikit-learn으로 학습한 모델 파일과 재현 스크립트를 로컬 개발 프로젝트에 보존합니다.')
