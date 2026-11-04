# -*- coding: utf-8 -*-
"""2026-11-04에 실제 화면에서 선택한 후보만 별도 보관. 승인·원본 CSV 수정 없음."""
import pandas as pd
from dashboard_data import BASE_DIR
from tram_analysis import load_stations,station_status
from coordinate_registry import candidate


def build():
    out=BASE_DIR/'results/final_improvement_20261104'
    url='https://www.openstreetmap.org/search?lat=36.357694&lon=127.388427&zoom=18'
    frame=candidate(load_stations(),'217',36.357694,127.388427,
        '공식 정거장 PDF p19 + OpenStreetMap 화면 좌표 읽기',
        'PDF 도로·샘머리공원 북측·북측 건물 블록 대조 후 OSM 주소 보기에서 후보점 선택',
        '한밭대로 샘머리네거리 동측에서 후보점을 선택. 네이버 캠코캐피탈타워(한밭대로 797)·샘머리네거리와 OSM 한밭대로 교차 확인. '
        '도면의 상대식 승강장 두 구간과 새 횡단부를 현행 지도에 대응하는 데 불확실성이 남아 승인 보류. 시설 좌표나 지도 중심 복사 값이 아님.',url,
        road_name='한밭대로',intersection='샘머리네거리 동측~모정네거리 서측',
        platform_description='PDF p19의 공원 북측 상대식 승강장 구간; 양방향 플랫폼 통합 중심 대응 재확인 필요')
    row=frame.loc[frame.station_id.eq('217')].copy()
    row['신뢰도']='C';row['후보선정일']='2026-11-04'
    row['후보기록자']='코드 에이전트 · 후보점 선정만 수행'
    row['추가대조지도']='https://map.naver.com/p/search/캠코캐피탈타워'
    row['분석허용']=False
    assert not station_status(row).analysis_eligible.any()
    row.to_csv(out/'coordinate_candidates.csv',index=False,encoding='utf-8-sig')
    review=pd.read_csv(BASE_DIR/'results/tram_expansion/station_review_45.csv',dtype=str,keep_default_na=False)
    review['이번검토']='기존 PDF 검토 기록 재사용; 추가 지도 대조 미완료'
    review.loc[review.station_id.eq('217'),'이번검토']='OSM·네이버 시설/도로 대조 및 후보점 기록; 플랫폼 통합 중심 미승인'
    review.loc[review['분석허용'].eq('True'),'이번검토']='기존 B 승인 좌표 유지'
    review.to_csv(out/'station_review_45.csv',index=False,encoding='utf-8-sig')
    review.loc[review['분석허용'].ne('True')].to_csv(out/'pending_station_reviews.csv',index=False,encoding='utf-8-sig')
    print('후보 1개 별도 저장. 기존 좌표 CSV·승인 5개 유지.')


if __name__=='__main__':build()
