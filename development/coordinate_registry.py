"""지도 대조 좌표의 후보→검토→승인 및 원본 열 보존 저장."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import tempfile
import fcntl
import pandas as pd

STATUSES = {'official':'공식 좌표', 'map_verified_approx':'지도 대조 근사 좌표',
            'manual_review_required':'사용자 확인 필요', 'unavailable':'좌표 미확보'}
EXTRA = ['coordinate_status','verification_method','estimated_uncertainty_m','reviewed_at',
         'reviewer_note','map_url','road_name','intersection','platform_description','uncertainty_basis']
CHECKS = ['road_matches','segment_matches','landmarks_match','platform_matches','differences_reviewed']


def extend(frame):
    result=frame.copy()
    for col in EXTRA:
        if col not in result: result[col]=''
    blank=result.coordinate_status.eq('')
    result.loc[blank,'coordinate_status']='unavailable'
    return result


def candidate(frame, station_id, latitude, longitude, source, method, note, map_url='', uncertainty='', uncertainty_basis='', **details):
    result=extend(frame)
    selected=result.station_id.astype(str).eq(str(station_id))
    if selected.sum()!=1: raise ValueError('정거장 번호를 확인해 주세요.')
    try: lat,lon=float(latitude),float(longitude)
    except (TypeError,ValueError): raise ValueError('위도와 경도를 모두 입력해 주세요.')
    if not (math.isfinite(lat) and math.isfinite(lon) and 36.15<=lat<=36.55 and 127.2<=lon<=127.6):
        raise ValueError('유효한 대전 지역 위도·경도를 입력해 주세요.')
    if not all(str(v).strip() for v in [source,method,note,map_url]): raise ValueError('지도 출처·주소·확인 방법·메모가 필요합니다.')
    if str(uncertainty).strip():
        try: u=float(uncertainty)
        except (TypeError,ValueError): raise ValueError('오차 범위는 양수로 입력하거나 비워 두세요.')
        if not math.isfinite(u) or u<=0 or not uncertainty_basis.strip(): raise ValueError('양수인 오차 범위와 산정 근거가 필요합니다.')
    values=dict(latitude=lat,longitude=lon,coordinate_source=source,coordinate_status='manual_review_required',
                verification_status='사용자 확인 필요',coordinate_accuracy='분석용 후보 · 오차 미산정',
                coordinate_crs='EPSG:4326',verification_method=method,reviewer_note=note,map_url=map_url,
                estimated_uncertainty_m=uncertainty,uncertainty_basis=uncertainty_basis,
                verified_by='',verified_at='',reviewed_at='',coordinate_evidence='',accuracy_m='')
    for key in ['road_name','intersection','platform_description']: values[key]=str(details.get(key,''))
    for key,value in values.items(): result.loc[selected,key]=value
    return result


def approve(frame, station_id, reviewer, checks):
    result=extend(frame); selected=result.station_id.astype(str).eq(str(station_id))
    if selected.sum()!=1: raise ValueError('정거장 번호를 확인해 주세요.')
    row=result.loc[selected].iloc[0]
    if row.coordinate_status!='manual_review_required': raise ValueError('후보 좌표를 먼저 저장한 뒤 검토해 주세요.')
    if not reviewer.strip() or not all(checks.get(k) is True for k in CHECKS): raise ValueError('검토자와 PDF·지도 대조 5개 항목 확인이 필요합니다.')
    # 승인 시에도 입력 좌표 및 출처를 다시 검사한다.
    candidate(result,station_id,row.latitude,row.longitude,row.coordinate_source,row.verification_method,row.reviewer_note,
              row.map_url,row.estimated_uncertainty_m,row.uncertainty_basis)
    if not all(str(row[k]).strip() for k in ['road_name','intersection','platform_description']):
        raise ValueError('도로·교차로·승강장 구간 설명을 기록해 주세요.')
    now=datetime.now(timezone.utc).isoformat()
    evidence=json.dumps({'checks':checks,'map_url':row.map_url,'pdf_page':int(row.source_page)},ensure_ascii=False)
    values=dict(coordinate_status='map_verified_approx',verification_status='지도 대조 후 검증한 좌표',
                coordinate_accuracy='분석용 근사 좌표 · 정량 오차 미산정' if str(row.estimated_uncertainty_m)=='' else '분석용 근사 좌표 · 오차 근거 별도 기록',
                verified_by=reviewer,verified_at=now,reviewed_at=now,coordinate_evidence=evidence)
    for key,value in values.items(): result.loc[selected,key]=value
    return result


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(frame, path, expected_sha256, action, station_id):
    """동시 수정 방지, 변경 전 CSV와 변경 후 CSV·사건 기록을 함께 보존."""
    path=Path(path); history=path.parent/'tram_coordinate_history'; history.mkdir(exist_ok=True)
    with (history/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if digest(path)!=expected_sha256: raise ValueError('다른 작업에서 CSV가 변경되었습니다. 화면을 새로 열어 주세요.')
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        before=path.read_bytes(); after=frame.to_csv(index=False).encode('utf-8-sig')
        (history/f'{stamp}_before.csv').write_bytes(before)
        (history/f'{stamp}_after.csv').write_bytes(after)
        record={'action':action,'station_id':str(station_id),'at':stamp,'before_sha256':expected_sha256,
                'after_sha256':hashlib.sha256(after).hexdigest()}
        (history/f'{stamp}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
        fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.tram_',suffix='.csv')
        try:
            with os.fdopen(fd,'wb') as out: out.write(after); out.flush(); os.fsync(out.fileno())
            os.replace(tmp,path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
