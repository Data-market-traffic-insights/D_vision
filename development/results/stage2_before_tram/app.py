"""실제 대전 상가 CSV와 검증된 K-means 결과를 탐색하는 Streamlit 앱."""
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard_data import (TYPES, COLORS, data_signature, load_dashboard_data,
                            industry_profile, entropy, select_shops, exploration_table,
                            map_points, make_map)

st.set_page_config(page_title='D·VISION | 대전 상권 탐색', page_icon='📊', layout='wide')
PAGES = ['전체 상권 현황', '지역별 상세 분석', 'AI 상권 유형 분석', '지역 비교', '업종별 입지 탐색', '상가 분포 지도']
PERIOD = '2026년 9월'
PALETTE = ['#127C80', '#526BB3', '#D98C40', '#78A6A0', '#74869D', '#C78B83', '#A6AC68', '#967FB2', '#68A4BF', '#BFA487']


@st.cache_data(show_spinner='실제 상가 데이터와 분석 결과를 확인하고 있습니다…')
def cached_data(signature):
    return load_dashboard_data()


def chart(fig, key=None, height=360):
    fig.update_layout(template='plotly_white', height=height, margin=dict(t=28, b=25, l=8, r=12),
                      font=dict(family='Arial, Apple SD Gothic Neo, sans-serif', color='#243D4B'),
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      legend_title_text='', hoverlabel=dict(bgcolor='white'),
                      colorway=PALETTE)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor='#E8EEF1')
    st.plotly_chart(fig, key=key, config={'displaylogo': False})


def bar(frame, x, y, color=None, horizontal=False, height=360):
    fig = px.bar(frame, x=x, y=y, color=color, orientation='h' if horizontal else 'v',
                 color_discrete_sequence=PALETTE, text_auto=',.0f' if '비율' not in y else '.1f')
    if horizontal:
        fig.update_yaxes(categoryorder='total ascending')
    chart(fig, height=height)


def download(frame, name, label='표 CSV 다운로드'):
    st.download_button(label, frame.to_csv(index=False).encode('utf-8-sig'), name,
                       mime='text/csv', key=f'download_{name}')


def section(title, note=None):
    st.subheader(title)
    if note:
        st.caption(note)


def profile_chart(profiles, order):
    combined = pd.concat([p.assign(지역=name) for name, p in profiles.items()], ignore_index=True)
    hover = {'비율(%)': ':.2f', '비율': False}
    hover['상가수'] = ':,' if combined['상가수'].notna().any() else False
    fig = px.bar(combined, x='업종', y='비율(%)', color='지역', barmode='group',
                 category_orders={'업종': order}, color_discrete_sequence=PALETTE,
                 hover_data=hover)
    fig.update_yaxes(title='전체 상가 중 비율 (%)', ticksuffix='%')
    chart(fig)


def metrics(items):
    for column, (label, value, help_text) in zip(st.columns(len(items)), items):
        with column.container(border=True):
            st.metric(label, value, help=help_text)


def overview(data):
    shops, admin, industries = data['shops'], data['admin'], data['industries']
    st.markdown('<div class="hero"><div class="eyebrow">DAEJEON · COMMERCIAL INTELLIGENCE</div><h1>데이터로 읽는 대전의 상권</h1><p>지역의 규모와 업종 구성을 비교하고, 관심 있는 상권을 직접 탐색하세요.</p></div>', unsafe_allow_html=True)
    metrics([('전체 상가', f'{len(shops):,}개', '등록된 상가업소 수'),
             ('분석 행정동', f'{len(admin)}개', '행정동코드 기준'),
             ('업종 대분류', f'{len(industries)}개', '상권업종대분류명 기준'),
             ('분석 기준', PERIOD, '소상공인시장진흥공단 상가(상권)정보')])
    left, right = st.columns([1, 1.2])
    with left.container(border=True):
        section('자치구별 상가 규모', '단위: 개 · 대전 전체 데이터')
        counts = shops.groupby('시군구명').size().rename('상가 수(개)').reset_index().sort_values('상가 수(개)', ascending=False)
        bar(counts, '시군구명', '상가 수(개)', '시군구명')
    with right.container(border=True):
        section('어떤 업종이 모여 있을까요?', '대분류별 등록 상가 수 · 단위: 개')
        p = industry_profile(shops, industries).sort_values('상가수')
        bar(p, '상가수', '업종', horizontal=True)
    left, right = st.columns([1.2, 1])
    with left.container(border=True):
        section('상가 수 상위 10개 행정동', '동 이름 앞에 자치구를 함께 표시합니다.')
        bar(admin.nlargest(10, '전체상가수'), '전체상가수', '지역표시', horizontal=True, height=400)
    with right.container(border=True):
        section('대전 전체 업종 구성', '전체 79,691개 상가를 분모로 계산한 비율')
        fig = px.pie(p, names='업종', values='상가수', hole=.65, color_discrete_sequence=PALETTE)
        fig.update_traces(textinfo='percent', hovertemplate='%{label}<br>%{value:,}개 · %{percent}<extra></extra>')
        chart(fig, height=400)
    with st.expander('집계 원자료 확인 및 다운로드'):
        st.dataframe(counts, hide_index=True, width='stretch')
        download(admin[['시군구명', '행정동코드', '행정동명', '전체상가수', '군집', '잠정유형']], '행정동별_상권현황.csv')


def detail(data, gu, dong):
    section('지역별 상세 분석', '왼쪽에서 자치구와 행정동을 선택하세요. 행정동코드를 기준으로 조회합니다.')
    if gu == '전체' or dong == '전체':
        st.info('자치구와 행정동을 모두 선택하면 해당 행정동의 상세 분석이 표시됩니다.')
        st.dataframe(data['admin'][['지역표시', '전체상가수', '잠정유형']], hide_index=True, width='stretch')
        return
    subset = select_shops(data['shops'], gu=gu, dong=dong)
    row = data['admin'].loc[data['admin']['행정동코드'].eq(dong)].iloc[0]
    p = industry_profile(subset, data['industries'])
    st.markdown(f"### {gu} · {row['행정동명']}")
    st.caption(f'행정동코드 {dong} · 모든 업종 집계')
    metrics([('전체 상가', f'{len(subset):,}개', None), ('주요 업종', p.loc[p['상가수'].idxmax(), '업종'], '등록 상가 수가 가장 많은 대분류'),
             ('업종 다양성', f'{entropy(p):.3f}', 'Shannon entropy, 자연로그 기준. 높을수록 구성이 고르게 분포하며 입지 우열을 의미하지 않습니다.'),
             ('탐색 군집', str(int(row['군집'])), '군집 번호에는 순위나 우열이 없습니다.')])
    st.info(f"잠정 유형: {row['잠정유형']} · 실루엣 {row['실루엣']:.3f}. 확정된 상권 유형이 아닙니다.")
    section('대전 전체 구성과 비교', '대전 전체 비율은 전체 상가 수를 분모로 한 가중 비율입니다. 행정동 평균과 다릅니다.')
    profile_chart({row['지역표시']: p, '대전 전체': industry_profile(data['shops'], data['industries'])}, data['industries'])
    left, right = st.columns(2)
    with left:
        section('업종별 상가 수', '단위: 개')
        bar(p, '업종', '상가수')
    with right:
        section('업종별 수치')
        table = p[['업종', '상가수', '비율(%)']]
        st.dataframe(table, hide_index=True, width='stretch', column_config={'비율(%)': st.column_config.NumberColumn(format='%.2f%%')})
        download(table, f'{dong}_업종구성.csv')


def clustering(data):
    meta, admin, summary, scores = data['metadata'], data['admin'], data['summary'], data['scores']
    section('AI 상권 유형 분석', '지리적 근접성이 아닌 업종 구성과 상권 규모의 유사성을 비교합니다.')
    score = scores.loc[scores.K.eq(3), 'silhouette_score'].iloc[0]
    metrics([('탐색 후보 K', '3', '절대적으로 최적인 K라는 뜻은 아닙니다.'),
             ('실루엣 점수', f'{score:.3f}', '-1~1 범위. 0 근처일수록 군집 경계가 겹칩니다.'),
             ('업종 구성 : 규모', '80 : 20', '표준화 후 블록 총분산에 부여한 가중치'),
             ('PCA 설명 분산', f"{sum(meta['pca_explained_variance_ratio']):.1%}", '두 축에 담긴 분산의 합')])
    st.warning('탐색적 분류입니다. 군집 경계가 뚜렷하지 않고 특징 가중치를 바꾸면 결과가 달라집니다. 군집 번호는 순위가 아닙니다.')
    with st.expander('분석 방법과 K 선택 근거'):
        st.write('업종 비율 10개를 각각 표준화하고 전체 상가 수를 log1p 변환·표준화했습니다. 업종 구성과 규모의 총분산을 80:20으로 맞췄으며, 비율에서 파생되는 다양성은 중복 입력하지 않았습니다.')
        st.write('K=2~8을 비교했습니다. K=2의 실루엣이 가장 높지만, K=3은 22·25·35개 동으로 나뉘고 초기값 변경 시 평균 ARI 약 0.992로 안정적이었습니다. 가중치 변경에 대한 안정성과는 다릅니다.')
        st.write('규모 가중치를 20%에서 10%로 바꾼 비교에서 ARI는 약 0.20입니다. 유형 설명은 이번 특징 설계에 의존하는 잠정 해석입니다.')
        st.caption(f"분석 결과 폴더: {data['run_dir'].name} · 난수 {meta['random_state']} · n_init={meta['n_init']}")
    for column, (_, row) in zip(st.columns(3), summary.sort_values('군집').iterrows()):
        with column.container(border=True):
            k = int(row['군집'])
            st.markdown(f'**군집 {k} · {int(row["행정동수"])}개 동**')
            st.write(TYPES[k])
            st.metric('행정동당 평균 상가', f'{row["전체상가수"]:,.1f}개')
    left, right = st.columns([1.3, 1])
    with left.container(border=True):
        section('PCA로 살펴본 상권의 유사성', '전체 특징의 일부만 투영한 그림이며, 2차원에서의 거리만으로 판단할 수 없습니다.')
        fig = px.scatter(admin.assign(군집표시=admin['군집'].map(lambda k: f'군집 {k}')), x='PCA1', y='PCA2', color='군집표시',
                         color_discrete_map={f'군집 {k}': COLORS[k] for k in TYPES},
                         hover_name='지역표시', hover_data={'전체상가수': ':,', '잠정유형': True, 'PCA1': ':.2f', 'PCA2': ':.2f'})
        fig.update_traces(marker_size=10, marker_opacity=.8)
        fig.update_xaxes(title=f"PC1 ({meta['pca_explained_variance_ratio'][0]:.1%})")
        fig.update_yaxes(title=f"PC2 ({meta['pca_explained_variance_ratio'][1]:.1%})")
        chart(fig, height=400)
    with right.container(border=True):
        section('K별 실루엣 점수', 'K=3은 해석성과 초기값 안정성을 고려한 선택입니다.')
        fig = px.line(scores, x='K', y='silhouette_score', markers=True)
        fig.add_vline(x=3, line_dash='dash', line_color='#D98C40')
        fig.update_yaxes(title='실루엣 점수')
        chart(fig, height=400)
    section('군집별 평균 업종 구성', '행정동별 비율의 단순 평균입니다. 군집 전체 상가를 합산한 비율과 다릅니다.')
    profiles = {f'군집 {int(row["군집"])}': pd.DataFrame({'업종': data['industries'],
                 '비율(%)': [row[f'{i}_비율']*100 for i in data['industries']], '상가수': np.nan, '비율': np.nan})
                for _, row in summary.sort_values('군집').iterrows()}
    profile_chart(profiles, data['industries'])
    chosen = st.selectbox('행정동 목록을 확인할 군집', list(TYPES), format_func=lambda k: f'군집 {k} · {TYPES[k]}', key='cluster_choice')
    table = admin.loc[admin['군집'].eq(chosen), ['시군구명', '행정동코드', '행정동명', '전체상가수', '실루엣']].sort_values('전체상가수', ascending=False)
    st.dataframe(table, hide_index=True, width='stretch')
    download(table, f'군집{chosen}_행정동목록.csv')


def comparison(data):
    section('두 지역의 상권 비교', '행정동과 법정동의 범위를 구분하여 실제 코드에 포함된 상가만 집계합니다.')
    basis = st.radio('비교 지역 기준', ['법정동', '행정동'], horizontal=True, key='compare_basis')
    regions = data['legal'] if basis == '법정동' else data['admin']
    code_col, name_col = ('법정동코드', '법정동명') if basis == '법정동' else ('행정동코드', '행정동명')
    favorites = ['궁동', '봉명동', '둔산동', '은행동', '관저동']
    options = regions.sort_values(name_col, key=lambda s: s.map({name: n for n, name in enumerate(favorites)}).fillna(99))[code_col].tolist()
    labels = regions.set_index(code_col)['지역표시'].to_dict()
    left, right = st.columns(2)
    first = left.selectbox('지역 A', options, format_func=labels.get, key=f'compare_a_{basis}')
    available = [c for c in options if c != first]
    second = right.selectbox('지역 B', available, format_func=labels.get, key=f'compare_b_{basis}')
    profiles, rows = {}, []
    for column, code in [(left, first), (right, second)]:
        sub = data['shops'].loc[data['shops'][code_col].eq(code)]
        p = industry_profile(sub, data['industries'])
        profiles[labels[code]] = p
        top = p.loc[p['상가수'].idxmax()]
        with column.container(border=True):
            st.markdown(f'**{labels[code]}**')
            st.caption(f'{basis}코드 {code}')
            st.metric('전체 상가', f'{len(sub):,}개')
            st.write(f"주요 업종: {top['업종']} ({top['비율']:.1%}) · 다양성 {entropy(p):.3f}")
            if basis == '행정동':
                st.caption(f"탐색 군집: {data['admin'].set_index('행정동코드').loc[code, '잠정유형']}")
        rows.append({'지역': labels[code], '지역기준': basis, '코드': code, '전체상가수': len(sub), '주요업종': top['업종'], '업종다양성': entropy(p)})
    if basis == '법정동':
        st.info('법정동 단위 집계입니다. 행정동 단위 K-means 군집을 하나로 지정하지 않습니다.')
        with st.expander('실제 상가 데이터의 행정동·법정동 대응 확인'):
            crosswalk = data['shops'].loc[data['shops'][code_col].isin([first, second])].groupby(['시군구명', '법정동코드', '법정동명', '행정동코드', '행정동명']).size().rename('상가수').reset_index()
            st.dataframe(crosswalk, hide_index=True, width='stretch')
            st.caption('등록된 상가에서 관측한 대응입니다. 행정구역 경계 전체의 공식 매핑을 뜻하지 않습니다.')
    profile_chart(profiles, data['industries'])
    p1, p2 = profiles[labels[first]], profiles[labels[second]]
    diff = p1['비율(%)'].to_numpy()-p2['비율(%)'].to_numpy()
    largest = int(np.abs(diff).argmax())
    st.write(f"업종 구성 차이가 가장 큰 항목은 {data['industries'][largest]}입니다. A−B 차이는 {diff[largest]:+.2f}%p입니다. 상가 수와 구성 비율만 비교한 결과입니다.")
    table = pd.concat([p.assign(지역=label) for label, p in profiles.items()], ignore_index=True)[['지역', '업종', '상가수', '비율(%)']]
    st.dataframe(table, hide_index=True, width='stretch')
    download(table, f'{basis}_지역비교.csv')


def explore(data):
    section('관심 업종으로 지역 탐색', '상가 수와 업종 비율은 서로 다른 지표입니다. 창업 성공 지역 추천이나 수익성 예측이 아닙니다.')
    left, middle, right = st.columns(3)
    industry = left.selectbox('관심 업종 대분류', data['industries'], index=data['industries'].index('음식'), key='explore_industry')
    mediums = sorted(data['shops'].loc[data['shops']['상권업종대분류명'].eq(industry), '상권업종중분류명'].dropna().unique())
    medium = middle.selectbox('관심 업종 중분류', ['전체'] + mediums, key=f'explore_medium_{industry}')
    gu = right.selectbox('탐색 자치구', ['전체'] + sorted(data['admin']['시군구명'].unique()), key='explore_gu')
    minimum = st.slider('행정동 전체 상가 수 최솟값', 0, int(data['admin']['전체상가수'].max()), 100, step=1, key='explore_minimum', help='작은 표본에서 비율이 극단적으로 보이는 현상을 줄이기 위한 필터입니다.')
    table = exploration_table(data['shops'], data['admin'], industry, medium, minimum, gu)
    if table.empty:
        st.info('조건에 맞는 행정동이 없습니다. 최소 상가 수를 낮춰보세요.')
        return
    selected = industry if medium == '전체' else f'{industry} / {medium}'
    st.caption(f'선택 업종: {selected} · 비율의 분모는 각 행정동의 모든 업종 상가 수입니다. 0개인 지역도 표에 포함합니다.')
    left, right = st.columns(2)
    with left.container(border=True):
        section('선택 업종 상가 수 상위 10곳', '단위: 개 · 등록 점포의 절대 규모')
        bar(table.nlargest(10, '선택업종상가수'), '선택업종상가수', '지역표시', horizontal=True, height=400)
    with right.container(border=True):
        section('선택 업종 비율 상위 10곳', '단위: % · 해당 행정동 전체 상가 대비')
        top = table.nlargest(10, '선택업종비율(%)')
        fig = px.bar(top, x='선택업종비율(%)', y='지역표시', orientation='h', hover_data=['선택업종상가수', '전체상가수'])
        fig.update_yaxes(categoryorder='total ascending')
        fig.update_xaxes(ticksuffix='%')
        chart(fig, height=400)
    cols = ['지역표시', '행정동코드', '선택업종상가수', '선택업종비율(%)', '전체상가수', '군집', '잠정유형']
    st.dataframe(table[cols].sort_values('선택업종상가수', ascending=False), hide_index=True, width='stretch')
    download(table[cols], '관심업종_행정동탐색.csv')
    code = st.selectbox('다른 업종 구성도 살펴볼 행정동', table['행정동코드'].tolist(), format_func=table.set_index('행정동코드')['지역표시'].to_dict().get, key='explore_dong')
    sub = select_shops(data['shops'], dong=code)
    profile_chart({'선택 행정동': industry_profile(sub, data['industries']), '대전 전체': industry_profile(data['shops'], data['industries'])}, data['industries'])
    st.caption('매출·유동인구·임대료·폐업률 자료가 없어 상가 수가 적다는 이유로 창업에 유리하다고 판단할 수 없습니다.')


def map_page(data, gu, dong):
    section('상가 분포 지도', '왼쪽 지역 선택과 아래 업종 선택이 지도·집계표·그래프에 함께 적용됩니다.')
    left, middle, right = st.columns(3)
    industry = left.selectbox('지도 업종 대분류', ['전체'] + data['industries'], key='map_industry')
    medium_options = data['shops'] if industry == '전체' else data['shops'].loc[data['shops']['상권업종대분류명'].eq(industry)]
    medium = middle.selectbox('지도 업종 중분류', ['전체'] + sorted(medium_options['상권업종중분류명'].dropna().unique()), key=f'map_medium_{industry}')
    limit = right.selectbox('지도 표시 상한', [1000, 3000, 5000, 10000], index=1, key='map_limit')
    filtered = select_shops(data['shops'], gu, dong, industry, medium)
    if filtered.empty:
        st.info('선택한 지역과 업종에 해당하는 상가가 없습니다. 필터를 변경해 주세요.')
        return
    points, excluded, located = map_points(filtered, limit)
    metrics([('조건에 맞는 전체 상가', f'{len(filtered):,}개', '필터를 적용한 전체 집계'),
             ('지도 표시 점', f'{len(points):,}개', '표시용 표본 수. 분석 집계는 전체 데이터를 사용합니다.'),
             ('좌표 제외', f'{excluded:,}개', '좌표 결측 또는 유효 범위 밖의 점')])
    if len(points) < located:
        st.info(f'지도에는 좌표가 유효한 {located:,}개 중 {len(points):,}개를 고정 난수 42로 추출하여 표시합니다. 아래 그래프와 표는 조건에 맞는 전체 {len(filtered):,}개 기준입니다.')
    else:
        st.caption('좌표가 유효한 모든 상가를 표시합니다. 아래 집계에는 좌표 제외 상가도 포함합니다.')
    if points.empty:
        st.warning('표시할 수 있는 유효한 좌표가 없습니다.')
    else:
        st.pydeck_chart(make_map(points), height=520)
        st.caption('배경 지도는 CARTO/OpenStreetMap을 사용하며 인터넷 연결이 필요합니다. 점에 마우스를 올리면 상가명과 업종을 확인할 수 있습니다.')
    left, right = st.columns([1, 1.2])
    with left:
        section('현재 조건의 업종별 상가 수', '지도 표본이 아닌 전체 필터 결과 · 단위: 개')
        bar(industry_profile(filtered, data['industries']), '상가수', '업종', horizontal=True)
    with right:
        section('현재 조건의 상가 목록', f'전체 {len(filtered):,}개 중 화면에는 최대 200개 · 다운로드는 전체 필터 결과')
        cols = ['상호명', '시군구명', '행정동명', '상권업종대분류명', '상권업종중분류명', '도로명주소']
        st.dataframe(filtered[cols].head(200), hide_index=True, width='stretch')
        download(filtered[cols], '지도조건_전체상가.csv')


def main():
    st.markdown('''<style>
    .stApp {background:#F5F8FA;color:#203847}
    .block-container {padding-top:2rem;padding-bottom:3rem;max-width:1520px}
    [data-testid="stSidebar"] {background:#EAF1F4;border-right:1px solid #D9E4EA}
    [data-testid="stMetricValue"] {font-size:1.9rem;font-weight:650;color:#146B71}
    [data-testid="stVerticalBlockBorderWrapper"]>div {border-radius:14px}
    .hero {background:#142F40;color:#F6FAFC;padding:30px 34px;border-radius:18px;margin-bottom:24px}
    .hero h1 {font-size:2.2rem;color:#FFF;letter-spacing:-.06em;padding:10px 0}
    .hero p {color:#C9DCE5;margin:0}.eyebrow {letter-spacing:.16em;font-size:.72rem;color:#86D5CE;font-weight:700}
    h1,h2,h3 {letter-spacing:-.035em} [data-testid="stMetric"] {min-height:100px}
    </style>''', unsafe_allow_html=True)
    try:
        data = cached_data(data_signature())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error('분석 데이터를 불러오지 못했습니다. data 폴더와 유효한 군집화 결과를 확인해 주세요.')
        with st.expander('문제 확인 정보'):
            st.code(str(exc))
        st.stop()
    with st.sidebar:
        st.markdown('## D·VISION')
        st.caption('대전 상권 분석 · 입지 탐색')
        page = st.radio('분석 메뉴', PAGES, key='navigation', label_visibility='collapsed')
        st.divider()
        st.markdown('**상세 분석 · 지도 지역 선택**')
        gu = st.selectbox('자치구', ['전체'] + sorted(data['admin']['시군구명'].unique()), key='region_gu')
        regions = data['admin'] if gu == '전체' else data['admin'].loc[data['admin']['시군구명'].eq(gu)]
        names = regions.set_index('행정동코드')['지역표시'].to_dict()
        options = ['전체'] + (regions['행정동코드'].tolist() if gu != '전체' else [])
        dong = st.selectbox('행정동', options, format_func=lambda c: '전체' if c == '전체' else names[c], key=f'region_dong_{gu}', disabled=gu == '전체')
        st.caption('위 지역 선택은 상세 분석과 지도에 적용됩니다. 전체 현황은 대전 전체를 표시합니다.')
        st.divider()
        st.caption(f'기준: {PERIOD}\n\n소상공인시장진흥공단 상가(상권)정보')
        with st.expander('데이터 및 분석 정보'):
            st.write(f"현재 {len(data['shops']):,}개 상가 · {len(data['admin'])}개 행정동")
            st.caption(f"사용 결과: {data['run_dir'].name}")
            st.caption('현재 입력 해시와 지역 코드·상가 수·비율이 일치하는 가장 최근 K=3 결과를 읽었습니다.')
            if data['skipped_runs']:
                st.warning('유효하지 않은 최근 결과를 제외했습니다.')
                st.write(data['skipped_runs'])
    if page == PAGES[0]: overview(data)
    elif page == PAGES[1]: detail(data, gu, dong)
    elif page == PAGES[2]: clustering(data)
    elif page == PAGES[3]: comparison(data)
    elif page == PAGES[4]: explore(data)
    else: map_page(data, gu, dong)
    st.divider()
    st.caption('D·VISION · 머신러닝 기반 대전광역시 상권 유형 분석 및 창업 입지 탐색 시스템 | 등록 상가의 구성과 규모를 탐색하는 참고 정보입니다.')


if __name__ == '__main__':
    main()
