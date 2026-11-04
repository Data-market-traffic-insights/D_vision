"""기존 1호선 전체와 승인된 트램만 비교하는 읽기 전용 공간 분석.

원본 추천과 군집은 변경하지 않는다. 정거장 원의 합집합에 포함된 상가를
업소번호로 한 번만 집계하며, 경계에 놓인 상가는 기존 거리 함수 기준 포함한다.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from tram_analysis import haversine_m, shop_coordinates, verified_stations

BASE_DIR = Path(__file__).resolve().parent
TITLE = '검토된 트램 정거장 5개 기준 신규 접근권 편입 후보'
NAMES = ['판암','신흥','대동','대전','중앙로','중구청','서대전네거리','오룡','용문','탄방','시청','정부청사','갈마','월평','갑천','유성온천','구암','현충원','월드컵경기장','노은','지족','반석']
CATEGORIES = ['기존 1호선만','두 접근권 중첩','신규 편입 후보','확인된 두 접근권 밖','좌표 제외']
ACCESS_COLORS = {'기존 1호선만':[38,105,190], '두 접근권 중첩':[137,80,170], '신규 편입 후보':[16,130,91], '확인된 두 접근권 밖':[152,162,174]}


def load_metro_stations(base=BASE_DIR):
    """공식 전체 역 자료가 불완전하면 신규 접근권 분석만 중단한다."""
    base=Path(base);path=base/'data/metro_line1_stations.csv'
    meta=json.loads((base/'data/metro_line1_sources.json').read_text(encoding='utf-8'))
    if meta.get('csv_sha256') != hashlib.sha256(path.read_bytes()).hexdigest():
        raise ValueError('1호선 자료가 출처 기록의 검증본과 다릅니다.')
    if meta.get('coordinate_crs')!='EPSG:4326' or meta.get('expected_count')!=22:
        raise ValueError('1호선 좌표계 또는 전체 역 수를 확인할 수 없습니다.')
    frame=pd.read_csv(path,dtype={'station_id':str},keep_default_na=False)
    required={'station_id','station_name','latitude','longitude','line_id','operator','coordinate_crs','source_date'}
    if not required.issubset(frame):raise ValueError('1호선 필수 열이 누락되었습니다.')
    frame=frame.sort_values('station_id').reset_index(drop=True)
    if frame.station_id.tolist()!=list(map(str,range(101,123))) or frame.station_name.tolist()!=NAMES:
        raise ValueError('1호선 22개 역의 번호·명칭·중복·누락을 확인해 주세요.')
    lat=pd.to_numeric(frame.latitude,errors='coerce');lon=pd.to_numeric(frame.longitude,errors='coerce')
    if not (np.isfinite(lat)&np.isfinite(lon)&lat.between(36.15,36.55)&lon.between(127.2,127.6)).all():
        raise ValueError('1호선 경위도가 유효하지 않습니다.')
    for key,value in [('line_id','S3001'),('operator','대전교통공사'),('coordinate_crs','EPSG:4326'),('source_date',meta['record_date'])]:
        if not frame[key].eq(value).all():raise ValueError('1호선 노선·운영기관·좌표 기준을 확인해 주세요.')
    frame['latitude']=lat;frame['longitude']=lon
    return frame,meta


def distance_index(shops,metro,stations):
    """반경과 무관한 거리를 한 번만 계산한다. UI는 이 결과를 캐싱한다."""
    if shops['상가업소번호'].isna().any() or shops['상가업소번호'].duplicated().any():
        raise ValueError('상가 업소번호가 누락되거나 중복되어 집계할 수 없습니다.')
    tram=verified_stations(stations)
    if tram.empty:raise ValueError('분석이 승인된 트램 정거장이 없습니다.')
    lat,lon,valid=shop_coordinates(shops)
    existing=np.full(len(shops),np.inf)
    for row in metro.itertuples(index=False):existing=np.minimum(existing,haversine_m(lat,lon,row.latitude,row.longitude))
    if metro.empty:raise ValueError('전체 1호선 자료가 필요합니다.')
    tram_dist=np.column_stack([haversine_m(lat,lon,row.latitude,row.longitude) for row in tram.itertuples(index=False)])
    return {'existing':existing,'tram':tram_dist,'valid':valid,'station_ids':tram.station_id.tolist(),'station_names':tram.station_name.tolist()}


def classify_access(index,radius):
    if radius not in (300,500):raise ValueError('신규 접근권 비교는 동일한 300m 또는 500m 반경만 지원합니다.')
    valid=index['valid'];old=valid & (index['existing']<=radius+1e-7)
    membership=(index['tram']<=radius+1e-7)&valid[:,None];planned=membership.any(axis=1)
    category=np.full(len(valid),CATEGORIES[3],dtype=object)
    category[old & ~planned]=CATEGORIES[0];category[old & planned]=CATEGORIES[1]
    category[~old & planned]=CATEGORIES[2];category[~valid]=CATEGORIES[4]
    return category,membership


def access_summary(shops,index,radius,industries):
    from dashboard_data import industry_profile
    category,membership=classify_access(index,radius)
    tagged=shops.copy();tagged['접근권구분']=category
    new=tagged.loc[tagged['접근권구분'].eq(CATEGORIES[2])].copy()
    mask=category==CATEGORIES[2]
    related=[]
    for row in membership[mask]:related.append(' / '.join(f'{sid} · {name}' for sid,name,hit in zip(index['station_ids'],index['station_names'],row) if hit))
    new['관련 트램 정거장']=related
    per_station=pd.DataFrame({'정거장번호':index['station_ids'],'정거장명':index['station_names'],'신규 후보 상가수':(membership & mask[:,None]).sum(axis=0).astype(int)})
    admin=new.groupby(['시군구명','행정동코드','행정동명'],dropna=False).size().rename('후보 상가수').reset_index().sort_values(['후보 상가수','행정동코드'],ascending=[False,True])
    return {'radius':radius,'shops':tagged,'candidates':new,'counts':pd.Series(category).value_counts().reindex(CATEGORIES,fill_value=0).astype(int),'industry':industry_profile(new,industries),'admin':admin,'stations':per_station,'membership':membership}


def radius_comparison(profiles,station_id,industries):
    """기존 집계값만 읽어 누적 반경과 서로 겹치지 않는 띠 범위를 비교한다."""
    summary=[];composition=pd.DataFrame({'업종':industries})
    previous=0
    for radius in [300,500,1000]:
        result=profiles[(station_id,radius)];total=result['total']
        summary.append({'반경':f'{radius:,}m','역할':'주요 탐색 범위' if radius<1000 else '확장 비교 범위','누적 상가수':total,'직전 반경 바깥 추가 상가수':total-previous})
        composition[f'{radius:,}m']=composition['업종'].map(result['profile'].set_index('업종')['상가수']).fillna(0).astype(int)
        previous=total
    return pd.DataFrame(summary),composition
