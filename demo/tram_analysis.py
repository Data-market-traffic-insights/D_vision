"""검증된 예정 정거장만 사용하는 지표면 거리 및 조건 부합도 계산."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pydeck as pdk

BASE_DIR = Path(__file__).resolve().parent
EARTH_RADIUS_M = 6371008.8
VERIFIED = {'공식 좌표', '지도 대조 후 검증한 좌표'}
RADII = [300, 500, 1000]
MAX_ACCURACY_M = 50.0  # 3단계 열만 있는 이전 자료의 호환 기준. 4단계 근사점에는 적용하지 않는다.


def load_stations(path=None):
    path = Path(path) if path is not None else BASE_DIR / 'data/tram_stations.csv'
    df = pd.read_csv(path, encoding='utf-8-sig', dtype={'station_id': str}, keep_default_na=False)
    required = ['station_id','station_name','nearby_landmark','latitude','longitude',
                'coordinate_source','coordinate_accuracy','source_page','verification_status',
                'coordinate_crs','verified_by','verified_at','coordinate_evidence','accuracy_m']
    if not set(required).issubset(df):
        raise ValueError('정거장 자료의 필수 열이 누락되었습니다.')
    if df['station_id'].duplicated().any() or set(df.station_id) != set(map(str, range(201,246))):
        raise ValueError('정거장 번호는 중복 없이 201~245의 45개여야 합니다.')
    if df['station_name'].str.strip().eq('').any():
        raise ValueError('정거장 명칭이 누락되었습니다.')
    return df.sort_values('station_id').reset_index(drop=True)


def station_status(stations):
    df = stations.copy()
    lat, lon = pd.to_numeric(df.latitude, errors='coerce'), pd.to_numeric(df.longitude, errors='coerce')
    accuracy = pd.to_numeric(df.accuracy_m, errors='coerce')
    date_valid = pd.to_datetime(df.verified_at, errors='coerce', utc=True).notna()
    valid = np.isfinite(lat) & np.isfinite(lon) & lat.between(36.15,36.55) & lon.between(127.2,127.6)
    evidence = df[['coordinate_source','coordinate_evidence','verified_by','verified_at']].astype(str).apply(
        lambda col: ~col.str.strip().isin(['', '미확보', '미검증', 'nan', 'None'])).all(axis=1)
    verified = df.verification_status.isin(VERIFIED)
    crs = df.coordinate_crs.eq('EPSG:4326')
    precise = np.isfinite(accuracy) & accuracy.between(0,MAX_ACCURACY_M)
    if 'coordinate_status' in df:
        # 4단계: 정량 오차를 입증할 수 없는 지도 대조 근사점도 명시적 검토 후 허용한다.
        canonical=df.coordinate_status.isin(['official','map_verified_approx'])
        reviewed=pd.to_datetime(df.get('reviewed_at',pd.Series('',index=df.index)),errors='coerce',utc=True).notna()
        for key in ['verification_method','reviewer_note','map_url']:
            reviewed &= df.get(key,pd.Series('',index=df.index)).astype(str).str.strip().ne('')
        uncertainty=df.get('estimated_uncertainty_m',pd.Series('',index=df.index)).astype(str)
        numeric=pd.to_numeric(uncertainty,errors='coerce')
        precise=uncertainty.eq('') | (np.isfinite(numeric) & numeric.gt(0) & df.get('uncertainty_basis',pd.Series('',index=df.index)).astype(str).str.strip().ne(''))
        verified=canonical & reviewed
    df['analysis_eligible'] = valid & evidence & verified & crs & precise & date_valid
    reasons = []
    for idx, row in df.iterrows():
        missing=[]
        if not valid.loc[idx]: missing.append('유효한 대전 경위도 미확보')
        if not verified.loc[idx]: missing.append('좌표 미검증')
        if not evidence.loc[idx] or not date_valid.loc[idx]: missing.append('검증 근거·담당·일자 미완료')
        if not crs.loc[idx]: missing.append('좌표계 미확인')
        if not precise.loc[idx]: missing.append('위치 오차 기록·근거 확인 필요')
        reasons.append('분석 가능' if not missing else ' / '.join(missing))
    df['analysis_reason'] = reasons
    df['latitude'], df['longitude'] = lat, lon
    return df


def verified_stations(stations):
    status = station_status(stations)
    return status.loc[status.analysis_eligible].copy()


def require_station(station):
    checked = station_status(pd.DataFrame([station])).iloc[0]
    if not checked.analysis_eligible:
        raise ValueError(f"{checked.station_id}번은 반경 분석 대상이 아닙니다: {checked.analysis_reason}")
    return checked


def haversine_m(latitude, longitude, center_latitude, center_longitude):
    lat, lon, clat, clon = np.broadcast_arrays(np.asarray(latitude,dtype=float), np.asarray(longitude,dtype=float),
                                               np.asarray(center_latitude,dtype=float), np.asarray(center_longitude,dtype=float))
    lat, lon, clat, clon = map(np.deg2rad, [lat, lon, clat, clon])
    a = np.sin((lat-clat)/2)**2 + np.cos(lat)*np.cos(clat)*np.sin((lon-clon)/2)**2
    return 2*EARTH_RADIUS_M*np.arcsin(np.sqrt(np.clip(a,0,1)))


def shop_coordinates(shops):
    lat = pd.to_numeric(shops['위도'],errors='coerce').to_numpy()
    lon = pd.to_numeric(shops['경도'],errors='coerce').to_numpy()
    valid=np.isfinite(lat)&np.isfinite(lon)&(lat>=-90)&(lat<=90)&(lon>=-180)&(lon<=180)
    return lat, lon, valid


def radius_shops(shops, station, radius_m):
    if radius_m not in RADII: raise ValueError('반경은 300m, 500m, 1km 중 선택하세요.')
    station = require_station(station)
    lat,lon,valid=shop_coordinates(shops)
    distances=haversine_m(lat,lon,station.latitude,station.longitude)
    mask=valid & (distances<=radius_m+1e-7)
    result=shops.loc[mask].copy()
    result['정거장거리(m)']=distances[mask]
    return result.sort_values('정거장거리(m)'), int((~valid).sum())


def nearest_station_access(shops, stations):
    eligible=verified_stations(stations)
    lat,lon,valid=shop_coordinates(shops)
    nearest=np.full(len(shops),np.inf)
    if eligible.empty:
        nearest[:]=np.nan
        return pd.Series(nearest,index=shops.index,name='최근접검증정거장거리(m)')
    for station in eligible.itertuples():
        nearest=np.minimum(nearest,haversine_m(lat,lon,station.latitude,station.longitude))
    nearest[~valid]=np.nan
    return pd.Series(nearest,index=shops.index,name='최근접검증정거장거리(m)')


def admin_access(shops, stations, radius_m):
    distances=nearest_station_access(shops,stations)
    frame=pd.DataFrame({'행정동코드':shops['행정동코드'], '전체':1, '좌표유효':distances.notna(),
                        '접근상가수':distances.le(radius_m)})
    result=frame.groupby('행정동코드').agg(전체상가수=('전체','sum'),좌표유효상가수=('좌표유효','sum'),접근상가수=('접근상가수','sum')).reset_index()
    if verified_stations(stations).empty:
        result['접근상가수']=np.nan
    result['트램접근상가비율(%)']=result['접근상가수']/result['전체상가수']*100
    return result


def station_summary(shops, stations, industries, radius_m, selected_industry):
    from dashboard_data import industry_profile, entropy
    rows=[]
    for _,station in verified_stations(stations).iterrows():
        subset,excluded=radius_shops(shops,station,radius_m)
        p=industry_profile(subset,industries)
        chosen=p.loc[p['업종'].eq(selected_industry)].iloc[0]
        rows.append({'station_id':station.station_id,'station_name':station.station_name,'반경(m)':radius_m,
                     '전체상가수':len(subset),'선택업종상가수':int(chosen['상가수']),
                     '선택업종비율(%)':float(chosen['비율(%)']) if len(subset) else np.nan,
                     '업종다양성':entropy(p) if len(subset) else np.nan,
                     '선택업종밀집도(개/km²)':int(chosen['상가수'])/(np.pi*(radius_m/1000)**2),
                     '좌표제외상가수':excluded})
    return pd.DataFrame(rows,columns=['station_id','station_name','반경(m)','전체상가수','선택업종상가수','선택업종비율(%)','업종다양성','선택업종밀집도(개/km²)','좌표제외상가수'])


def covered_shop_ids(shops,stations,radius_m):
    if radius_m not in RADII: raise ValueError('지원하지 않는 반경입니다.')
    if verified_stations(stations).empty: return None
    nearest=nearest_station_access(shops,stations)
    return set(shops.loc[nearest.le(radius_m),'상가업소번호'])


def preference_scores(table, same_industry='무관', diversity='무관', access=False):
    result=table.copy();components=[]
    for preference,column in [(same_industry,'선택업종비율(%)'),(diversity,'업종다양성')]:
        if preference=='무관': continue
        values=result[column].astype(float)
        span=values.max()-values.min()
        scaled=(values-values.min())/span if span>0 else pd.Series(.5,index=result.index)
        components.append(1-scaled if preference=='낮은 비율' or preference=='낮은 다양성' else scaled)
    if access:
        if '트램접근상가비율(%)' not in result or result['트램접근상가비율(%)'].isna().all():
            raise ValueError('검증된 정거장이 없어 접근성 조건을 점수에 넣을 수 없습니다.')
        components.append(result['트램접근상가비율(%)']/100)
    result['사용자 조건 부합도']=pd.concat(components,axis=1).mean(axis=1,skipna=False)*100 if components else np.nan
    return result


def scenario_exposure(shops,station,radius_m,change_pct,industry,industries):
    if not -20<=change_pct<=30: raise ValueError('시연 가정은 -20~+30% 범위입니다.')
    from dashboard_data import industry_profile
    subset,excluded=radius_shops(shops,station,radius_m)
    profile=industry_profile(subset,industries)
    count=int(profile.loc[profile['업종'].eq(industry),'상가수'].iloc[0])
    return {'assumed_change_pct':float(change_pct),'exposed_shops':len(subset),'selected_industry_shops':count,
            'profile':profile,'shops':subset,'excluded_coordinates':excluded}


def circle_polygon(lat,lon,radius_m,steps=96):
    angular=radius_m/EARTH_RADIUS_M; lat0=np.deg2rad(lat);lon0=np.deg2rad(lon)
    bearing=np.linspace(0,2*np.pi,steps+1)
    latitude=np.arcsin(np.sin(lat0)*np.cos(angular)+np.cos(lat0)*np.sin(angular)*np.cos(bearing))
    longitude=lon0+np.arctan2(np.sin(bearing)*np.sin(angular)*np.cos(lat0),np.cos(angular)-np.sin(lat0)*np.sin(latitude))
    return np.column_stack([np.rad2deg(longitude),np.rad2deg(latitude)]).tolist()


def station_map(stations,selected,shops,radius_m,limit=3000):
    selected=require_station(selected)
    from dashboard_data import map_points
    points,_,_=map_points(shops,limit)
    plotted=points[['상호명','경도','위도']].rename(columns={'상호명':'label','경도':'lon','위도':'lat'})
    eligible=verified_stations(stations).copy()
    markers=pd.DataFrame({'lon':eligible.longitude,'lat':eligible.latitude,
                          'label':eligible.station_id+' '+eligible.station_name+' · 예정 위치'})
    polygon=[{'polygon':circle_polygon(selected.latitude,selected.longitude,radius_m),'label':f'분석 반경 {radius_m}m · 지표면 직선거리'}]
    layers=[pdk.Layer('PolygonLayer',polygon,id='radius',get_polygon='polygon',get_fill_color=[18,124,128,25],get_line_color=[18,124,128,200],line_width_min_pixels=2,stroked=True,pickable=True),
            pdk.Layer('ScatterplotLayer',plotted,id='shops',get_position='[lon,lat]',get_fill_color=[18,124,128,150],get_radius=15,radius_min_pixels=3,pickable=True),
            pdk.Layer('ScatterplotLayer',markers,id='stations',get_position='[lon,lat]',get_fill_color=[217,140,64,255],get_radius=35,radius_min_pixels=7,pickable=True),
            pdk.Layer('TextLayer',markers,id='station_labels',get_position='[lon,lat]',get_text='label',get_size=13,get_color=[20,47,64],get_pixel_offset=[0,-20])]
    return pdk.Deck(layers=layers,map_provider='carto',map_style='light',initial_view_state=pdk.ViewState(latitude=selected.latitude,longitude=selected.longitude,zoom=14 if radius_m<1000 else 13),tooltip={'text':'{label}'})
