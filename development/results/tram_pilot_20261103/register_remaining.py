# -*- coding: utf-8 -*-
"""2026-11-03 실제 지도에서 확인한 두 점의 검토 기록. 재실행하지 않는다."""
from pathlib import Path
import json
from coordinate_registry import candidate, approve, save, digest, CHECKS
from tram_analysis import load_stations

p = Path('data/tram_stations.csv')
records = [
    ('206', 36.329505, 127.433499, '대전로',
     '중앙로 남쪽·원동사거리 북쪽 시장 연결 골목 교차부',
     '대전도매시장·대전중앙시장 동쪽, 역전시장 서쪽 대전로의 시장 연결 횡단부 남쪽 예정 승강장 구간',
     'PDF 8페이지의 대전로 사선 방향, 대전역 남서측·역전시장 서측, 서쪽 시장 골목과 동쪽 역전2길 연결부 및 남쪽 원동사거리를 OSM에서 대조. 시장 연결 교차부 남쪽 도로 위 구간을 화면에서 선택. OSM은 시장 상호 일부를 생략하여 도로망과 건물 블록 형태를 함께 비교함. 시설 대표점이 아닌 예정 구간 근사점이며 정량 오차 미산정.'),
    ('234', 36.302844, 127.342567, '계백로',
     '관저네거리 동쪽·가수원네거리 서쪽·건양대병원네거리 동쪽',
     '건양대학교병원 남쪽, 느리울마을 주공11단지 북서쪽, 병원 앞 횡단부 서쪽 계백로 중앙 예정 승강장 구간',
     'PDF 36페이지의 계백로 동북 방향, 병원 건물군 북측·주공11단지 남동측 및 횡단부를 OSM에서 대조. 병원 대표점 대신 횡단부 바로 서쪽 도로 중앙 예정 구간 중간 부근 선택. 현황 지도는 공사 선형을 포함하며 예정 도면과 도로·주변 시설 배치가 대응하나 승강장 측량 중심점은 미확인. 정량 오차 미산정.')
]
for sid, lat, lon, road, junction, platform, note in records:
    sha = digest(p)
    frame = load_stations()
    if frame.loc[frame.station_id.eq(sid), 'coordinate_status'].iloc[0] != 'unavailable':
        raise ValueError('이미 기록된 좌표이므로 재등록하지 않습니다.')
    url = f'https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=18/{lat}/{lon}'
    new = candidate(frame, sid, lat, lon, '공식 정거장 상세위치 PDF + OpenStreetMap 기여자',
                    'PDF 도로·교차로·시설 상대 위치·승강장 예정 구간 시각 대조 후 OSM 우클릭 주소 보기 경위도 기록',
                    note, url, road_name=road, intersection=junction, platform_description=platform)
    save(new, p, sha, 'PDF·지도 대조 후보 기록', sid)
    approved = approve(new, sid, 'Codex · PDF 및 OSM 화면 대조', {k: True for k in CHECKS})
    save(approved, p, digest(p), '지도 대조 근사 좌표 승인', sid)
record_path = Path('results/tram_pilot_20261103/map_review_records.json')
record_path.write_text(json.dumps(json.loads(record_path.read_text()) + records, ensure_ascii=False, indent=2))
