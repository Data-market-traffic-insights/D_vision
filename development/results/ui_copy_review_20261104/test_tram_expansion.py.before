"""승인 경계·실제 집계·가정 분리·추천 화면의 상태 연결을 검증한다."""
import hashlib
import itertools
import json
import unittest
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from dashboard_data import BASE_DIR,load_dashboard_data
from tram_analysis import load_stations,verified_stations,radius_shops,covered_shop_ids
from tram_scenarios import all_profiles,scenario_explanation,SCENARIOS,station_comparison,overlap_summary
from prototype_logic import PRIORITIES,EXPERIENCES,recommendation_table


class ExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=load_dashboard_data();cls.stations=load_stations()
        cls.profiles=all_profiles(cls.data,cls.stations)

    def test_all_45_review_and_preserved_coordinates(self):
        review=pd.read_csv(BASE_DIR/'results/tram_expansion/station_review_45.csv',dtype=str,keep_default_na=False)
        self.assertEqual(set(review.station_id),set(map(str,range(201,246))))
        self.assertTrue(review.station_id.is_unique)
        self.assertEqual(review['신뢰도'].value_counts().to_dict(),{'C':40,'B':5})
        self.assertTrue(review.loc[review['신뢰도'].eq('C'),['latitude','longitude']].eq('').all().all())
        self.assertTrue(review['PDF위치단서'].ne('').all())
        self.assertTrue(review.loc[review['신뢰도'].eq('C'),'분석허용'].eq('False').all())
        old=BASE_DIR/'results/tram_expansion/baseline/data/tram_stations.csv'
        self.assertEqual(old.read_bytes(),(BASE_DIR/'data/tram_stations.csv').read_bytes())

    def test_input_hashes_and_original_app_preserved(self):
        metadata=json.loads((BASE_DIR/'results/tram_expansion/analysis_metadata.json').read_text())
        for file,expected in metadata['input_sha256'].items():
            self.assertEqual(hashlib.sha256((BASE_DIR/file).read_bytes()).hexdigest(),expected)
        self.assertEqual(len(self.data['shops']),79691);self.assertEqual(len(self.data['admin']),82)
        self.assertEqual((BASE_DIR/'app.py').read_bytes(),(BASE_DIR/'results/tram_expansion/baseline/app.py').read_bytes())
        self.assertEqual(self.data['admin'].군집.value_counts().to_dict(),{0:35,2:25,1:22})

    def test_unapproved_and_bad_evidence_are_excluded(self):
        changed=self.stations.copy()
        changed.loc[changed.station_id.eq('206'),'coordinate_status']='manual_review_required'
        changed.loc[changed.station_id.eq('218'),'coordinate_evidence']=''
        profiles=all_profiles(self.data,changed)
        self.assertEqual({k[0] for k in profiles},{'224','225','234'})
        self.assertFalse(any(k[0] in ['206','218','201'] for k in profiles))

    def test_all_radii_industry_and_admin_cluster_totals(self):
        self.assertEqual(len(self.profiles),15)
        lookup=self.data['admin'].set_index('행정동코드')['군집']
        for (sid,radius),r in self.profiles.items():
            station=self.stations.loc[self.stations.station_id.eq(sid)].iloc[0]
            shops,_=radius_shops(self.data['shops'],station,radius)
            self.assertEqual(r['total'],len(shops))
            self.assertEqual(r['profile']['상가수'].sum(),r['total'])
            self.assertAlmostEqual(r['profile']['비율(%)'].sum(),100)
            self.assertEqual(int(r['admins']['반경내상가수'].sum()),r['total'])
            self.assertEqual(r['admins'].set_index('행정동코드')['군집'].to_dict(),lookup.loc[r['admins']['행정동코드']].to_dict())
            self.assertTrue(0<=r['concentration']<=1)
            self.assertEqual(set(r['top3']['업종']),set(r['profile'].nlargest(3,'상가수')['업종']))

    def test_overlaps_equal_union_and_identify_memberships(self):
        for radius in [300,500,1000]:
            summary,memberships=overlap_summary(self.profiles,radius)
            union=covered_shop_ids(self.data['shops'],self.stations,radius)
            self.assertEqual(set(memberships),union)
            self.assertEqual(summary['union'],len(union))
            self.assertEqual(summary['station_sum']-summary['duplicate_assignments'],len(union))
        # 실제 정거장 간 겹침 유무와 별개로, 중복 처리를 알려진 집합으로도 검사한다.
        fixture={('a',500):{'shop_ids':{'1','2'}},('b',500):{'shop_ids':{'2','3'}}}
        summary,memberships=overlap_summary(fixture,500)
        self.assertEqual(summary,dict(radius=500,station_sum=4,union=3,overlapping_shops=1,duplicate_assignments=1))
        self.assertEqual(memberships['2'],['a','b'])

    def test_station_comparison_same_radius_and_actual_ratios(self):
        for a,b in itertools.combinations(verified_stations(self.stations).station_id,2):
            table,text=station_comparison(self.profiles[(a,500)],self.profiles[(b,500)],'음식')
            self.assertEqual(len(table),2);self.assertIn('유리함의 차이를 뜻하지 않습니다',text)
            np.testing.assert_allclose(table['선택업종비율(%)'],table['선택업종상가수']/table['전체상가수']*100)
        with self.assertRaises(ValueError):station_comparison(self.profiles[('206',300)],self.profiles[('225',500)],'음식')

    def test_three_scenarios_differ_in_all_explanation_fields_without_score_change(self):
        scores=recommendation_table(self.data,self.stations,'음식',[PRIORITIES[3]])
        for r in self.profiles.values():
            before=r['profile'].copy(deep=True)
            for industry in self.data['industries']:
                variants=[scenario_explanation(r,industry,s) for s in SCENARIOS]
                for field in ['focus','structure','check','compare','why']:
                    self.assertEqual(len({v[field] for v in variants}),3)
            pd.testing.assert_frame_equal(before,r['profile'])
        pd.testing.assert_frame_equal(scores,recommendation_table(self.data,self.stations,'음식',[PRIORITIES[3]]))
        with self.assertRaises(ValueError):scenario_explanation(self.profiles[('206',500)],'음식','예측')

    def test_empty_profile_has_no_invented_observations(self):
        r=self.profiles[('206',500)].copy();r['total']=0;r['profile']=r['profile'].copy()
        r['profile'][['상가수','비율(%)']]=0;r['top3']=r['top3'].iloc[:0]
        for s in SCENARIOS:self.assertIn('구조 해석을 보류',scenario_explanation(r,'음식',s)['structure'])

    def test_ui_scenarios_comparison_context_and_roundtrip(self):
        app=AppTest.from_file(str(BASE_DIR/'prototype_app.py'),default_timeout=30).run()
        app.session_state['finder_answers']={'industry':'소매','experience':EXPERIENCES[0],'priorities':[PRIORITIES[0]]}
        app.radio(key='main_map_mode').set_value('트램 연계 시나리오').run()
        app.selectbox(key='prototype_tram_station').select('225').run()
        app.selectbox(key='prototype_tram_radius').select(300).run()
        app.selectbox(key='prototype_tram_industry').select('교육').run()
        original=[m.value for m in app.metric]
        for s in SCENARIOS:
            app.radio(key='tram_scenario').set_value(s).run()
            self.assertFalse(app.exception,[e.message for e in app.exception])
            self.assertEqual(original,[m.value for m in app.metric])
            text=' '.join(e.value for e in app.markdown)
            self.assertIn('현재 상권 — 실제 데이터',text);self.assertIn('트램 개통 후 변화 가정 — 시나리오',text)
        self.assertFalse(app.slider)
        app.selectbox(key='tram_compare_station').select('234').run()
        payload=json.loads(app.get('deck_gl_json_chart')[0].proto.json)
        self.assertIn('selected_tram',{l['id'] for l in payload['layers']})
        app.button(key='tram_to_finder').click().run()
        self.assertEqual(app.session_state['tram_finder_context'],{'station_id':'225','radius':300,'industry':'교육'})
        self.assertEqual(app.multiselect(key='finder_priorities').value,[PRIORITIES[0],PRIORITIES[3]])
        self.assertEqual(app.selectbox(key='finder_industry').value,'교육')
        self.assertEqual(len([m for m in app.metric if m.label=='사용자 조건 부합도']),5)
        app.button(key='finder_return_tram').click().run()
        self.assertEqual(app.selectbox(key='prototype_tram_station').value,'225')
        self.assertEqual(app.selectbox(key='prototype_tram_radius').value,300)
        self.assertEqual(app.selectbox(key='prototype_tram_industry').value,'교육')
        self.assertFalse(app.exception,[e.message for e in app.exception])
        app.session_state['finder_answers']={'industry':'교육','experience':EXPERIENCES[0],'priorities':PRIORITIES[:2]}
        app.button(key='tram_to_finder').click().run()
        self.assertEqual(app.multiselect(key='finder_priorities').value,PRIORITIES[:2])


if __name__=='__main__':unittest.main(verbosity=2)
