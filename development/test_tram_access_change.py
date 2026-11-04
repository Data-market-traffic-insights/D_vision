"""신규 접근권의 경계·중복·누락과 실제 앱 회귀 검사. 가상 좌표는 메모리에서만 사용."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from dashboard_data import BASE_DIR,load_dashboard_data
from tram_analysis import load_stations,verified_stations,haversine_m,EARTH_RADIUS_M
from tram_access_change import *

class AccessChangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=load_dashboard_data();cls.stations=load_stations();cls.metro,cls.meta=load_metro_stations()
        cls.index=distance_index(cls.data['shops'],cls.metro,cls.stations)
    def test_official_complete_roster_and_crs(self):
        self.assertEqual(len(self.metro),22);self.assertEqual(self.metro.station_name.tolist(),NAMES)
        self.assertTrue(self.metro.coordinate_crs.eq('EPSG:4326').all())
        self.assertAlmostEqual(float(haversine_m(0,0,0,1)),EARTH_RADIUS_M*np.pi/180,places=6)
    def test_loader_rejects_missing_duplicate_and_unverified(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);(base/'data').mkdir()
            with self.assertRaises(OSError):load_metro_stations(base)
            for kind in ['missing','duplicate','crs','nan','outside','name','hash']:
                frame=self.metro.copy();meta=self.meta.copy()
                if kind=='missing':frame=frame.iloc[:-1]
                if kind=='duplicate':frame.loc[1,'station_id']='101'
                if kind=='crs':frame['coordinate_crs']='EPSG:5179'
                if kind=='nan':frame.loc[0,'latitude']=np.nan
                if kind=='outside':frame.loc[0,'latitude']=127.45
                if kind=='name':frame.loc[0,'station_name']='가상역'
                path=base/'data/metro_line1_stations.csv';frame.to_csv(path,index=False)
                meta['csv_sha256']=hashlib.sha256(path.read_bytes()).hexdigest() if kind!='hash' else 'invalid'
                (base/'data/metro_line1_sources.json').write_text(json.dumps(meta))
                with self.subTest(kind=kind),self.assertRaises(ValueError):load_metro_stations(base)
    def test_boundary_and_invalid_exclusion(self):
        index={'valid':np.array([True]*6+[False]),'existing':np.array([500,500.01,800,100,800,800,0]),'tram':np.array([[500,501],[500,900],[500.01,900],[800,800],[300,400],[800,800],[0,0]])}
        category,membership=classify_access(index,500)
        self.assertEqual(category.tolist(),[CATEGORIES[1],CATEGORIES[2],CATEGORIES[3],CATEGORIES[0],CATEGORIES[2],CATEGORIES[3],CATEGORIES[4]])
        self.assertFalse(membership[-1].any())
        category300,_=classify_access(index,300)
        self.assertEqual(category300.tolist().count(CATEGORIES[2]),1)
        with self.assertRaises(ValueError):classify_access(index,1000)
    def test_real_counts_union_and_industry(self):
        expected={300:[9603,1189,1036,67863,0],500:[15898,4277,1593,57923,0]}
        for radius in (300,500):
            r=access_summary(self.data['shops'],self.index,radius,self.data['industries'])
            self.assertEqual(r['counts'].tolist(),expected[radius]);self.assertEqual(int(r['counts'].sum()),79691)
            self.assertEqual(len(r['candidates']),r['candidates']['상가업소번호'].nunique())
            self.assertEqual(int(r['industry']['상가수'].sum()),len(r['candidates']))
            self.assertAlmostEqual(r['industry']['비율(%)'].sum(),100)
            self.assertEqual(r['admin']['후보 상가수'].sum(),len(r['candidates']))
            # 전체 역·승인 정거장을 각각 조회해 독립적인 기대 집합을 구성한다.
            old=set();tram=set()
            for row in self.metro.itertuples():old.update(self.data['shops'].loc[haversine_m(self.data['shops']['위도'],self.data['shops']['경도'],row.latitude,row.longitude)<=radius+1e-7,'상가업소번호'])
            for row in verified_stations(self.stations).itertuples():tram.update(self.data['shops'].loc[haversine_m(self.data['shops']['위도'],self.data['shops']['경도'],row.latitude,row.longitude)<=radius+1e-7,'상가업소번호'])
            self.assertEqual(set(r['candidates']['상가업소번호']),tram-old)
    def test_overlapping_tram_counted_once_and_empty(self):
        shops=self.data['shops'].iloc[:2].copy()
        index={'valid':np.array([True,True]),'existing':np.array([900,900]),'tram':np.array([[250,450],[900,900]]),'station_ids':['206','224'],'station_names':['검사용1','검사용2']}
        r=access_summary(shops,index,500,self.data['industries'])
        self.assertEqual(len(r['candidates']),1);self.assertEqual(r['stations']['신규 후보 상가수'].sum(),2)
        self.assertIn('206',r['candidates']['관련 트램 정거장'].iloc[0]);self.assertIn('224',r['candidates']['관련 트램 정거장'].iloc[0])
        index['existing'][:]=100
        r=access_summary(shops,index,300,self.data['industries'])
        self.assertTrue(r['candidates'].empty);self.assertTrue(r['admin'].empty);self.assertEqual(r['industry']['비율(%)'].sum(),0)
        with self.assertRaises(ValueError):distance_index(pd.concat([shops,shops]),self.metro,self.stations)
        unapproved=self.stations.copy();unapproved['coordinate_status']='unavailable'
        with self.assertRaises(ValueError):distance_index(shops,self.metro,unapproved)
    def test_app_mode_radius_and_empty_filters(self):
        app=AppTest.from_file(str(BASE_DIR/'prototype_app.py'),default_timeout=30).run()
        app.radio(key='main_map_mode').set_value('신규 접근권 편입 후보').run()
        self.assertFalse(app.exception);self.assertFalse(app.error)
        self.assertIn('1,593개',[m.value for m in app.metric])
        deck=json.loads(app.get('deck_gl_json_chart')[0].proto.json)
        self.assertIn('access_shops',[x['id'] for x in deck['layers']])
        app.radio(key='access_change_radius').set_value(300).run()
        self.assertIn('1,036개',[m.value for m in app.metric])
        app.multiselect(key='access_change_categories').set_value([]).run()
        self.assertFalse(app.exception);self.assertTrue(any('표시할 상가가 없습니다' in e.value for e in app.info))
        app.radio(key='main_map_mode').set_value('트램 연계 시나리오').run()
        app.selectbox(key='prototype_tram_station').set_value('225').run()
        self.assertIn('1,663개',[m.value for m in app.metric]);self.assertFalse(app.exception)

if __name__=='__main__':unittest.main(verbosity=2)
