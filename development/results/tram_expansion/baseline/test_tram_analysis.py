"""합성 좌표는 계산 검증에만 사용하고 실제 정거장 CSV에 저장하지 않는다."""
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import tempfile
import unittest

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard_data import BASE_DIR,load_dashboard_data,industry_profile
from tram_analysis import (EARTH_RADIUS_M,load_stations,station_status,verified_stations,haversine_m,
                           radius_shops,station_summary,covered_shop_ids,admin_access,scenario_exposure,
                           preference_scores,station_map,circle_polygon)
from community import load_examples,filter_examples,DEMO_NOTICE


def synthetic_station(station_id='201',lon=127.38,status='지도 대조 후 검증한 좌표'):
    # 이 값은 실제 정거장 위치가 아니다. 알고리즘의 경계/중복 처리를 확인하는 합성 자료이다.
    return {'station_id':station_id,'station_name':'합성 시험용 정거장','nearby_landmark':'합성 자료',
            'latitude':36.35,'longitude':lon,'coordinate_source':'시험 전용 합성 출처',
            'coordinate_accuracy':'시험용 오차 10m','source_page':3,'verification_status':status,
            'coordinate_crs':'EPSG:4326','verified_by':'합성 테스트','verified_at':'2026-11-03',
            'coordinate_evidence':'합성 테스트이며 실제 정거장 자료가 아님','accuracy_m':10}


def synthetic_shops():
    distances=np.array([0,299,300,301,499,500,501,999,1000,1001],dtype=float)
    rows=[]
    for i,distance in enumerate(distances):
        rows.append({'상가업소번호':f'test-{i}','상호명':f'합성 상가 {i}','시군구명':'시험구',
                     '행정동코드':'test-admin','행정동명':'합성동','법정동코드':'test-legal','법정동명':'합성동',
                     '위도':36.35+np.rad2deg(distance/EARTH_RADIUS_M),'경도':127.38,
                     '상권업종대분류명':'음식' if i%2 else '소매','상권업종중분류명':'합성 중분류'})
    return pd.DataFrame(rows)


class TramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.data=load_dashboard_data()

    def clean(self,app):
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertFalse(app.error,[e.value for e in app.error])

    def test_pdf_inventory_and_source_audit(self):
        stations=load_stations()
        self.assertEqual(stations.station_id.tolist(),list(map(str,range(201,246))))
        self.assertEqual(stations.source_page.astype(int).tolist(),list(range(3,48)))
        self.assertTrue(stations.apply(lambda row:row.source_title.startswith(row.station_id+' '),axis=1).all())
        self.assertEqual(stations.set_index('station_id').loc['226','source_title'],'226 상대정거장정거장')
        for _,row in stations.iterrows():
            source=BASE_DIR/row.source_document
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),row.source_sha256)
            self.assertTrue((BASE_DIR/'data/tram_reference'/f'station_{row.station_id}.png').is_file())
        self.assertTrue(set(stations.coordinate_status).issubset({'official','map_verified_approx','manual_review_required','unavailable'}))
        missing=stations.coordinate_status.eq('unavailable')
        self.assertTrue(stations.loc[missing,'latitude'].eq('').all() and stations.loc[missing,'longitude'].eq('').all())

    def test_unverified_coordinate_gate_and_evidence(self):
        unverified=pd.DataFrame([synthetic_station(status='임시 추정 좌표')])
        self.assertTrue(verified_stations(unverified).empty)
        with self.assertRaisesRegex(ValueError,'반경 분석 대상'):
            radius_shops(synthetic_shops(),unverified.iloc[0],500)
        for field,value in [('coordinate_source','미확보'),('coordinate_evidence',''),('verified_by',''),('verified_at','잘못된 일자'),
                            ('coordinate_crs','EPSG:5179'),('accuracy_m',100),('latitude',0)]:
            station=synthetic_station();station[field]=value
            self.assertTrue(verified_stations(pd.DataFrame([station])).empty,field)
        self.assertEqual(len(verified_stations(pd.DataFrame([synthetic_station()]))),1)
        unavailable=load_stations(); unavailable['coordinate_status']='unavailable'
        self.assertIsNone(covered_shop_ids(synthetic_shops(),unavailable,500))
        self.assertTrue(admin_access(synthetic_shops(),unavailable,500)['트램접근상가비율(%)'].isna().all())

    def test_station_id_integrity(self):
        stations=load_stations();stations.loc[1,'station_id']='201'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'stations.csv';stations.to_csv(path,index=False,encoding='utf-8-sig')
            with self.assertRaisesRegex(ValueError,'45개'):load_stations(path)

    def test_haversine_and_boundary_counts(self):
        self.assertEqual(float(haversine_m(36.35,127.38,36.35,127.38)),0)
        self.assertAlmostEqual(float(haversine_m(0,0,0,1)),111195.0802,places=3)
        shops=synthetic_shops();station=synthetic_station()
        for radius,expected in [(300,3),(500,6),(1000,9)]:
            subset,excluded=radius_shops(shops,station,radius)
            self.assertEqual((len(subset),excluded),(expected,0))
            self.assertEqual(industry_profile(subset,['음식','소매'])['상가수'].sum(),expected)
        invalid=shops.copy();invalid.loc[0,'위도']=np.nan;invalid.loc[1,'경도']=181
        self.assertEqual(radius_shops(invalid,station,300)[1],2)
        with self.assertRaises(ValueError):radius_shops(shops,station,200)

    def test_overlap_union_and_same_radius_density(self):
        shops=synthetic_shops();stations=pd.DataFrame([synthetic_station(),synthetic_station('202')])
        summary=station_summary(shops,stations,['음식','소매'],500,'음식')
        self.assertEqual(summary['전체상가수'].tolist(),[6,6])
        self.assertEqual(summary['반경(m)'].unique().tolist(),[500])
        self.assertEqual(len(covered_shop_ids(shops,stations,500)),6)
        self.assertAlmostEqual(summary.iloc[0]['선택업종밀집도(개/km²)'],3/(np.pi*.5**2))
        access=admin_access(shops,stations,500).iloc[0]
        self.assertEqual(access['접근상가수'],6)
        self.assertEqual(access['트램접근상가비율(%)'],60)

    def test_scenario_exposure_does_not_predict_growth(self):
        shops=synthetic_shops();station=synthetic_station()
        counts=[]
        for change in [-20,0,10,30]:
            scenario=scenario_exposure(shops,station,500,change,'음식',['음식','소매'])
            counts.append(scenario['exposed_shops'])
            self.assertEqual(scenario['selected_industry_shops'],3)
            self.assertNotIn('predicted_sales',scenario)
        self.assertEqual(counts,[6,6,6,6])
        with self.assertRaises(ValueError):scenario_exposure(shops,station,500,31,'음식',['음식','소매'])
        polygon=np.array(circle_polygon(36.35,127.38,500))
        self.assertTrue(np.allclose(haversine_m(polygon[:,1],polygon[:,0],36.35,127.38),500))
        payload=json.loads(station_map(pd.DataFrame([station]),pd.Series(station),shops,500).to_json())
        self.assertEqual({l['id'] for l in payload['layers']},{'radius','shops','stations','station_labels'})

    def test_preference_score_semantics(self):
        df=pd.DataFrame({'선택업종비율(%)':[10,20,30],'업종다양성':[1,2,3]})
        self.assertTrue(preference_scores(df)['사용자 조건 부합도'].isna().all())
        self.assertEqual(preference_scores(df,'높은 비율')['사용자 조건 부합도'].tolist(),[0,50,100])
        self.assertEqual(preference_scores(df,'낮은 비율')['사용자 조건 부합도'].tolist(),[100,50,0])
        self.assertEqual(preference_scores(df,'낮은 비율','높은 다양성')['사용자 조건 부합도'].tolist(),[50,50,50])
        with self.assertRaises(ValueError):preference_scores(df,access=True)

    def test_demo_posts_and_literal_search(self):
        posts=load_examples(self.data['legal'])
        self.assertEqual(len(posts),12)
        self.assertEqual(set(posts.region),{'궁동','봉명동','둔산동','은행동','관저동'})
        self.assertTrue(posts.is_demo.all())
        self.assertTrue(filter_examples(posts,query='[').shape[0]>0)
        self.assertTrue(filter_examples(posts,query='존재하지않는검색어').empty)
        self.assertTrue(filter_examples(posts,region='궁동').region.eq('궁동').all())

    def test_new_pages_and_round_trip_navigation(self):
        app=AppTest.from_file(str(BASE_DIR/'app.py'),default_timeout=30).run()
        self.clean(app)
        app.button(key='home_tram').click().run();self.clean(app)
        self.assertEqual(app.radio(key='navigation').value,'트램 역세권 상권 분석')
        count=len(verified_stations(load_stations()))
        self.assertEqual(app.metric[0].value,'45개')
        self.assertEqual(app.metric[1].value,f'{count}개')
        self.assertEqual(any('반경 내 전체 상가'==m.label for m in app.metric),count>0)
        app.selectbox(key='tram_station').select('224').run();self.clean(app)
        app.radio(key='navigation').set_value('트램 개통 영향 시나리오').run();self.clean(app)
        app.slider(key='scenario_change').set_value(-20).run();self.clean(app)
        app.selectbox(key='scenario_station').select('201').run();self.clean(app)
        self.assertTrue(any('계산할 수 없습니다' in info.value for info in app.info))
        app.radio(key='navigation').set_value('창업 경험 커뮤니티').run();self.clean(app)
        self.assertTrue(any(DEMO_NOTICE==warning.value for warning in app.warning))
        app.selectbox(key='community_region').select('궁동').run();self.clean(app)
        app.button(key='community_to_analysis').click().run();self.clean(app)
        self.assertEqual(app.radio(key='detail_basis').value,'법정동')
        self.assertEqual(app.selectbox(key='detail_legal_code').value,'3020012200')
        community_button=next(b for b in app.button if b.key and b.key.startswith('related_community_'))
        community_button.click().run();self.clean(app)
        self.assertEqual(app.radio(key='navigation').value,'창업 경험 커뮤니티')
        self.assertEqual(app.selectbox(key='community_region').value,'궁동')
        app.text_input(key='community_search').set_value('없는가상문구').run();self.clean(app)
        self.assertTrue(any('없습니다' in info.value for info in app.info))
        app.radio(key='navigation').set_value('업종별 입지 탐색').run();self.clean(app)
        self.assertEqual(app.selectbox(key='explore_tram_access').disabled,len(verified_stations(load_stations()))==0)
        app.selectbox(key='explore_same_preference').select('높은 비율').run();self.clean(app)
        app.selectbox(key='explore_diversity').select('낮은 다양성').run();self.clean(app)
        app.radio(key='explore_basis').set_value('트램 정거장 기반').run();self.clean(app)
        self.assertEqual(any('검증된 정거장 좌표가 확보되면' in info.value for info in app.info),len(verified_stations(load_stations()))==0)

    def test_verified_ui_path_with_synthetic_fixtures_only(self):
        # 실제 데이터 파일에 좌표를 쓰지 않고, 테스트 프로세스 안에서만 합성 정거장을 전달한다.
        import stage3_ui
        mock_stations=station_status(pd.DataFrame([synthetic_station(),synthetic_station('202',127.385)]))
        with patch.object(stage3_ui,'get_stations',return_value=mock_stations):
            app=AppTest.from_file(str(BASE_DIR/'app.py'),default_timeout=30).run()
            app.radio(key='navigation').set_value('트램 역세권 상권 분석').run();self.clean(app)
            self.assertTrue(any(m.label=='반경 내 전체 상가' for m in app.metric))
            app.radio(key='navigation').set_value('트램 개통 영향 시나리오').run();self.clean(app)
            self.assertTrue(any('가정의 분석 대상' in m.value for m in app.markdown))


if __name__=='__main__':unittest.main(verbosity=2)
