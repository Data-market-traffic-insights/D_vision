"""후보·승인 상태 전이와 실제 자료의 반경 집계를 분리해 검증."""
import json
import math
import tempfile
import unittest
import shutil
from unittest.mock import patch
from pathlib import Path
import pandas as pd
from coordinate_registry import extend,candidate,approve,save,digest,CHECKS
from tram_analysis import load_stations,verified_stations,station_status,radius_shops,covered_shop_ids,station_summary,scenario_exposure
from dashboard_data import load_dashboard_data,industry_profile
from streamlit.testing.v1 import AppTest


class CoordinateTests(unittest.TestCase):
    def frame(self): return extend(load_stations())
    def proposal(self,frame=None):
        return candidate(self.frame() if frame is None else frame,'201',36.35,127.38,'시험 전용 지도','시험 전용 대조','합성 좌표이며 실제 저장하지 않음',
                         'https://example.test/map',road_name='합성 도로',intersection='합성 교차로',platform_description='합성 승강장 구간')
    def test_candidate_review_edit_and_unknown_uncertainty(self):
        f=self.proposal(); row=f.loc[f.station_id.eq('201')].iloc[0]
        self.assertEqual(row.coordinate_status,'manual_review_required')
        self.assertFalse(station_status(pd.DataFrame([row])).iloc[0].analysis_eligible)
        with self.assertRaises(ValueError): approve(f,'201','시험자',{})
        approved=approve(f,'201','시험자',{key:True for key in CHECKS})
        row=approved.loc[approved.station_id.eq('201')].iloc[0]
        self.assertEqual(row.estimated_uncertainty_m,'')
        self.assertTrue(station_status(pd.DataFrame([row])).iloc[0].analysis_eligible)
        edited=self.proposal(approved); row=edited.loc[edited.station_id.eq('201')].iloc[0]
        self.assertEqual(row.coordinate_status,'manual_review_required');self.assertEqual(row.reviewed_at,'')
        self.assertFalse(station_status(pd.DataFrame([row])).iloc[0].analysis_eligible)
        self.assertEqual(approved.source_sha256.tolist(),f.source_sha256.tolist())
    def test_input_empty_invalid_and_uncertainty_validation(self):
        f=self.frame()
        for lat,lon in [('',127.38),(36.35,''),(float('nan'),127.38),(0,0)]:
            with self.assertRaises(ValueError):candidate(f,'201',lat,lon,'지도','방법','메모','https://example.test')
        with self.assertRaises(ValueError):candidate(f,'201',36.35,127.38,'지도','방법','메모','https://example.test',50)
        missing=f.coordinate_status.eq('unavailable')
        self.assertTrue(f.loc[missing,'latitude'].eq('').all())
    def test_atomic_save_audit_and_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'stations.csv';self.frame().to_csv(path,index=False,encoding='utf-8-sig');before=digest(path)
            save(self.proposal(),path,before,'시험 후보','201')
            self.assertNotEqual(before,digest(path))
            history=path.parent/'tram_coordinate_history'
            self.assertEqual(len(list(history.glob('*_before.csv'))),1)
            self.assertEqual(len(list(history.glob('*_after.csv'))),1)
            with self.assertRaisesRegex(ValueError,'변경'):save(self.frame(),path,before,'충돌 시험','201')
    def test_real_verified_coordinates_counts_and_union(self):
        data=load_dashboard_data();stations=verified_stations(load_stations())
        self.assertGreater(len(stations),0,'실제 시범 좌표 확보 여부를 확인')
        shops=data['shops']; circles=[]
        for _,station in stations.iterrows():
            previous=set()
            for radius in [300,500,1000]:
                subset,_=radius_shops(shops,station,radius)
                # 구현과 별도인 scalar math를 가까운 후보에 적용한다.
                near=shops.loc[(shops['위도']-station.latitude).abs().lt(.02)&(shops['경도']-station.longitude).abs().lt(.02)]
                expected=set()
                for lat,lon,sid in near[['위도','경도','상가업소번호']].itertuples(index=False,name=None):
                    a=math.sin(math.radians(lat-station.latitude)/2)**2+math.cos(math.radians(lat))*math.cos(math.radians(station.latitude))*math.sin(math.radians(lon-station.longitude)/2)**2
                    distance=12742017.6*math.asin(math.sqrt(min(1,a)))
                    if distance<=radius+1e-7:expected.add(sid)
                found=set(subset['상가업소번호']);self.assertEqual(found,expected);self.assertTrue(previous<=found);previous=found
                self.assertEqual(industry_profile(subset,data['industries'])['상가수'].sum(),len(subset))
                if radius==500:circles.append(found)
            counts=[scenario_exposure(shops,station,500,change,'음식',data['industries'])['exposed_shops'] for change in [-20,10,30]]
            self.assertEqual(counts,[len(circles[-1])]*3)
        self.assertEqual(covered_shop_ids(shops,stations,500),set().union(*circles))
        summary=station_summary(shops,stations,data['industries'],500,'음식')
        self.assertEqual(len(summary),len(stations));self.assertTrue(summary['반경(m)'].eq(500).all())
    def test_canonical_status_overrides_legacy_label(self):
        f=self.proposal();f.loc[f.station_id.eq('201'),'verification_status']='공식 좌표'
        self.assertFalse(station_status(f).loc[f.station_id.eq('201'),'analysis_eligible'].iloc[0])

    def test_official_and_approx_are_distinct(self):
        approved=approve(self.proposal(),'201','시험자',{key:True for key in CHECKS})
        approved.loc[approved.station_id.eq('201'),'coordinate_status']='official'
        row=station_status(approved).loc[approved.station_id.eq('201')].iloc[0]
        self.assertTrue(row.analysis_eligible)
        self.assertEqual(row.coordinate_status,'official')
        # 공식 여부는 실제 CSV에서 0개이며, 여기의 변경은 합성 시험 안에만 존재한다.
        self.assertEqual(load_stations().coordinate_status.eq('official').sum(),0)

    def test_manual_editor_blank_input_save_review_and_edit(self):
        import coordinate_ui
        from dashboard_data import BASE_DIR
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);(base/'data/tram_reference').mkdir(parents=True)
            path=base/'data/tram_stations.csv';self.frame().to_csv(path,index=False,encoding='utf-8-sig')
            shutil.copyfile(BASE_DIR/'data/tram_reference/station_201.png',base/'data/tram_reference/station_201.png')
            with patch.object(coordinate_ui,'BASE_DIR',base):
                app=AppTest.from_string('from coordinate_ui import coordinate_editor\ncoordinate_editor()',default_timeout=20).run()
                self.assertFalse(app.exception)
                self.assertEqual(app.text_input(key='coord_201_lat').value,'')
                self.assertEqual(app.text_input(key='coord_201_lon').value,'')
                fields={e.label:e for e in app.text_input}
                for label,value in {'위도':'36.35','경도':'127.38','지도·좌표 출처':'합성 시험 지도',
                                    '대조한 지도 주소':'https://example.test/map','도로명':'합성 도로',
                                    '인접 교차로':'합성 교차로','승강장 예정 구간·주변 시설의 상대 위치':'합성 구간',
                                    '확인 방법':'합성 UI 시험'}.items(): fields[label].set_value(value)
                app.text_area[0].set_value('합성 좌표이며 실제 정거장 파일에 저장하지 않음')
                next(b for b in app.button if b.label.startswith('후보 좌표 저장')).click().run()
                self.assertFalse(app.exception);self.assertFalse(app.error)
                self.assertEqual(load_stations(path).iloc[0].coordinate_status,'manual_review_required')
                self.assertFalse(station_status(load_stations(path)).iloc[0].analysis_eligible)
                self.assertTrue(all(not e.value for e in app.checkbox))
                for checkbox in app.checkbox: checkbox.check()
                next(e for e in app.text_input if e.label=='검토자').set_value('합성 UI 검토자')
                next(b for b in app.button if b.label=='지도 대조 근사 좌표로 승인').click().run()
                self.assertFalse(app.exception);self.assertFalse(app.error)
                self.assertTrue(station_status(load_stations(path)).iloc[0].analysis_eligible)
                app.text_input(key='coord_201_lon').set_value('127.381')
                next(b for b in app.button if b.label.startswith('후보 좌표 저장')).click().run()
                self.assertFalse(app.exception);self.assertFalse(app.error)
                self.assertFalse(station_status(load_stations(path)).iloc[0].analysis_eligible)
                self.assertTrue(all(not e.value for e in app.checkbox))

if __name__=='__main__':unittest.main(verbosity=2)
