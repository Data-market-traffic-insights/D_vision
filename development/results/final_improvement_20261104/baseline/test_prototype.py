"""새 사용자 진입점과 실제 82개 행정동의 추천·해설을 검증한다. 기존 테스트는 수정하지 않는다."""
import itertools
import json
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from dashboard_data import BASE_DIR,load_dashboard_data,industry_profile,COLORS,exploration_table
from tram_analysis import load_stations,admin_access,verified_stations
from prototype_logic import PRIORITIES,EXPERIENCES,recommendation_table,normalize,reasons,experience_note,admin_summary,FRIENDLY_TYPES

class PrototypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=load_dashboard_data();cls.stations=load_stations();cls.access=admin_access(cls.data['shops'],cls.stations,500)
    def app(self):
        app=AppTest.from_file(str(BASE_DIR/'prototype_app.py'),default_timeout=30).run();self.clean(app);return app
    def clean(self,app):
        self.assertFalse(app.exception,[e.message for e in app.exception]);self.assertFalse(app.error,[e.value for e in app.error])
    def ready(self,app=None):
        app=app or self.app();app.radio(key='active_page').set_value('내 창업 지역 찾기').run()
        app.selectbox(key='finder_industry').select('음식').run()
        app.radio(key='finder_experience').set_value(EXPERIENCES[0]).run()
        app.multiselect(key='finder_priorities').set_value([PRIORITIES[0],PRIORITIES[3]]).run();self.clean(app)
        return app
    def test_scoring_all_single_and_pair_preferences(self):
        for count in [1,2]:
            for choices in itertools.combinations(PRIORITIES,count):
                table=recommendation_table(self.data,self.stations,'음식',choices,access=self.access)
                def scale(v):return (v-v.min())/(v.max()-v.min()) if v.max()!=v.min() else v*0+.5
                full=exploration_table(self.data['shops'],self.data['admin'],'음식').set_index('행정동코드')
                ids=table['행정동코드'].tolist()
                expected={PRIORITIES[0]:1-scale(full['선택업종비율(%)']).loc[ids].reset_index(drop=True),
                          PRIORITIES[1]:scale(full['전체상가수']).loc[ids].reset_index(drop=True),
                          PRIORITIES[2]:scale(full['업종다양성']).loc[ids].reset_index(drop=True),PRIORITIES[3]:table['트램접근상가비율(%)']/100}
                self.assertEqual(len(table),int(self.access['접근상가수'].gt(0).sum()) if PRIORITIES[3] in choices else 82)
                if PRIORITIES[3] in choices:self.assertTrue(table['접근상가수'].gt(0).all())
                np.testing.assert_allclose(table['사용자 조건 부합도'],sum(expected[p] for p in choices)/len(choices)*100)
                self.assertTrue(table['사용자 조건 부합도'].between(0,100).all())
                self.assertTrue(table['사용자 조건 부합도'].is_monotonic_decreasing)
                for _,row in table.head(5).iterrows():
                    text=' '.join(reasons(row,'음식',choices,500))
                    self.assertIn('조건 점수',text)
                    if PRIORITIES[0] in choices:self.assertIn(f"{row['선택업종비율(%)']:.1f}%",text)
    def test_invalid_requests_and_unavailable_station(self):
        for choices in [[],PRIORITIES[:3],[PRIORITIES[0],PRIORITIES[0]],['성공률']]:
            with self.assertRaises(ValueError):recommendation_table(self.data,self.stations,'음식',choices)
        with self.assertRaises(ValueError):recommendation_table(self.data,self.stations,'가상 업종',[PRIORITIES[0]])
        unavailable=self.stations.copy();unavailable['coordinate_status']='unavailable'
        with self.assertRaises(ValueError):recommendation_table(self.data,unavailable,'음식',[PRIORITIES[3]])
        self.assertEqual(len(recommendation_table(self.data,unavailable,'음식',[PRIORITIES[0]])),82)
        self.assertTrue(normalize(pd.Series([2,2])).eq(.5).all())
    def test_actual_summary_and_experience_only_guidance(self):
        for code in self.data['admin']['행정동코드']:
            summary=admin_summary(self.data,self.stations,code,'음식',access=self.access)
            shops=self.data['shops'].loc[self.data['shops']['행정동코드'].eq(code)]
            profile=industry_profile(shops,self.data['industries'])
            self.assertEqual(summary['row']['전체상가수'],len(shops))
            self.assertEqual(summary['selected']['상가수'],len(shops.loc[shops['상권업종대분류명'].eq('음식')]))
            self.assertEqual(summary['top3']['업종'].tolist(),profile.nlargest(3,'상가수')['업종'].tolist())
        self.assertNotEqual(experience_note(EXPERIENCES[0]),experience_note(EXPERIENCES[1]))
        self.assertEqual(set(FRIENDLY_TYPES),{0,1,2})
    def test_initial_map_three_primary_menus_and_modes(self):
        app=self.app()
        self.assertEqual(app.radio(key='active_page').options,['대전 상권 지도','상권 상세 분석','내 창업 지역 찾기'])
        self.assertEqual(app.radio(key='active_page').value,'대전 상권 지도')
        self.assertEqual(app.radio(key='main_map_mode').value,'현재 상권')
        self.assertFalse(any('법정동' in str(e.label) for e in app.radio))
        app.selectbox(key='current_visual').set_value('업종별 상가 분포 지도').run();self.clean(app)
        app.multiselect(key='prototype_map_industries').set_value([]).run();self.clean(app)
        self.assertTrue(any('표시할 상가가 없습니다' in e.value for e in app.info))
        app.selectbox(key='current_visual').set_value('상가 밀집도 지도').run();self.clean(app)
    def test_three_choices_top5_reasons_and_no_experience_weight(self):
        app=self.app();app.button(key='hero_finder').click().run();self.clean(app)
        self.assertIsNone(app.selectbox(key='finder_industry').value)
        self.assertIsNone(app.radio(key='finder_experience').value)
        app=self.ready(app)
        metrics=[m.value for m in app.metric if m.label=='사용자 조건 부합도']
        self.assertEqual(len(metrics),5)
        expected=recommendation_table(self.data,self.stations,'음식',[PRIORITIES[0],PRIORITIES[3]],access=self.access).head(5)
        self.assertEqual(metrics,[f'{v:.1f} / 100' for v in expected['사용자 조건 부합도']])
        app.radio(key='finder_experience').set_value(EXPERIENCES[1]).run();self.clean(app)
        self.assertEqual(metrics,[m.value for m in app.metric if m.label=='사용자 조건 부합도'])
    def test_recommendation_map_highlight_detail_and_state_roundtrip(self):
        app=self.ready()
        button=next(b for b in app.button if b.key and b.key.startswith('finder_map_'))
        code=button.key.replace('finder_map_','');button.click().run();self.clean(app)
        self.assertEqual(app.radio(key='active_page').value,'대전 상권 지도')
        self.assertEqual(app.selectbox(key='map_admin').value,code)
        # AppTest의 실제 지도 JSON에서 선택 강조 계층을 확인한다.
        deck=app.get('deck_gl_json_chart')[0].proto.json
        payload=json.loads(deck);self.assertIn('selected_admin',{l['id'] for l in payload['layers']})
        app.button(key='map_to_detail').click().run();self.clean(app)
        self.assertEqual(app.selectbox(key='detail_admin').value,code)
        app.button(key='detail_to_finder').click().run();self.clean(app)
        self.assertEqual(app.multiselect(key='finder_priorities').value,[PRIORITIES[0],PRIORITIES[3]])
    def test_comparison_can_change_both_candidates(self):
        app=self.ready()
        next(b for b in app.button if b.key and b.key.startswith('finder_compare_')).click().run();self.clean(app)
        a=app.selectbox(key='finder_compare_a')
        codes=recommendation_table(self.data,self.stations,'음식',[PRIORITIES[0],PRIORITIES[3]],access=self.access).head(5)['행정동코드']
        other=next(i for i in codes if i!=a.value)
        a.select(other).run();self.clean(app)
        self.assertEqual(app.selectbox(key='finder_compare_a').value,other)
        self.assertNotEqual(other,app.selectbox(key='finder_compare_b').value)
    def test_tram_real_counts_and_finder_connection(self):
        app=self.app();app.radio(key='main_map_mode').set_value('트램 연계 시나리오').run();self.clean(app)
        self.assertEqual(set(app.selectbox(key='prototype_tram_station').options),{'206 · 대전역(중앙시장)','218 · 정부청사(서구청·둔산경찰서·을지대병원)','224 · 궁동(충남대)','225 · 유성온천(유성온천공원)','234 · 관저(건양대병원)'})
        app.selectbox(key='prototype_tram_station').select('225').run();self.clean(app)
        self.assertTrue(any(m.value=='1,663개' for m in app.metric))
        # 기준 방문객 자료가 없는 변화율 슬라이더를 정성적 시나리오로 교체했다.
        app.radio(key='tram_scenario').set_value('방문 수요 감소 가정').run();self.clean(app)
        self.assertTrue(any(m.value=='1,663개' for m in app.metric))
        app.button(key='tram_to_finder').click().run();self.clean(app)
        self.assertEqual(app.radio(key='active_page').value,'내 창업 지역 찾기')
        self.assertEqual(app.multiselect(key='finder_priorities').value,[PRIORITIES[3]])

    def test_auxiliary_community_preserved_without_legal_region_widgets(self):
        app=self.app()
        app.selectbox(key='prototype_aux').select('시연용 창업 커뮤니티').run();self.clean(app)
        self.assertTrue(any('전체 가상 게시글 12개' in c.value for c in app.caption))
        self.assertFalse(any('법정동' in str(e.label) for e in list(app.selectbox)+list(app.radio)))
        app.text_input(key='prototype_post_query').set_value('존재하지않는시연문구').run();self.clean(app)
        self.assertTrue(any('조건에 맞는 시연글이 없습니다' in c.value for c in app.info))

if __name__=='__main__':unittest.main(verbosity=2)
