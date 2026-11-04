"""승인 정거장의 현재 지표와 정성적 가정. 미래 수치·추천 점수를 만들지 않는다."""
import pandas as pd
from dashboard_data import industry_profile, entropy
from tram_analysis import radius_shops, verified_stations, station_status
from prototype_logic import FRIENDLY_TYPES

SCENARIOS = ['방문 수요 증가 가정', '방문 수요 유지 가정', '방문 수요 감소 가정']


def review_inventory(stations):
    """등급과 분석 허용은 분리한다. A/B라도 기존 승인 검사를 통과해야 한다."""
    table = station_status(stations)
    table['신뢰도'] = table.coordinate_status.map({
        'official':'A', 'map_verified_approx':'B', 'manual_review_required':'C',
        'unavailable':'D'}).fillna('D')
    return table


def radius_profile(data, station, radius):
    shops, excluded = radius_shops(data['shops'], station, radius)
    profile = industry_profile(shops, data['industries'])
    counts = shops.groupby(['행정동코드','시군구명','행정동명']).size().rename('반경내상가수').reset_index()
    admins = counts.merge(data['admin'][['행정동코드','군집']], on='행정동코드', validate='one_to_one')
    admins['AI상권유형'] = admins['군집'].map(FRIENDLY_TYPES)
    admins = admins.sort_values(['반경내상가수','행정동코드'], ascending=[False,True])
    top = profile.loc[profile['상가수'].gt(0)].nlargest(3,'상가수')
    return dict(station_id=str(station.station_id), station_name=station.station_name,
                radius=radius, total=len(shops), excluded=excluded, profile=profile,
                top3=top, diversity=entropy(profile),
                concentration=float(((profile['비율(%)']/100)**2).sum()),
                admins=admins, shop_ids=set(shops['상가업소번호']))


def all_profiles(data, stations):
    return {(str(row.station_id), radius):radius_profile(data,row,radius)
            for _,row in verified_stations(stations).iterrows() for radius in [300,500,1000]}


def scenario_explanation(result, industry, scenario):
    if scenario not in SCENARIOS: raise ValueError('지원하지 않는 시나리오입니다.')
    selected = result['profile'].set_index('업종').loc[industry]
    n, share = int(selected['상가수']), float(selected['비율(%)'])
    top = result['top3']
    top_name = '없음' if top.empty else str(top.iloc[0]['업종'])
    top_share = 0.0 if top.empty else float(top.iloc[0]['비율(%)'])
    total = result['total']; diversity = result['diversity']; hhi = result['concentration']
    base = f"현재 {result['radius']:,}m 안의 {industry} 상가는 {n:,}개({share:.1f}%)입니다."
    if total == 0:
        return dict(focus='집계된 상가 없음', structure=base+' 분석할 현재 상가가 없어 구조 해석을 보류합니다.',
                    check='좌표와 데이터 누락, 실제 영업 상가를 현장에서 먼저 확인하세요.',
                    compare='등록 상가가 있는 다른 정거장과 자료 범위를 먼저 비교하세요.',
                    why='방문 수요 가정을 선택해도 없는 관측값을 미래 수치로 채우지 않습니다.')
    if scenario == SCENARIOS[0]:
        values = dict(focus=f"전체 {total:,}개 · {industry} {share:.1f}% · 최대 업종 {top_name} {top_share:.1f}%",
            structure=base+f' 방문 수요가 늘어난다고 가정하면, 가장 큰 업종인 {top_name} 업종과 관심 업종이 새 방문 동선에서 함께 이용될 수 있는지 살펴볼 출발점입니다.',
            check='정거장 출입 동선·횡단보도·시간대별 방문 목적을 확인하세요. 점포 비중은 새 방문객의 소비 비중을 뜻하지 않습니다.',
            compare=f'다른 정거장의 {industry} 비율과 전체 상가 규모를 함께 비교하고, 신규 방문 동선이 실제 점포로 이어지는지 확인하세요.',
            why='증가 가정에서는 새 방문과 연결될 업종 구성과 점포 규모에 주목합니다. 유입 규모나 매출 증가율은 계산하지 않습니다.')
    elif scenario == SCENARIOS[1]:
        values = dict(focus=f"{industry} {n:,}개 · 비율 {share:.1f}% · 업종 다양성 {diversity:.3f}",
            structure=base+f' 방문 수요가 비슷하게 유지된다면, 현재 {n:,}개 점포와의 차별화와 업종 조합(다양성 {diversity:.3f})을 검토할 필요가 있습니다.',
            check='현재 단골·반복 방문 시간대·가격대·임대 조건을 확인하세요. 같은 업종 안의 세부 서비스와 규모는 이 집계로 알 수 없습니다.',
            compare=f'다른 정거장의 {industry} 상가 수·비율·다양성을 같은 반경에서 비교해 현재 경쟁 환경의 차이를 확인하세요.',
            why='유지 가정에서는 새로운 수요를 전제하지 않고 기존 경쟁과 반복 방문 조건에 주목합니다.')
    else:
        values = dict(focus=f"최대 업종 {top_name} {top_share:.1f}% · 업종 집중도 {hhi:.3f} · {industry} {n:,}개",
            structure=base+f' 방문 수요 감소를 가정하면 최대 업종 {top_name}의 비율({top_share:.1f}%)과 집중도({hhi:.3f})를 통해 특정 업종에 치우친 현재 구성을 살펴볼 수 있습니다. 이 값은 피해율이 아닙니다.',
            check='공사 중 출입 가능 여부·우회 동선·배달 및 생활권 수요·고정비 감당 조건을 확인하세요. 실제 공사 영향은 별도 조사해야 합니다.',
            compare='다른 정거장의 최대 업종 비율과 집중도를 비교하고, 각 지역의 우회 접근성과 기존 고객 방문 경로를 현장에서 확인하세요.',
            why='감소 가정에서는 동선 단절과 업종 편중을 검토합니다. 폐업 수나 매출 감소량을 추정하지 않습니다.')
    return values


def station_comparison(first, second, industry):
    if first['radius'] != second['radius']: raise ValueError('같은 반경으로 비교해 주세요.')
    rows=[]
    for r in [first,second]:
        p=r['profile'].set_index('업종').loc[industry]
        rows.append({'정거장':r['station_id']+' · '+r['station_name'], '반경(m)':r['radius'],
                     '전체상가수':r['total'],'선택업종상가수':int(p['상가수']),
                     '선택업종비율(%)':float(p['비율(%)']),'업종다양성':r['diversity'],
                     '업종집중도':r['concentration'],
                     '주요업종':' / '.join(r['top3']['업종']),
                     '주변행정동':' / '.join(r['admins']['시군구명']+' '+r['admins']['행정동명'])})
    text=(f"같은 {first['radius']:,}m에서 {first['station_name']}은 {first['total']:,}개, "
          f"{second['station_name']}은 {second['total']:,}개의 상가가 집계됩니다. "
          '규모 차이는 고객 수나 창업 유리함의 차이를 뜻하지 않습니다. 관심 업종 비율과 주변 행정동 구성을 함께 비교하세요.')
    return pd.DataFrame(rows), text


def overlap_summary(profiles, radius):
    memberships={}
    for (sid,r),result in profiles.items():
        if r == radius:
            for shop_id in result['shop_ids']: memberships.setdefault(shop_id,[]).append(sid)
    assigned=sum(len(v) for v in memberships.values())
    return dict(radius=radius, station_sum=assigned, union=len(memberships),
                overlapping_shops=sum(len(v)>1 for v in memberships.values()),
                duplicate_assignments=assigned-len(memberships)), memberships
