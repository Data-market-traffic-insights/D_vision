# -*- coding: utf-8 -*-
"""검토한 기존 이미지의 판단 기록만 저장한다. 좌표 승인·운영 CSV 쓰기는 없다."""
import csv
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'results/project_cleanup_20261104'
EVIDENCE=BASE/'results/station_final_review_20261104'

ASSESSMENTS={
 '217':('승인 권고',True,
  '한밭대로 위이며 샘머리네거리 동쪽·모정네거리 서쪽, 공원 북측이다. 도면의 두 회색 승강장이 북측 진입로 부근에서 엇갈리는 위치와 후보점이 대응한다. 교차로·공원·두 북측 건물 블록의 상대 위치를 함께 확인했다.',
  '양방향 승강장을 합친 분석용 근사 대표점으로 권고한다. 공식 측량값·정확한 승강장 중심으로 확정하는 권고는 아니다. 지리참조 도면 부재·예정 횡단부 신설·위치 변경 가능성과 정량 오차 미산정은 남는다.',
  '최종 사용자가 도로·구간·시설·승강장·현재 지도 차이의 5개 항목을 확인하고 승인해야 한다. 최신 설계 위치가 바뀌었다면 재검토한다.'),
 '202':('추가 검토 필요',False,
  '계백로의 서대전네거리 서쪽·공원 북쪽 구간은 일치한다. 후보는 교차로 중심이나 제일가구프라자 건물점이 아니다. 도면에는 중앙 횡단부 서쪽의 상대식 두 승강장이 보인다.',
  '지도에서 실제 선택점인 빨간 핀 끝이 도로 남측 가장자리 가까이에 보인다. 주변 주소의 파란 핀과 다르며, 현재 점이 양방향 승강장 통합 중심을 적절히 대표하는지 가로 방향 대응을 확정하기 부족하다. 명확한 오지점으로 단정하지는 않는다.',
  '도면의 각 플랫폼 경계·중심과 도로 횡단 방향을 현행 지도에 대응한다. 예정 횡단부와 현재 횡단부의 차이를 확인한 뒤 중심 적절성을 판단한다.'),
 '233':('추가 검토 필요',False,
  '관저네거리 동쪽·관저지하차도 남측·남동측 건물 블록이라는 구간 관계는 맞는다. 도면의 북→동 곡선 이후 두 승강장 구간과 대조했다. 교차로 중심을 복사한 점은 아니다.',
  '빨간 선택점은 지하차도 본선과 다른 남측 공사 선형·도로 부속 공간에 보이며, 파란 주소 피처는 본선 쪽에 따로 표시된다. 예정 트램 전용 공간과 실제 양방향 플랫폼 통합 중심의 세부 대응을 확인하기 부족하다.',
  '본선·측도·예정 전용선·플랫폼 공간을 구별하는 상세 계획 평면 또는 고해상도 대조로 두 플랫폼의 중심과 현재 후보 관계를 확인한다.'),
 '238':('추가 검토 필요',False,
  '도마네거리 북동쪽 계백로, 남측 아파트와 남서측 농협·북측 골목 구조는 대응한다. 시설 대표점이나 도마네거리 중심점으로 선정한 좌표는 아니다.',
  '기존 도면 이미지에서는 승강장 세부 경계와 예정 횡단부 해석이 제한된다. 저장된 OSM 화면만으로 아디다스·원셀프안경의 현행 위치와 양방향 플랫폼 길이 방향 중심을 충분히 확정하기 어렵다.',
  '승강장 경계가 선명한 도면과 해당 북측 시설·예정 횡단부를 대응해 후보가 두 플랫폼을 대표하는지 확인한다.'),
 '220':('추가 검토 필요',False,
  '대덕대로 도로 공간, 초원아파트 동측·남쪽 교차로 북쪽이며, 북측 진입부/보도교와 맞은편 골목이 보인다. 지도에서 반환한 온약국 파란 피처가 아니라 별도의 빨간 도로 위 선택점이다.',
  '도면은 상대식 승강장과 횡단부를 보여 주지만 현재 보도교·동측 골목에 대한 플랫폼 두 구간의 세부 대응이 완결되지 않았다. 교차로 명칭도 자료마다 다르게 표기되어 이름만으로 같은 위치라고 확정할 수 없다.',
  '아파트 진입부·보도교·동측 골목·남쪽 교차로를 복수 기준점으로 맞추고 각 플랫폼 중심과 후보의 세로 방향 위치를 확인한다.')
}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    OUT.mkdir(exist_ok=True,parents=True)
    rows=list(csv.DictReader((EVIDENCE/'coordinate_candidates.csv').open(encoding='utf-8-sig')))
    records=[]
    evidence_files=[]
    for r in rows:
        sid=r['station_id'];category,recommended,observed,uncertainty,next_step=ASSESSMENTS[sid]
        pdf=('results/final_improvement_20261104/pdf217_detail.png' if sid=='217'
             else f'results/station_final_review_20261104/{sid}_pdf_detail.png')
        mapfile=f'results/station_final_review_20261104/{r["지도증빙"]}'
        evidence_files.extend([pdf,mapfile])
        records.append(dict(station_id=sid,station_name=r['station_name'],latitude=r['latitude'],longitude=r['longitude'],
            source_page=r['source_page'],classification=category,approval_recommended=recommended,
            operational_approved=False,grade='C',observations=observed,uncertainty=uncertainty,next_step=next_step,
            pdf_image=pdf,map_image=mapfile,map_url=r['map_url']))
    evidence_files.append('results/final_improvement_20261104/candidate_217_naver.png')
    evidence_sha={p:sha(BASE/p) for p in evidence_files}
    pdfs=list((BASE/'data').glob('*.pdf'))
    source=next(p for p in pdfs if sha(p)=='97145293277e85a3dbfa03fa3a6116b88675bfe7b340dfee89345984c0568ae4')
    evidence_sha[str(source.relative_to(BASE))]=sha(source)
    (OUT/'candidate_assessments.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'evidence_sha256.json').write_text(json.dumps(evidence_sha,ensure_ascii=False,indent=2),encoding='utf-8')
    ready=[r for r in rows if ASSESSMENTS[r['station_id']][1]]
    with (OUT/'recommended_candidates_staging.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(ready)
    prep={'recommended_ids':[r['station_id'] for r in ready],'operational_csv_sha256':sha(BASE/'data/tram_stations.csv'),
          'applied':False,'human_approval_required':True,'reviewer':'','reviewed_at':'',
          'required_checks':['road_matches','segment_matches','landmarks_match','platform_matches','differences_reviewed'],
          'procedure':'사용자 최종 승인 후 coordinate_ui에서 후보 저장→5개 항목·검토자 확인→기존 approve/save 절차. 현재는 어느 단계도 운영 자료에 적용하지 않음.'}
    (OUT/'approval_preparation.json').write_text(json.dumps(prep,ensure_ascii=False,indent=2),encoding='utf-8')
    docs=BASE/'docs/reviews';docs.mkdir(parents=True,exist_ok=True)
    text='# 정거장 후보 최종 검증 결과\n\n'
    text+='2026년 11월 4일. **승인 권고 1개(217), 추가 검토 4개(202·233·238·220), 사용 부적합 확정 0개**입니다. 승인 권고는 사용자 최종 승인이 아니며 217번도 C·미승인 상태입니다. 운영 좌표 CSV와 기존 승인 5개를 변경하지 않았습니다.\n\n'
    text+='## 검증 범위와 자료\n\n기존 공식 PDF 도면 이미지 5개와 실제 지도 화면 5개를 모두 직접 열어 확인했고 217번의 네이버 건물 대조 화면도 재확인했습니다. 기존 증빙으로 판단하고 같은 지도 검색을 반복하지 않았습니다. 새 좌표를 찾거나 기존 후보 값을 수정하지 않았습니다.\n\n'
    text+=f'공식 원본 PDF의 SHA-256은 `{sha(source)}`로 기존 좌표 자료의 출처 지문과 같습니다. 기존 이미지·지도 증빙 지문은 [검증 기록](../../results/project_cleanup_20261104/evidence_sha256.json)에 저장했습니다. 이미지 지문은 이번 검토 자료를 식별하며 별도의 측량 정확도를 보증하지 않습니다.\n\n'
    text+='지도 핀의 그림 중심이 아닌 끝점과 경위도 검색란을 확인했습니다. 빨간 선택점과 주변 주소를 반환한 파란 피처 핀은 서로 다를 수 있습니다. 도면의 승강장 구간·형태·양방향 위치·교차로·횡단부·시설을 대조했으며 지리참조 변환이나 검증되지 않은 수치 오차 계산은 하지 않았습니다.\n\n'
    text+='| 번호 | 후보 좌표 | PDF | 분류 | 승인 권고 | 운영 상태 |\n| --- | --- | --- | --- | --- | --- |\n'
    for r in records:
        text+=f"| {r['station_id']} | {r['latitude']}, {r['longitude']} | {r['source_page']}쪽 | {r['classification']} | {'예' if r['approval_recommended'] else '아니오'} | C·미승인 유지 |\n"
    for r in records:
        text+=f"\n## {r['station_id']} {r['station_name']}\n\n"
        text+=f"- 후보: **{r['latitude']}, {r['longitude']}**, 공식 PDF **{r['source_page']}쪽**.\n"
        text+=f"- 지도와 승강장 대응: {r['observations']}\n- 확인된 불확실성: {r['uncertainty']}\n"
        text+=f"- 최종 분류: **{r['classification']}**. 승인 권고: **{'예' if r['approval_recommended'] else '아니오'}**.\n"
        text+=f"- 추가 확인/반영 조건: {r['next_step']}\n"
        text+=f"- [후보 지도]({r['map_url']}) · [도면 증빙](../../{r['pdf_image']}) · [지도 증빙](../../{r['map_image']})\n"
    text+='\n## 운영 반영 준비\n\n217번 한 행만 [별도 준비 CSV](../../results/project_cleanup_20261104/recommended_candidates_staging.csv)에 복사했습니다. 승인자·승인일·승인 증거는 공란이며 `manual_review_required`를 유지합니다. [반영 준비 기록](../../results/project_cleanup_20261104/approval_preparation.json)은 현재 운영 CSV 지문과 필요한 5개 검사·절차를 적은 문서이며 자동 적용 도구가 아닙니다.\n\n'
    text+='사용자 최종 승인이 있으면 기존 관리자 화면에서 217번을 선택해 준비 CSV의 좌표·출처·도로·구간·메모를 입력하고 **후보 저장 → 실제 검토자의 5개 항목 및 이름 확인 → 근사 좌표 승인** 순서로 반영할 수 있습니다. 기존 `coordinate_registry`의 변경 전후 백업·지문 검사·승인 절차를 우회하지 않습니다. 이번에는 운영 저장·승인을 실행하지 않았습니다.\n\n'
    text+='이 판단은 기존 증빙 범위의 분석용 근사 대표점에 대한 권고입니다. 공식 측량 좌표나 최신 설계의 확정 위치로 승격하지 않습니다. 현재 실제 분석 가능 정거장은 계속 **5개**입니다.\n'
    (docs/'정거장_후보_최종검증결과.md').write_text(text,encoding='utf-8')
    print('승인 권고 1 / 추가 검토 4 / 사용 부적합 확정 0 · 운영 CSV 변경 없음')


if __name__=='__main__':build()
