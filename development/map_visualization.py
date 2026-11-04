"""기존 행정동 K=3 결과를 재학습 없이 표시하는 지도 계층."""
import numpy as np
import pandas as pd
import pydeck as pdk
from dashboard_data import COLORS,TYPES,map_points

INDUSTRY_COLORS = {
    '과학·기술':'#4E79A7','교육':'#F28E2B','보건의료':'#E15759','부동산':'#76B7B2',
    '소매':'#59A14F','수리·개인':'#B6992D','숙박':'#B07AA1','시설관리·임대':'#FF9DA7',
    '예술·스포츠':'#9C755F','음식':'#6B6570'}
MODES=['상가 밀집도','업종별 분포','AI 상권 유형(K-means)']


def rgb(color): return [int(color[i:i+2],16) for i in [1,3,5]]


def admin_representatives(shops,admin,industries):
    """동별 상가 좌표 중앙값에 가장 가까운 실제 상가 점. 경계·공식 중심점 아님."""
    if admin['행정동코드'].duplicated().any(): raise ValueError('행정동 코드가 중복되었습니다.')
    if set(shops['행정동코드'])!=set(admin['행정동코드']): raise ValueError('상가·군집 행정동 코드가 일치하지 않습니다.')
    names=shops[['행정동코드','시군구명','행정동명']].drop_duplicates()
    if len(names)!=len(admin): raise ValueError('동일 코드의 자치구·행정동명이 불일치합니다.')
    check=admin.merge(names,on='행정동코드',validate='one_to_one',suffixes=('','_상가'))
    if not (check['시군구명'].eq(check['시군구명_상가']) & check['행정동명'].eq(check['행정동명_상가'])).all():
        raise ValueError('상가·군집 행정동 명칭이 불일치합니다.')
    if not admin['군집'].isin(TYPES).all(): raise ValueError('기존 K=3 결과의 군집 번호를 확인하세요.')
    valid,_,_=map_points(shops,len(shops))
    rows=[]
    for code,group in valid.groupby('행정동코드',sort=True):
        lat,lon=group[['위도','경도']].median()
        distance=(group['위도']-lat)**2+((group['경도']-lon)*np.cos(np.deg2rad(lat)))**2
        point=group.loc[distance.idxmin()]
        rows.append({'행정동코드':code,'lat':float(point['위도']),'lon':float(point['경도']),
                     '대표좌표_상가업소번호':point['상가업소번호']})
    positions=pd.DataFrame(rows,columns=['행정동코드','lat','lon','대표좌표_상가업소번호'])
    result=admin.merge(positions,on='행정동코드',how='left',validate='one_to_one')
    count=shops.groupby(['행정동코드','상권업종대분류명']).size().unstack(fill_value=0).reindex(columns=industries,fill_value=0)
    result['주요업종']=result['행정동코드'].map(count.idxmax(axis=1))
    result['label']=result['지역표시']+' · 행정동 대표점'
    result['name']=result['지역표시'];result['industry']=result['주요업종']
    result['detail']=result.apply(lambda r:f"군집 {int(r['군집'])} · {TYPES[int(r['군집'])]}\n전체 상가 {int(r['전체상가수']):,}개 · 주요 업종 {r['주요업종']}",axis=1)
    result['color']=result['군집'].map(lambda k:rgb(COLORS[int(k)]))
    return result


def build_map(points,mode,stations=None):
    if mode not in MODES: raise ValueError('지원하지 않는 지도 유형입니다.')
    if mode==MODES[2]:
        plotted=points.dropna(subset=['lat','lon']).copy()
        layers=[pdk.Layer('ScatterplotLayer',plotted,id='admin_clusters',get_position='[lon,lat]',
                          get_fill_color='color',get_radius=1,radius_units='pixels',radius_min_pixels=10,
                          radius_max_pixels=10,get_line_color=[255,255,255],stroked=True,line_width_min_pixels=2,
                          pickable=True,auto_highlight=True)]
    else:
        plotted=points[['상호명','행정동명','상권업종대분류명','경도','위도']].rename(columns={'상호명':'name','행정동명':'dong','상권업종대분류명':'industry','경도':'lon','위도':'lat'}).copy()
        plotted['detail']=plotted['dong']+' · '+plotted['industry']
        if not set(plotted.industry).issubset(INDUSTRY_COLORS): raise ValueError('실제 업종에 대응하는 색상이 없습니다.')
        plotted['color']=plotted.industry.map(lambda i:rgb(INDUSTRY_COLORS[i]))
        layers=[pdk.Layer('ScatterplotLayer',plotted,id='shops',get_position='[lon,lat]',
                          get_fill_color='color' if mode==MODES[1] else [18,124,128,160],
                          get_radius=24,radius_min_pixels=3,radius_max_pixels=10,pickable=True,auto_highlight=True)]
    if stations is not None and len(stations):
        from tram_analysis import verified_stations
        s=verified_stations(stations)
        markers=pd.DataFrame({'lat':s.latitude,'lon':s.longitude,'name':s.station_id+' · '+s.station_name,
                              'detail':'트램 예정 위치 · 지도 대조 근사 좌표 · 공식 측량 좌표 아님','marker':'◆'})
        layers.append(pdk.Layer('ScatterplotLayer',markers,id='tram_halo',get_position='[lon,lat]',
                                get_fill_color=[255,255,255],get_line_color=[20,47,64],stroked=True,line_width_min_pixels=2,
                                get_radius=1,radius_units='pixels',radius_min_pixels=12,radius_max_pixels=12,pickable=True))
        layers.append(pdk.Layer('ScatterplotLayer',markers,id='tram_markers',get_position='[lon,lat]',
                                get_fill_color=[20,47,64],get_radius=1,radius_units='pixels',
                                radius_min_pixels=4,radius_max_pixels=4,pickable=True))
    view_points=plotted[['lat','lon']]
    if stations is not None and len(stations):
        view_points=pd.concat([view_points,markers[['lat','lon']]],ignore_index=True)
    if len(view_points):
        x=(view_points.lon.to_numpy()+180)/360
        y=(1-np.arcsinh(np.tan(np.deg2rad(view_points.lat.to_numpy())))/np.pi)/2
        cx=(x.min()+x.max())/2;cy=(y.min()+y.max())/2
        zoom=float(np.clip(min(np.log2(900/(256*max(np.ptp(x),1e-9))),np.log2(420/(256*max(np.ptp(y),1e-9)))),9,15))
        center_lat=float(np.rad2deg(np.arctan(np.sinh(np.pi*(1-2*cy)))))
        view=pdk.ViewState(latitude=center_lat,longitude=float(cx*360-180),zoom=zoom)
    else:
        view=pdk.ViewState(latitude=36.35,longitude=127.38,zoom=10.5)
    return pdk.Deck(layers=layers,map_provider='carto',map_style='light',
                    initial_view_state=view,
                    tooltip={'text':'{name}\n{detail}','style':{'backgroundColor':'#142C3D','color':'white'}})
