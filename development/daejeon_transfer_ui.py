"""대전 실측 검증과 연간 전이 모델의 조건부 전망을 함께 표시한다."""
from pathlib import Path
import json
import hashlib
import pandas as pd
import plotly.express as px
import streamlit as st
from daejeon_transfer import MODEL_NAMES
from shop_prediction import error_metrics

BASE = Path(__file__).resolve().parent


def transfer_page():
    folder = BASE/'data/daejeon_transfer'
    if not (folder/'manifest.json').exists():
        st.info('대전 적용 실험 자료가 없습니다. 오프라인 학습 결과를 먼저 준비하세요.')
        return
    meta = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if hashlib.sha256((BASE/'data/tram_stations.csv').read_bytes()).hexdigest()!=meta['station_sha256']:
        st.error('정거장 자료가 학습 당시와 달라졌습니다. 위치별 집계를 다시 준비해야 합니다.')
        return
    panel = pd.read_csv(folder/'panel.csv',dtype={'anchor_id':str})
    tests = pd.read_csv(folder/'test_predictions.csv',dtype={'anchor_id':str})
    future = pd.read_csv(folder/'latest_predictions.csv',dtype={'anchor_id':str})
    metrics = pd.read_csv(folder/'metrics.csv')
    local = tests.loc[tests.city.eq('대전')]
    lm = error_metrics(local.actual,local.prediction)
    bm = error_metrics(local.actual,local.baseline_prediction)
    st.header('대전 적용 실험 · 500m 주변 점포 수')
    st.write('서울과 대전의 같은 출처 상가자료를 같은 반경으로 집계해 연간 모델을 다시 학습했습니다. 대전 정답은 학습과 모델 선택에 사용하지 않았습니다.')
    st.caption(f"서울 {meta['seoul_anchors']}개 격자 중심에서 학습 · 대전 근사 좌표 {meta['daejeon_anchors']}개 정거장에서 평가 · 음식·카페·소매·수리·개인")
    st.subheader('대전 실제 변화로 검사한 결과 · 2025.10 → 2026.09')
    a,b,c = st.columns(3)
    a.metric('학습 모델 평균 오차',f"{lm['mae']:.2f}개")
    b.metric('비교 기준 평균 오차',f"{bm['mae']:.2f}개")
    c.metric('평가한 정거장',f"{meta['daejeon_anchors']}곳",'4개 업종 · 20건',delta_color='off')
    if lm['mae']>=bm['mae']:
        st.warning('이번 대전 평가에서는 학습 모델이 현재 점포 수 유지 기준보다 못했습니다. 아래 모델 전망은 실험 결과이며, 창업 판단을 위한 검증된 예측으로 권하지 않습니다.')
    else:
        st.info('이번 대전 구간에서는 모델의 오차가 더 작았습니다. 다만 한 구간·5개 위치의 결과로 향후 성능을 보장하지는 못합니다.')
    st.caption(f"학습 모델: {MODEL_NAMES[meta['selected_learned_model']]} / 비교 기준: {MODEL_NAMES[meta['selected_baseline']]}. MAE는 위치·업종별 점포 수의 평균 절대 차이입니다. 정확도 %나 미래 오차 범위가 아닙니다.")
    labels = future[['anchor_id','anchor_name']].drop_duplicates().set_index('anchor_id').anchor_name.to_dict()
    a,b = st.columns(2)
    sid = a.selectbox('대전 적용 정거장',list(labels),format_func=lambda k:f'{k} · {labels[k]}',key='transfer_station')
    sector = b.selectbox('대전 적용 업종',meta['sectors'],key='transfer_sector')
    picked = future.loc[future.anchor_id.eq(sid)&future.sector.eq(sector)].iloc[0]
    past = local.loc[local.anchor_id.eq(sid)&local.sector.eq(sector)].iloc[0]
    outlook, evaluation, method = st.tabs(['2027년 실험 전망','2026년 예측과 실제 비교','학습 근거와 한계'])
    with outlook:
        st.subheader(f'{labels[sid]} · {sector} · 직선 500m')
        st.write('입력 기준일 **2026년 9월 30일** → 예측 대상일 **2027년 9월 30일**')
        a,b,c = st.columns(3)
        a.metric('입력 시점 등록 점포',f'{int(picked["count"]):,}개')
        b.metric('학습 모델 실험값',f'{picked.prediction:,.1f}개',f'{picked.prediction-picked["count"]:+,.1f}개',delta_color='off')
        c.metric('점포 수 유지 기준',f'{picked.persistence_prediction:,.1f}개')
        if bool(picked.outside_training_range):
            st.warning('선택 입력의 일부 특성이 서울 학습 자료의 최소~최대 범위를 벗어납니다. 도시 간 적용에 특히 주의가 필요합니다.')
        st.caption('소수점은 모델의 평균적 추정입니다. 트램 개통 효과와 2030년 계획 수요를 더한 값이 아닙니다. 카페는 음식에 포함되므로 두 수를 더하면 중복됩니다.')
        col = {'음식':'food_count','카페':'coffee_count','소매':'retail_count','수리·개인':'service_count'}[sector]
        history = panel.loc[panel.city.eq('대전')&panel.anchor_id.eq(sid)].sort_values('date')
        chart = [{'기준일':row.date,'점포 수':row[col],'구분':'실제 등록 점포'} for _,row in history.iterrows()]
        for key,label in [('prediction','학습 모델 실험'),('persistence_prediction','점포 수 유지 기준')]:
            chart.extend([{'기준일':picked.origin_date,'점포 수':picked['count'],'구분':label},
                          {'기준일':picked.target_date,'점포 수':picked[key],'구분':label}])
        st.plotly_chart(px.line(pd.DataFrame(chart),x='기준일',y='점포 수',color='구분',markers=True),key='transfer_history',config={'displaylogo':False})
        all_rows = future.loc[future.sector.eq(sector)].copy()
        all_rows['delta'] = all_rows.prediction-all_rows['count']
        view = all_rows[['anchor_name','count','prediction','delta','persistence_prediction','outside_training_range']].rename(columns={
            'anchor_name':'정거장','count':'2026 등록 점포','prediction':'2027 모델 실험값','delta':'모델 추정 증감',
            'persistence_prediction':'유지 기준','outside_training_range':'학습 입력 범위 밖'})
        st.dataframe(view,hide_index=True,width='stretch',column_config={key:st.column_config.NumberColumn(format='%.1f') for key in ['2027 모델 실험값','모델 추정 증감','유지 기준']})
        st.download_button('대전 전체 업종 전망·기준 비교 CSV',future.to_csv(index=False).encode('utf-8-sig'),'daejeon_2027_transfer_experiment.csv','text/csv')
    with evaluation:
        st.write(f"**선택 위치·업종:** 2025년 입력 {int(past['count']):,}개 → 2026년 실제 **{int(past.actual):,}개** / 모델 예측 **{past.prediction:,.1f}개** / 유지 기준 **{past.persistence_prediction:,.1f}개**")
        per = []
        for name,group in local.groupby('sector'):
            per.append({'업종':name,'관측 수':len(group),'모델 MAE':error_metrics(group.actual,group.prediction)['mae'],
                        '유지 기준 MAE':error_metrics(group.actual,group.persistence_prediction)['mae']})
        st.dataframe(pd.DataFrame(per),hide_index=True,column_config={key:st.column_config.NumberColumn(format='%.2f') for key in ['모델 MAE','유지 기준 MAE']})
        view = local[['anchor_name','sector','count','actual','prediction','persistence_prediction']].rename(columns={
            'anchor_name':'정거장','sector':'업종','count':'2025 입력','actual':'2026 실제',
            'prediction':'2026 모델 예측','persistence_prediction':'유지 기준'})
        st.dataframe(view,hide_index=True,width='stretch')
        st.caption('같은 위치의 여러 업종이 포함되고 음식과 카페도 중복됩니다. 20개 독립된 지역에서 검증한 것이 아닙니다. 원본 등록 여부의 변화를 개업·폐업으로 단정하지 않습니다.')
        st.download_button('대전 보류 평가 전체 CSV',local.to_csv(index=False).encode('utf-8-sig'),'daejeon_transfer_test_2026.csv','text/csv')
    with method:
        st.write('**기존 분기 모델과 구분:** 서울 분기 자료의 업종·상권 단위와 대전 연간 상가자료는 다릅니다. 이번에는 전국 상가정보의 서울·대전 파일 8개로 동일 출처·동일 반경·동일 업종 정의를 맞춘 별도 모델을 만들었습니다.')
        st.write('**입력:** 입력 시점의 업종 점포 수, 전체 점포 수, 음식·카페·소매·수리·개인의 구성 비율, 업종 종류. 과거 증감·역 거리·수요를 배웠다고 주장하지 않습니다.')
        st.write('**시간 분리:** 서울 2023→2024 학습 → 서울 2024→2025 검증으로 모델 선택 → 서울 2025년 정답까지 재학습 → 고정한 모델로 서울·대전 2025→2026 평가 및 대전 2026→2027 전망. 실제 날짜 간격으로 log(1+점포 수) 변화를 연율화합니다.')
        validation = metrics.loc[metrics.split.eq('seoul_validation_2025')].copy()
        validation['model'] = validation.model.map(MODEL_NAMES)
        st.dataframe(validation[['model','rows','mae','rmse']].rename(columns={'model':'서울 검증 방법','rows':'평가 건수','mae':'MAE','rmse':'RMSE'}),hide_index=True)
        st.write(f"서울 검증에서 가장 좋았던 방법도 **{MODEL_NAMES[meta['validation_recommendation']]}**였습니다. 모델 예측은 비교 실험으로 남기며 대전 평가를 보고 다시 고르지 않았습니다.")
        for note in meta['limitations']: st.caption('• '+note)
        st.caption('2030년 계획 수요와 공사 상권 52곳은 기존 대전 예정지 분석에서 조회합니다. 과거 서울 정답과 연결된 학습 근거가 없어 이번 모델의 가중치로 사용하지 않았습니다.')
