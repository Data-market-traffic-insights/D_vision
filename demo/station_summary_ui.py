"""Main station view and the single food-sector forecast hypothesis."""
import json
from hashlib import sha256
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from tram_analysis import verified_stations
from tram_forecast import load_forecast_data

BASE = Path(__file__).resolve().parent
RADIUS = 500


@st.cache_data(show_spinner=False)
def evaluation(folder, version, result_signature):
    meta = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if version != meta['station_sha256']:
        return None
    choice = meta['selections']['음식']
    results = pd.read_csv(folder / 'test_predictions.csv', dtype={'anchor_id': str})
    food = results.loc[results.kind.eq('station') & results.sector.eq('음식')]
    keys = ['anchor_id', 'count', 'actual']
    model = food.loc[food.method.eq(choice['learned']), keys + ['prediction']].copy()
    keep = food.loc[food.method.eq('persistence'), keys + ['prediction']]
    return model.merge(keep, on=keys, validate='one_to_one', suffixes=('_model', '_keep'))


def show_hypothesis(station_id):
    with st.expander('음식 업종 예측 실험 · 가설과 검증'):
        st.markdown('**가설:** 최근 점포 수와 업종 구성, 주변 상권의 변화를 학습하면 대전 트램 예정지 500m 안의 다음해 음식 점포 수를 현재 수준 유지보다 잘 추정할 수 있다.')
        st.write('음식 한 업종과 약 1년 뒤의 등록 점포 수에 집중했습니다. 대전의 117개 격자로 학습하고, 반경이 겹치는 곳을 제외한 정거장 5곳에서 2025년 10월 자료로 2026년 9월을 추정했습니다.')
        version = sha256((BASE / 'data/tram_stations.csv').read_bytes()).hexdigest()
        folder = BASE / 'data/daejeon_local_ml'
        paths = [folder / 'manifest.json', folder / 'test_predictions.csv']
        if not all(p.is_file() for p in paths):
            st.info('저장된 예측 검증 결과가 없습니다.')
            return
        signature = tuple((p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
        result = evaluation(folder, version, signature)
        if result is None:
            st.info('좌표가 변경되어 기존 평가를 표시할 수 없습니다.')
            return
        model_error = (result.prediction_model - result.actual).abs()
        keep_error = (result.prediction_keep - result.actual).abs()
        model, keep, wins = st.columns(3)
        model.metric('학습 모델 평균 오차', f'{model_error.mean():.2f}개')
        keep.metric('점포 수 유지 평균 오차', f'{keep_error.mean():.2f}개')
        wins.metric('유지보다 오차가 작았던 곳', f'{(model_error < keep_error).sum()}/{len(result)}곳')
        selected = result.loc[result.anchor_id.eq(station_id)]
        if not selected.empty:
            row = selected.iloc[0]
            st.write(f"선택 정거장 · 2025년 {int(row['count']):,}개 → 2026년 실제 {int(row.actual):,}개 · 모델 추정 {row.prediction_model:,.1f}개")
        st.caption('모델은 2025년 공간 검증으로 선택했습니다. 음식으로 범위를 좁힌 결정은 기존 결과를 본 뒤에 이뤄졌으므로, 이 수치는 회고 비교입니다.')
        st.warning('향후 증가·감소 방향은 불확실합니다. 한 기간·정거장 5곳에서 비교한 값이며, 트램 개통에 따른 변화량은 검증하지 못했습니다.')


def station_summary_page(stations, to_finder):
    st.title('트램 예정지 주변 상권은 어떻게 바뀌었을까요?')
    st.write('정류장 주변 500m의 점포 변화부터 살펴보고, 내 조건으로 창업 후보지를 비교해보세요.')
    history, _, _, _ = load_forecast_data(BASE)
    available = verified_stations(stations)
    names = available.loc[available.station_id.isin(history.station_id)].set_index('station_id').station_name.to_dict()
    if not names:
        st.info('점포 이력과 승인 좌표가 함께 있는 정거장이 없습니다.')
        return

    station, industry = st.columns(2)
    sid = station.selectbox('정거장', list(names), format_func=names.get, key='summary_station')
    group = history.loc[history.station_id.eq(sid) & history.radius_m.eq(RADIUS)]
    industries = sorted(group.industry.unique())
    sector = industry.selectbox('업종', industries, index=industries.index('음식'), key='summary_industry')
    rows = group.loc[group.industry.eq(sector)].sort_values('date')
    first, previous, latest = rows.iloc[0], rows.iloc[-2], rows.iloc[-1]
    current, recent, long_term = st.columns(3)
    current.metric('2026년 9월 등록 점포', f'{latest.shop_count:,}개')
    recent.metric('직전 관측 대비', f'{latest.shop_count - previous.shop_count:+,}개')
    long_term.metric('2023년 9월 대비', f'{latest.shop_count - first.shop_count:+,}개')

    chart_data = rows.assign(관측일=pd.to_datetime(rows.date))
    chart = px.line(chart_data, x='관측일', y='shop_count', markers=True, labels={'shop_count': '등록 점포(개)'})
    chart.update_traces(line_color='#127C80', line_width=3, marker_size=8,
                        hovertemplate='%{x|%Y-%m-%d}<br>%{y:,}개<extra></extra>')
    chart.update_xaxes(tickvals=chart_data.관측일, tickformat='%Y.%m', title_text=None)
    chart.update_yaxes(tickformat=',d', separatethousands=True)
    chart.update_layout(height=270, margin=dict(l=10, r=20, t=10, b=12))
    st.plotly_chart(chart, key='station_history_summary', config={'displayModeBar': False})
    st.caption('같은 근사 좌표의 직선 500m 이내 · 실제 관측 4회 · 등록 점포 수 증감에는 수집 범위 변경이 포함될 수 있습니다.')
    st.button('이 정거장에서 내 조건으로 추천받기', key='hero_finder',
              on_click=to_finder, args=(sector, RADIUS, sid), type='primary')

    st.caption('향후 증가·감소 방향은 아직 불확실합니다.')
    show_station_context(sid)
    show_hypothesis(sid)


def show_station_context(station_id):
    path = BASE / 'data/station_context.json'
    if not path.is_file():
        return
    context = json.loads(path.read_text(encoding='utf-8'))
    version = sha256((BASE / 'data/tram_stations.csv').read_bytes()).hexdigest()
    station = context['stations'].get(station_id)
    if version != context['station_sha256'] or context['radius_m'] != RADIUS or station is None:
        st.caption('현재 좌표에 맞는 개·폐업 및 교통 집계가 없습니다.')
        return

    st.subheader('선택 정거장 주변 500m 참고 지표')
    food_card, transit_card = st.columns(2)
    with food_card.container(border=True):
        food = station['food']
        st.markdown('**일반음식점 개·폐업**')
        start, end = context['food_period']
        st.caption(f'{start} ~ {end} · 일반음식점 인허가 기준')
        opened, closed = st.columns(2)
        for column, label, count in [(opened, '신규 인허가', food['opened']),
                                     (closed, '폐업 등록', food['closed'])]:
            rate = f"{100 * count / food['at_start']:.1f}%" if food['at_start'] else None
            column.metric(label, f'{count:,}건')
            column.caption(f'기간 시작 영업 기록 대비 {rate}' if rate else '기간 시작 영업 기록 0건')
        st.caption(f"기간 시작 영업 기록 {food['at_start']:,}건 · 위치가 확인된 인허가 기록 기준")
    with transit_card.container(border=True):
        st.markdown('**기존 대중교통 이용량**')
        bus = station['bus']
        metro = station['metro']
        bus_label = f"{context['bus_year']}년 일평균 버스"
        metro_label = f"{context['metro_month']} 월간 대전 도시철도 1호선"
        if bus['matched']:
            st.write(f"**{bus_label}**  ·  승차 {bus['board']:,}건 / 하차 {bus['alight']:,}건")
            st.caption(f"위치 자료에서 500m 이내 {bus['nearby']}곳 중 이용량 연결 {bus['matched']}곳")
        else:
            st.write(f'**{bus_label}**  ·  반경 내 이용량 연결 자료 없음')
        if metro['stations']:
            st.write(f"**{metro_label}**  ·  승차 {metro['board']:,}건 / 하차 {metro['alight']:,}건")
            st.caption('포함 역 ' + ' · '.join(metro['stations']))
        else:
            st.write(f'**{metro_label}**  ·  반경 500m 이내 역 없음')
        st.caption('기간과 단위가 각각 다릅니다. 승하차는 상권 방문객 수와 구분합니다.')

    with st.expander('참고 지표 출처와 집계 기준'):
        audit = context['food_audit']
        location_date = ', '.join(context['bus_audit']['position_date'])
        st.write(f"개·폐업 비율은 해당 기간 인허가·폐업 건수를 기간 시작 영업 기록 수로 각각 나눈 값입니다. 대전 원본 전체에서 기간 내 위치 누락·범위 밖 인허가 {audit['excluded_openings']}건과 폐업 {audit['excluded_closures']}건을 반경 집계에서 제외했습니다.")
        st.markdown('[일반음식점 인허가 원자료](https://www.data.go.kr/data/15096283/standard.do)')
        st.write(f'버스는 {location_date} 위치 자료와 일평균 이용량을 정류장 ID로 연결하고 명칭·ARS 번호를 대조했습니다. 중복이나 불일치로 연결할 수 없는 정류장은 합계에서 빠집니다.')
        st.markdown('[버스 일평균 이용량](https://www.data.go.kr/data/15162142/fileData.do) · [버스 정류장 위치](https://www.data.go.kr/data/15067528/fileData.do) · [도시철도 월별 통행량](https://www.data.go.kr/data/15137332/fileData.do) · [도시철도 역사 위치](https://data.kric.go.kr/rips/M_01_01/detail.do?id=32)')
        st.caption('이 지표는 정거장 주변을 살펴보는 참고 자료입니다. 업종 선택과 관계없이 일반음식점 인허가 전체를 표시하며, 예측과 추천 점수에는 사용하지 않습니다.')
