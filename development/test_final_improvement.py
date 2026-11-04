"""별도 후보·동적 승인 목록·두 추천 범위·현재값 강조·화면 상태를 검증한다."""
import hashlib
from copy_review_checks import assert_preserved_source
import json
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from dashboard_data import BASE_DIR,load_dashboard_data
from tram_analysis import load_stations,verified_stations,radius_shops,admin_access
from prototype_logic import recommendation_table,scoped_recommendations,TRAM_SCOPES,PRIORITIES,EXPERIENCES
from tram_scenarios import all_profiles,overlap_summary,SCENARIOS,scenario_visuals

OUT=BASE_DIR/'results/final_improvement_20261104'


class FinalImprovementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=load_dashboard_data();cls.stations=load_stations();cls.profiles=all_profiles(cls.data,cls.stations)

    def test_candidate_evidence_is_pending_and_never_in_production(self):
        row=pd.read_csv(OUT/'coordinate_candidates.csv',dtype={'station_id':str},keep_default_na=False)
        self.assertEqual(row.station_id.tolist(),['217'])
        self.assertTrue(row['map_url'].str.contains('lat=36.357694&lon=127.388427',regex=False).all())
        self.assertTrue(row[['verified_by','verified_at','reviewed_at','coordinate_evidence']].eq('').all().all())
        self.assertTrue(verified_stations(row).empty)
        self.assertEqual(set(self.stations.loc[self.stations.station_id.eq('217'),'latitude']),{''})
        self.assertNotIn('217',set(verified_stations(self.stations).station_id))

    def test_existing_52_test_files_and_inputs_untouched(self):
        baseline=json.loads((OUT/'baseline_manifest.json').read_text())
        for file in baseline:
            if file.startswith('test_') or file in ['app.py','tram_analysis.py','data/tram_stations.csv','data/tram_sources.json','data/daejeon_clean.csv','data/ml_features.csv']:
                assert_preserved_source(self,file,baseline[file])
        self.assertEqual(len(self.data['shops']),79691);self.assertEqual(len(self.data['admin']),82)
        self.assertEqual(set(self.data['admin'].군집),{0,1,2})

    def test_new_approved_slot_automatically_reaches_profiles_access_and_recommendation(self):
        # 복제 좌표는 메모리 안의 테스트 전용 자료이다. 실제 CSV·지도·보고서에 쓰지 않는다.
        expanded=self.stations.copy();fixture=verified_stations(self.stations).iloc[0]
        for c in self.stations.columns:
            if c not in ['station_id','station_name','source_page']:expanded.loc[expanded.station_id.eq('201'),c]=fixture[c]
        expanded.loc[expanded.station_id.eq('201'),'verified_by']='자동 테스트 전용 가상 승인'
        profiles=all_profiles(self.data,expanded)
        self.assertEqual(len(profiles),18)
        for radius in [300,500,1000]:self.assertEqual(profiles[('201',radius)]['shop_ids'],profiles[(fixture.station_id,radius)]['shop_ids'])
        before,_=overlap_summary(self.profiles,500);after,_=overlap_summary(profiles,500)
        self.assertEqual(before['union'],after['union']);self.assertGreater(after['station_sum'],before['station_sum'])
        selected=scoped_recommendations(self.data,expanded,'음식',[PRIORITIES[3]],scope=TRAM_SCOPES[0],station_id='201')
        self.assertTrue(len(selected)>0)
        app=AppTest.from_file(str(BASE_DIR/'prototype_app.py'),default_timeout=30).run()
        # 현재 CSV의 승인 목록과 실제 UI 마커 수가 동적으로 일치하는지도 검사한다.
        app.radio(key='main_map_mode').set_value('트램 연계 시나리오').run()
        self.assertEqual(len(app.selectbox(key='prototype_tram_station').options),len(verified_stations(self.stations)))

    def test_selected_candidates_use_radius_membership_for_every_station_and_radius(self):
        for _,s in verified_stations(self.stations).iterrows():
            for radius in [300,500,1000]:
                table=scoped_recommendations(self.data,self.stations,'음식',[PRIORITIES[0]],radius,TRAM_SCOPES[0],s.station_id)
                subset,_=radius_shops(self.data['shops'],s,radius)
                self.assertEqual(set(table['행정동코드']),set(subset['행정동코드']))
                self.assertEqual(int(table['접근상가수'].sum()),len(subset))
                self.assertEqual(int(table['반경내선택업종상가수'].sum()),int(subset['상권업종대분류명'].eq('음식').sum()))
                np.testing.assert_allclose(table['반경내선택업종비율(%)'],table['반경내선택업종상가수']/table['접근상가수']*100)

    def test_global_scope_keeps_legacy_scores_and_union(self):
        for priorities in [[PRIORITIES[3]],[PRIORITIES[0],PRIORITIES[3]],PRIORITIES[:2]]:
            actual=scoped_recommendations(self.data,self.stations,'음식',priorities)
            old=recommendation_table(self.data,self.stations,'음식',priorities)
            expected=old.loc[old['접근상가수'].gt(0)].reset_index(drop=True)
            pd.testing.assert_frame_equal(actual[expected.columns],expected)
        total,_=overlap_summary(self.profiles,500)
        self.assertEqual(int(actual['접근상가수'].sum()),total['union'])

    def test_selected_scores_use_full_82_normalization_before_candidate_filter(self):
        sid='225';one=verified_stations(self.stations).loc[lambda s:s.station_id.eq(sid)]
        priorities=[PRIORITIES[0],PRIORITIES[3]]
        actual=scoped_recommendations(self.data,self.stations,'음식',priorities,scope=TRAM_SCOPES[0],station_id=sid)
        expected=recommendation_table(self.data,one,'음식',priorities,access=admin_access(self.data['shops'],one,500))
        pd.testing.assert_frame_equal(actual[expected.columns],expected)
        global_counts=self.data['shops'].loc[lambda s:s['상권업종대분류명'].eq('음식')].groupby('행정동코드').size()
        self.assertEqual(actual.set_index('행정동코드')['선택업종상가수'].to_dict(),global_counts.loc[actual['행정동코드']].to_dict())

    def test_fewer_than_five_and_zero_candidate_results_are_not_padded(self):
        table=scoped_recommendations(self.data,self.stations,'음식',[PRIORITIES[3]],300,TRAM_SCOPES[0],'234')
        self.assertTrue(0<len(table)<5)
        # 테스트 전용 승인 복사본을 상가가 없는 범위로 이동해 0개 처리를 확인한다.
        remote=self.stations.copy();mask=remote.station_id.eq('234')
        remote.loc[mask,'latitude']=36.16;remote.loc[mask,'longitude']=127.21
        empty=scoped_recommendations(self.data,remote,'음식',[PRIORITIES[3]],300,TRAM_SCOPES[0],'234')
        self.assertTrue(empty.empty)
        for sid in ['217',None,'가짜']:
            with self.assertRaises(ValueError):scoped_recommendations(self.data,self.stations,'음식',[PRIORITIES[0]],scope=TRAM_SCOPES[0],station_id=sid)

    def test_visual_cards_have_distinct_current_metrics_without_mutation(self):
        for result in self.profiles.values():
            original=result['profile'].copy(deep=True)
            views=[scenario_visuals(result,'음식',s) for s in SCENARIOS]
            self.assertEqual(len({tuple(v['cards']) for v in views}),3)
            self.assertEqual(len({v['color'] for v in views}),3)
            self.assertIn(str(result['total']),views[0]['cards'][0][1].replace(',',''))
            self.assertEqual(views[1]['cards'][2][1],f"{result['diversity']:.3f}")
            self.assertEqual(views[2]['cards'][0][1],f"{result['concentration']:.3f}")
            pd.testing.assert_frame_equal(original,result['profile'])

    def test_ui_dynamic_sixth_station_and_empty_recommendation(self):
        import streamlit as st
        expanded=self.stations.copy();source=verified_stations(self.stations).iloc[0]
        for col in self.stations.columns:
            if col not in ['station_id','station_name','source_page']:
                expanded.loc[expanded.station_id.eq('201'),col]=source[col]
        expanded.loc[expanded.station_id.eq('201'),'verified_by']='메모리 테스트 전용 가상 승인'
        st.cache_data.clear()
        try:
            with patch('tram_analysis.load_stations',return_value=expanded):
                app=AppTest.from_file(str(BASE_DIR/'prototype_app.py'),default_timeout=30).run()
                app.radio(key='main_map_mode').set_value('트램 연계 시나리오').run()
                self.assertEqual(len(app.selectbox(key='prototype_tram_station').options),6)
                deck=json.loads(app.get('deck_gl_json_chart')[0].proto.json)
                markers=next(layer for layer in deck['layers'] if layer['id']=='tram_markers')
                self.assertEqual(len(markers['data']),6)
            remote=expanded.copy()
            remote.loc[remote.station_id.eq('201'),'latitude']=36.16
            remote.loc[remote.station_id.eq('201'),'longitude']=127.21
            st.cache_data.clear()
            with patch('tram_analysis.load_stations',return_value=remote):
                app=AppTest.from_file(str(BASE_DIR/'prototype_app.py'),default_timeout=30).run()
                app.radio(key='main_map_mode').set_value('트램 연계 시나리오').run()
                app.selectbox(key='prototype_tram_station').select('201').run()
                app.button(key='tram_to_finder').click().run()
                app.radio(key='finder_experience').set_value(EXPERIENCES[0]).run()
                app.radio(key='finder_scope').set_value(TRAM_SCOPES[0]).run()
                self.assertTrue(any('추천할 행정동이 없습니다' in i.value for i in app.info))
                self.assertFalse(any(m.label=='사용자 조건 부합도' for m in app.metric))
                self.assertFalse(app.exception,[e.message for e in app.exception])
        finally:
            st.cache_data.clear()

    def test_ui_scope_switch_and_complete_state_roundtrip(self):
        app=AppTest.from_file(str(BASE_DIR/'prototype_app.py'),default_timeout=30).run()
        app.radio(key='main_map_mode').set_value('트램 연계 시나리오').run()
        app.selectbox(key='prototype_tram_station').select('225').run()
        metrics=[m.value for m in app.metric]
        for s in SCENARIOS:
            app.radio(key='tram_scenario').set_value(s).run()
            self.assertEqual([m.value for m in app.metric],metrics)
            self.assertFalse(app.exception,[e.message for e in app.exception])
        charts=[json.loads(c.proto.spec) for c in app.get('plotly_chart')]
        actual=[c for c in charts if c['layout'].get('title',{}).get('text','').startswith('현재 업종 비율 비교')]
        self.assertEqual(len(actual),1)
        self.assertEqual(len(actual[0]['data']),2)  # 두 정거장의 현재 업종 비율
        app.button(key='tram_to_finder').click().run()
        app.radio(key='finder_experience').set_value(EXPERIENCES[0]).run()
        app.radio(key='finder_scope').set_value(TRAM_SCOPES[0]).run()
        self.assertEqual(app.selectbox(key='finder_station').value,'225')
        self.assertEqual(app.selectbox(key='finder_radius').value,500)
        self.assertEqual(app.selectbox(key='finder_radius').proto.default,1)
        expected=scoped_recommendations(self.data,self.stations,'음식',[PRIORITIES[3]],500,TRAM_SCOPES[0],'225')
        self.assertEqual(len([m for m in app.metric if m.label=='사용자 조건 부합도']),min(5,len(expected)))
        app.radio(key='finder_scope').set_value(TRAM_SCOPES[1]).run()
        self.assertEqual(len([m for m in app.metric if m.label=='사용자 조건 부합도']),5)
        app.radio(key='finder_scope').set_value(TRAM_SCOPES[0]).run()
        app.selectbox(key='finder_radius').select(300).run()
        app.selectbox(key='finder_station').select('234').run()
        app.selectbox(key='finder_industry').select('교육').run()
        app.button(key='finder_return_tram').click().run()
        self.assertEqual(app.selectbox(key='prototype_tram_station').value,'234')
        self.assertEqual(app.selectbox(key='prototype_tram_radius').value,300)
        self.assertEqual(app.selectbox(key='prototype_tram_industry').value,'교육')
        app.button(key='tram_to_finder').click().run()
        self.assertEqual(app.radio(key='finder_scope').value,TRAM_SCOPES[0])
        self.assertEqual(app.radio(key='finder_experience').value,EXPERIENCES[0])
        self.assertFalse(app.exception,[e.message for e in app.exception])


if __name__=='__main__':unittest.main(verbosity=2)
