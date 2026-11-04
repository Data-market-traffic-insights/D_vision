"""실제 업종·행정동 연결 및 새 지도 UI 회귀 검증."""
import json
import unittest
import numpy as np
from streamlit.testing.v1 import AppTest
from dashboard_data import BASE_DIR,load_dashboard_data,map_points,COLORS
from map_visualization import INDUSTRY_COLORS,MODES,rgb,admin_representatives,build_map
from tram_analysis import load_stations


class MapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=load_dashboard_data()
        cls.reps=admin_representatives(cls.data['shops'],cls.data['admin'],cls.data['industries'])
    def clean(self,app):
        self.assertFalse(app.exception,[e.message for e in app.exception]);self.assertFalse(app.error,[e.value for e in app.error])
    def test_actual_industries_fixed_palette(self):
        self.assertEqual(set(INDUSTRY_COLORS),set(self.data['industries']))
        self.assertEqual(len(set(INDUSTRY_COLORS.values())),10)
        points=map_points(self.data['shops'],1000)[0]
        payload=json.loads(build_map(points,MODES[1]).to_json())
        for row in payload['layers'][0]['data']:
            self.assertEqual(row['color'],rgb(INDUSTRY_COLORS[row['industry']]))
        food=points.loc[points['상권업종대분류명'].eq('음식')]
        p=json.loads(build_map(food,MODES[1]).to_json())
        self.assertTrue(all(r['color']==rgb(INDUSTRY_COLORS['음식']) for r in p['layers'][0]['data']))
    def test_all_admin_codes_clusters_and_real_representative(self):
        self.assertEqual(len(self.reps),82)
        self.assertFalse(self.reps[['lat','lon']].isna().any().any())
        expected=self.data['admin'].set_index('행정동코드')
        source=self.data['shops'].set_index('상가업소번호')
        self.assertEqual(set(self.reps['행정동코드']),set(expected.index))
        for _,row in self.reps.iterrows():
            original=source.loc[row['대표좌표_상가업소번호']]
            self.assertEqual(original['행정동코드'],row['행정동코드'])
            self.assertEqual((row.lat,row.lon),(original['위도'],original['경도']))
            self.assertEqual(row['군집'],expected.loc[row['행정동코드'],'군집'])
            self.assertEqual(row['color'],rgb(COLORS[int(row['군집'])]))
            shops=self.data['shops'].loc[self.data['shops']['행정동코드'].eq(row['행정동코드'])]
            self.assertEqual(len(shops),row['전체상가수'])
            self.assertEqual(shops.groupby('상권업종대분류명').size().idxmax(),row['주요업종'])
    def test_mapping_rejects_duplicate_missing_and_wrong_name(self):
        for kind in ['duplicate','missing','name']:
            admin=self.data['admin'].copy()
            if kind=='duplicate':admin.loc[1,'행정동코드']=admin.loc[0,'행정동코드']
            elif kind=='missing':admin=admin.iloc[:-1]
            else:admin.loc[0,'행정동명']='잘못된명칭'
            with self.assertRaises(ValueError):admin_representatives(self.data['shops'],admin,self.data['industries'])
    def test_three_modes_and_tram_only_verified(self):
        points=map_points(self.data['shops'],1000)[0]
        density=json.loads(build_map(points,MODES[0]).to_json())
        self.assertEqual(density['layers'][0]['getFillColor'],[18,124,128,160])
        clusters=json.loads(build_map(self.reps,MODES[2]).to_json())
        self.assertEqual(len(clusters['layers'][0]['data']),82)
        colored=json.loads(build_map(points,MODES[1],load_stations()).to_json())
        layers={r['id']:r for r in colored['layers']}
        self.assertEqual(len(layers['shops']['data']),1000)
        self.assertEqual(len(layers['tram_markers']['data']),5)
        self.assertEqual({r['name'].split(' · ')[0] for r in layers['tram_markers']['data']},{'206','218','224','225','234'})
        stations=load_stations();stations.loc[stations.station_id.eq('224'),'coordinate_status']='manual_review_required'
        again=json.loads(build_map(points,MODES[1],stations).to_json())
        self.assertEqual(len(next(r for r in again['layers'] if r['id']=='tram_markers')['data']),4)
    def test_ui_modes_filters_empty_and_detail_navigation(self):
        app=AppTest.from_file(str(BASE_DIR/'app.py'),default_timeout=30).run()
        app.radio(key='navigation').set_value('상가 분포 지도').run();self.clean(app)
        self.assertEqual([m.value for m in app.metric],['79,691개','3,000개','0개'])
        app.radio(key='map_mode').set_value(MODES[1]).run();self.clean(app)
        app.multiselect(key='map_enabled_industries').set_value(['음식']).run();self.clean(app)
        self.assertEqual(app.metric[0].value,'23,052개')
        app.checkbox(key='map_show_tram').check().run();self.clean(app)
        self.assertTrue(any('확인된 5곳' in c.value for c in app.caption))
        app.multiselect(key='map_enabled_industries').set_value([]).run();self.clean(app)
        self.assertEqual(app.metric[0].value,'0개')
        app.radio(key='map_mode').set_value(MODES[2]).run();self.clean(app)
        self.assertEqual([m.value for m in app.metric],['82개','82개','82개'])
        code=app.selectbox(key='map_admin_choice').value
        app.button(key='map_admin_detail').click().run();self.clean(app)
        self.assertEqual(app.radio(key='navigation').value,'지역별 상세 분석')
        self.assertEqual(app.radio(key='detail_basis').value,'행정동')
        row=self.data['admin'].loc[self.data['admin']['행정동코드'].eq(code)].iloc[0]
        self.assertEqual(app.metric[0].value,f'{int(row["전체상가수"]):,}개')
    def test_regional_filter_keeps_original_cluster(self):
        app=AppTest.from_file(str(BASE_DIR/'app.py'),default_timeout=30).run()
        app.radio(key='navigation').set_value('상가 분포 지도').run()
        app.selectbox(key='region_gu').select('서구').run()
        app.radio(key='map_mode').set_value(MODES[2]).run();self.clean(app)
        n=len(self.data['admin'].loc[self.data['admin']['시군구명'].eq('서구')])
        self.assertEqual(app.metric[1].value,f'{n}개')
        code=app.selectbox(key='map_admin_choice').value
        app.selectbox(key='region_dong_서구').select(code).run();self.clean(app)
        self.assertEqual(app.metric[1].value,'1개')

if __name__=='__main__':unittest.main(verbosity=2)
