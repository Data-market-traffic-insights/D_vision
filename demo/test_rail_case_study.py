"""개통 전 매칭, 비교 차이 재현, 불확실성 해석과 화면을 검사한다."""
from pathlib import Path
import json
import unittest
import numpy as np
import pandas as pd
from rail_case_study import (MATCH_QUARTERS,PRE_QUARTERS,POST_QUARTERS,
    matched_pairs,estimate_comparison,evidence_status,cluster_interval)

BASE=Path(__file__).resolve().parent


class RailCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder=BASE/'data/sillim_study'
        cls.results=json.loads((folder/'summary.json').read_text())
        cls.manifest=json.loads((folder/'manifest.json').read_text())
        cls.geo=pd.read_csv(folder/'geography.csv',dtype={'market_code':str,'nearest_station':str})
        panel=pd.read_csv(folder/'panel.csv',dtype={'market_code':str,'quarter':str})
        cls.panel=panel.loc[panel.sector=='음식'].pivot(index='market_code',columns='quarter',values='count')

    def test_real_sources_scope_and_no_automatic_transfer(self):
        self.assertFalse(self.manifest['transfer_allowed'])
        self.assertEqual(self.manifest['opening_date'],'2022-05-28')
        self.assertEqual(len(self.results),12)
        self.assertEqual(len(self.geo),1650)
        self.assertEqual(len(self.panel.columns),20)
        self.assertFalse(self.geo.market_code.duplicated().any())
        traffic=pd.read_csv(BASE/'data/sillim_study/station_ridership.csv')
        self.assertEqual(len(traffic),11)
        self.assertTrue(traffic.days.eq(218).all())
        self.assertTrue(np.isfinite(traffic.daily_board_alight).all())
        events=pd.read_csv(BASE/'data/sillim_study/events.csv',dtype={'quarter':str})
        self.assertNotIn('20222',set(events.quarter))

    def test_matching_does_not_read_post_or_reserved_pre_values(self):
        pairs,_,_,_=matched_pairs(self.panel,self.geo,500)
        changed=self.panel.copy()
        changed.loc[:,POST_QUARTERS]=changed.loc[:,POST_QUARTERS]*10+123
        changed['20221']=changed['20221']*4+100
        newer,_,_,_=matched_pairs(changed,self.geo,500)
        self.assertEqual(pairs,newer)
        self.assertTrue(pairs)

    def test_real_pairs_respect_scope_and_unique_controls(self):
        pairs,complete,_,_=matched_pairs(self.panel,self.geo,500)
        geo=self.geo.set_index('market_code');used=set()
        for pair in pairs:
            t=geo.loc[pair['treated']]
            self.assertLessEqual(t.new_distance_m,500)
            self.assertLessEqual(pair['max_match_distance'],1)
            for code in pair['controls']:
                self.assertNotIn(code,used);used.add(code)
                c=geo.loc[code]
                self.assertGreaterEqual(c.new_distance_m,1000)
                self.assertLessEqual(c.new_distance_m,5000)
                self.assertEqual(c.market_type,t.market_type)
                self.assertEqual(c.existing_distance_m<=500,t.existing_distance_m<=500)
        self.assertEqual(len(pairs),31)

    def test_known_synthetic_effect_and_station_cluster_reproducibility(self):
        codes=['T1','T2','C1','C2','C3','C4']
        panel=pd.DataFrame(20.,index=codes,columns=PRE_QUARTERS+POST_QUARTERS)
        panel.loc[['T1','T2'],POST_QUARTERS]=np.expm1(np.log1p(20)+.2)
        geo=pd.DataFrame({'market_code':codes,'new_distance_m':[100,150,2000,2100,2200,2300],
            'existing_distance_m':[900]*6,'market_type':['A']*6,'pre_total':[100]*6,
            'nearest_station':['S1','S2','S3','S4','S5','S6']})
        result,_,_=estimate_comparison(panel,geo,500,draws=100)
        self.assertAlmostEqual(result['effect_pct'],np.expm1(.2)*100)
        self.assertAlmostEqual(result['placebo_pct'],0)
        self.assertEqual(cluster_interval([.1,.2,.3],['A','A','B'],100),
                         cluster_interval([.1,.2,.3],['A','A','B'],100))

    def test_uncertainty_and_pre_warning_are_not_positive_effect_labels(self):
        food=next(r for r in self.results if r['sector']=='음식' and r['radius_m']==500)
        coffee=next(r for r in self.results if r['sector']=='커피·음료' and r['radius_m']==500)
        self.assertEqual(evidence_status(food,self.results),'증가·감소 방향 불확실')
        self.assertEqual(evidence_status(coffee,self.results),'개통 전 점검에서 차이 발견')

    def test_study_page_sector_and_radius_controls(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(BASE/'prototype_app.py'),default_timeout=30).run()
        app.radio(key='active_page').set_value('트램 주변 미래 상권').run()
        app.radio(key='forecast_evidence').set_value('신림선 개통 사례').run()
        self.assertFalse(app.exception);self.assertFalse(app.error)
        self.assertTrue(any('증가·감소 방향 불확실' in h.value for h in app.subheader))
        app.selectbox(key='sillim_sector').set_value('커피·음료').run()
        self.assertFalse(app.exception);self.assertTrue(app.warning)
        app.selectbox(key='sillim_radius').set_value(700).run()
        self.assertFalse(app.exception);self.assertFalse(app.error)
        app.radio(key='forecast_evidence').set_value('대전 예정지 분석').run()
        self.assertFalse(app.exception);self.assertFalse(app.error)


if __name__=='__main__':unittest.main()
