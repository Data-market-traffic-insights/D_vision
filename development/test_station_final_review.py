"""이번 좌표 검토는 운영 승인과 분리되며 기존 앱·기존 62개 시험을 보존한다."""
import ast
from copy_review_checks import assert_preserved_source
import hashlib
import json
import unittest
import pandas as pd
from dashboard_data import BASE_DIR
from tram_analysis import load_stations,verified_stations
from coordinate_registry import candidate

OUT=BASE_DIR/'results/station_final_review_20261104'


class DisplayCopyNormalization(ast.NodeTransformer):
    """허용된 화면 함수의 표시 문자열만 무시하고 계산·호출·숫자 구조를 비교한다."""
    def visit_Constant(self,node):
        if isinstance(node.value,str):return ast.copy_location(ast.Constant(value='DISPLAY_TEXT'),node)
        return node
    def visit_Dict(self,node):
        pairs=[(k,v) for k,v in zip(node.keys,node.values) if not (k is None and isinstance(v,ast.Name) and v.id=='TABLE_LABELS')]
        node.keys=[k for k,v in pairs];node.values=[v for k,v in pairs]
        return self.generic_visit(node)
    def visit_Call(self,node):
        if isinstance(node.func,ast.Attribute) and node.func.attr=='rename' and len(node.keywords)==1 and node.keywords[0].arg=='index' and isinstance(node.keywords[0].value,ast.Name) and node.keywords[0].value.id=='TABLE_LABELS':
            return self.visit(node.func.value)
        # 창업 경험의 점수 미반영 도움말과 차트 축 명칭만 추가하도록 허용한다.
        node.keywords=[kw for kw in node.keywords if not (
            kw.arg=='help' and isinstance(kw.value,ast.Constant) and kw.value.value=='창업 경험은 안내 문구에만 사용하며 추천 점수에는 반영하지 않습니다.'
            or kw.arg=='format_func' and isinstance(kw.value,ast.Attribute) and kw.value.attr=='get' and isinstance(kw.value.value,ast.Dict) and [v.value for v in kw.value.value.values if isinstance(v,ast.Constant)]==['선택 정거장 주변','승인된 트램 정거장 전체']
            or kw.arg=='column_config' and isinstance(kw.value,ast.Name) and kw.value.id=='TABLE_LABELS'
            or kw.arg=='labels' and isinstance(kw.value,ast.Dict) and ast.literal_eval(kw.value)=={'상가수':'상가 수','비율(%)':'전체 상가 중 비율(%)'})]
        return self.generic_visit(node)


class StationFinalReviewTests(unittest.TestCase):
    def test_existing_operational_coordinates_and_all_previous_code_are_unchanged(self):
        hashes=json.loads((OUT/'before_sha256.json').read_text())
        for file,expected in hashes.items():
            path=BASE_DIR/file
            if file=='prototype_app.py':
                # 2026-11-04 허용된 트램 UI 확장: 과거 파일은 별도 보존하고,
                # 트램 두 화면의 허용된 확장 외에는 AST로 기존 구조를 검사한다.
                # 최종 문구 교정은 표시 문자열·지정한 도움말/축 명칭만 허용한다.
                before=BASE_DIR/'results/tram_specialization_20261104/prototype_app_before.py'
                self.assertEqual(hashlib.sha256(before.read_bytes()).hexdigest(),expected,file)
                old_tree=ast.parse(before.read_text());new_tree=ast.parse(path.read_text())
                functions={n.name:n for n in new_tree.body if isinstance(n,ast.FunctionDef)}
                display={'get_data','profile_chart','current_map','compare_panel','finder_page','detail_page','auxiliary','main'}
                for node in old_tree.body:
                    if isinstance(node,ast.FunctionDef) and node.name not in {'tram_map','map_page'}:
                        current=functions[node.name]
                        if node.name in display:
                            node=DisplayCopyNormalization().visit(node);current=DisplayCopyNormalization().visit(current)
                        self.assertEqual(ast.dump(node,include_attributes=False),ast.dump(current,include_attributes=False),node.name)
            else:
                assert_preserved_source(self,file,expected)
        self.assertEqual(set(verified_stations(load_stations()).station_id),{'206','218','224','225','234'})

    def test_all_review_candidates_remain_unapproved_even_when_staged_together(self):
        rows=pd.read_csv(OUT/'coordinate_candidates.csv',dtype={'station_id':str},keep_default_na=False)
        self.assertEqual(set(rows.station_id),{'217','202','233','238','220'})
        self.assertTrue(rows[['verified_by','verified_at','reviewed_at','coordinate_evidence']].eq('').all().all())
        self.assertTrue(verified_stations(rows).empty)
        staged=load_stations()
        for _,r in rows.iterrows():
            staged=candidate(staged,r.station_id,r.latitude,r.longitude,r.coordinate_source,
                             r.verification_method,r.reviewer_note,r.map_url,
                             road_name=r.road_name,intersection=r.intersection,platform_description=r.platform_description)
        self.assertEqual(set(verified_stations(staged).station_id),{'206','218','224','225','234'})

    def test_candidate_provenance_and_review_evidence_are_present(self):
        rows=pd.read_csv(OUT/'coordinate_candidates.csv',dtype={'station_id':str},keep_default_na=False)
        originals=load_stations().set_index('station_id')
        for _,r in rows.iterrows():
            self.assertEqual(int(r.source_page),int(originals.loc[r.station_id,'source_page']))
            self.assertTrue((OUT/r['지도증빙']).is_file())
            self.assertIn('mlat=',r.map_url)
            self.assertIn('mlon=',r.map_url)
            self.assertTrue(r.road_name and r.intersection and r.platform_description)
        decision=json.loads((OUT/'review_decision.json').read_text())
        self.assertEqual(decision['decision'],'keep_as_candidates')
        self.assertEqual(decision['approved_ids'],[])


if __name__=='__main__':unittest.main(verbosity=2)
