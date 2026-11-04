"""기존 행정동 분석 엔진 위의 조건 부합도·쉬운 해설. 새 모델을 학습하지 않는다."""
import numpy as np
from dashboard_data import exploration_table,industry_profile
from tram_analysis import preference_scores,admin_access,verified_stations

FRIENDLY_TYPES={0:'음식·소매 비중형',1:'생활·사업 서비스 비중형',2:'상가 규모가 큰 복합형'}
TYPE_NOTES={0:'음식·소매 비중이 상대적으로 높고, 평균 상가 규모가 작은 그룹입니다.',
            1:'수리·개인, 시설관리·임대, 과학·기술 업종 비중이 상대적으로 높은 그룹입니다.',
            2:'다른 그룹보다 평균 상가 수가 많은 그룹입니다. 여러 업종이 함께 분포합니다.'}
PRIORITIES=['동일 업종 비율이 낮은 지역','상가가 많이 모인 지역','업종이 다양한 지역','트램 예정 정거장 접근성이 좋은 지역']
EXPERIENCES=['처음 창업해요','창업 경험이 있어요']


def normalize(values):
    span=values.max()-values.min()
    return (values-values.min())/span if span>0 else values*0+.5


def recommendation_table(data,stations,industry,priorities,radius=500,access=None):
    if industry not in data['industries']: raise ValueError('지원하는 실제 업종을 선택하세요.')
    if len(priorities) not in [1,2] or len(set(priorities))!=len(priorities) or not set(priorities)<=set(PRIORITIES):
        raise ValueError('중요 조건을 한두 가지 선택하세요.')
    if radius not in [300,500,1000]: raise ValueError('지원하지 않는 접근성 반경입니다.')
    table=exploration_table(data['shops'],data['admin'],industry)
    if access is None: access=admin_access(data['shops'],stations,radius)
    table=table.merge(access[['행정동코드','접근상가수','트램접근상가비율(%)']],on='행정동코드',validate='one_to_one')
    same=PRIORITIES[0] in priorities;diverse=PRIORITIES[2] in priorities;tram=PRIORITIES[3] in priorities
    if tram and verified_stations(stations).empty: raise ValueError('분석 가능한 정거장이 없어 접근성 조건을 계산할 수 없습니다.')
    # 이전 비율·다양성·접근성 평균을 재사용하고 규모 조건만 같은 가중치로 합친다.
    legacy=preference_scores(table,'낮은 비율' if same else '무관','높은 다양성' if diverse else '무관',tram)
    count=int(same)+int(diverse)+int(tram)
    weighted=legacy['사용자 조건 부합도'].fillna(0)*count
    if PRIORITIES[1] in priorities: weighted=weighted+normalize(table['전체상가수'])*100
    table['사용자 조건 부합도']=weighted/len(priorities)
    components={PRIORITIES[0]:1-normalize(table['선택업종비율(%)']),PRIORITIES[1]:normalize(table['전체상가수']),
                PRIORITIES[2]:normalize(table['업종다양성']),PRIORITIES[3]:table['트램접근상가비율(%)']/100}
    for label in priorities:table['조건점수_'+label]=components[label]*100
    # 기존 창업 탐색과 같이 접근성 선택 시 실제 반경 내 상가가 있는 동만 후보로 둔다.
    # 비율·규모·다양성 점수의 정규화 기준은 필터 전 82개 동으로 유지한다.
    if tram:table=table.loc[table['접근상가수'].gt(0)].copy()
    return table.sort_values(['사용자 조건 부합도','행정동코드'],ascending=[False,True]).reset_index(drop=True)


def reasons(row,industry,priorities,radius):
    texts={PRIORITIES[0]:f"{industry} 상가는 {int(row['선택업종상가수']):,}개, 전체의 {row['선택업종비율(%)']:.1f}%입니다.",
           PRIORITIES[1]:f"전체 상가 {int(row['전체상가수']):,}개로 지역의 등록 상가 규모를 비교했습니다.",
           PRIORITIES[2]:f"업종 다양성은 {row['업종다양성']:.3f}입니다. 구성의 고른 정도를 비교했습니다.",
           PRIORITIES[3]:f"확인된 정거장 {radius:,}m 안에 상가 {int(row['접근상가수']):,}개({row['트램접근상가비율(%)']:.1f}%)가 있습니다." if np.isfinite(row['트램접근상가비율(%)']) else '정거장 접근성 자료가 없습니다.'}
    return [texts[label]+f" 선택 조건 점수 {row['조건점수_'+label]:.1f}/100." for label in priorities]


def experience_note(experience):
    if experience not in EXPERIENCES:raise ValueError('창업 경험을 선택하세요.')
    return ('처음이라면 점포 수와 비율을 함께 살펴보세요. 후보지를 직접 방문하고 임대 조건을 확인하는 출발점으로 활용하세요.'
            if experience==EXPERIENCES[0] else '기존 운영 경험과 비교해 업종 구성·규모 차이를 살펴보세요. 현장 동선과 임대 조건은 별도 확인이 필요합니다.')


def admin_summary(data,stations,code,industry,radius=500,access=None):
    if industry not in data['industries']:raise ValueError('실제 업종을 선택하세요.')
    rows=data['admin'].loc[data['admin']['행정동코드'].eq(code)]
    if len(rows)!=1:raise ValueError('행정동 코드를 확인하세요.')
    row=rows.iloc[0];shops=data['shops'].loc[data['shops']['행정동코드'].eq(code)]
    profile=industry_profile(shops,data['industries'])
    selected=profile.loc[profile['업종'].eq(industry)].iloc[0]
    all_table=exploration_table(data['shops'],data['admin'],industry)
    mean=float(all_table['선택업종비율(%)'].mean())
    comparison='높습니다' if selected['비율(%)']>mean else '낮습니다' if selected['비율(%)']<mean else '같습니다'
    if access is None:access=admin_access(data['shops'],stations,radius)
    local_access=access.loc[access['행정동코드'].eq(code)].iloc[0]
    return {'row':row,'profile':profile,'top3':profile.nlargest(3,'상가수'),'selected':selected,
            'size_rank':int(data['admin']['전체상가수'].gt(len(shops)).sum()+1),
            'mean_share':mean,'share_note':f"{industry} 비율은 {selected['비율(%)']:.1f}%로, 82개 행정동의 단순 평균 {mean:.1f}%보다 {comparison}.",
            'access':local_access,'available_stations':len(verified_stations(stations))}
