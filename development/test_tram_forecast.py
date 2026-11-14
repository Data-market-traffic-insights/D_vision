"""예측 시간 분리, 시나리오 경계, 원본 집계 회귀 검사."""
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from tram_forecast import (load_forecast_data,predict_share,evaluate_models,
                           forecast_series,demand_scenario,filter_markets)
from tram_outlook import industry_outlook,station_outlook,describe_industry,change_percent

BASE=Path(__file__).resolve().parent


class ForecastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history,cls.demand,cls.markets,cls.metadata=load_forecast_data(BASE)

    def test_snapshot_grid_and_latest_known_count(self):
        h=self.history
        self.assertEqual(len(h),600)
        self.assertEqual(h.groupby(['station_id','radius_m','industry']).size().unique().tolist(),[4])
        current=h.loc[(h.date==h.date.max())&(h.station_id=='225')&(h.radius_m==500)]
        self.assertEqual(int(current.shop_count.sum()),1663)
        self.assertEqual(int(current.loc[current.industry=='음식','shop_count'].iloc[0]),442)
        self.assertEqual([x['rows'] for x in self.metadata['sources']],[72054,68867,78418,79691])

    def test_constant_zero_and_irregular_dates(self):
        s=pd.DataFrame({'date':pd.to_datetime(['2023-09-30','2024-09-30','2025-10-30']),
                        'share_per_10000':[20.,20.,20.]})
        self.assertAlmostEqual(predict_share(s,'2030-09-30'),20)
        s['share_per_10000']=0
        self.assertEqual(predict_share(s,'2030-09-30'),0)
        s['share_per_10000']=[10,20,30]
        self.assertGreater(predict_share(s,'2030-09-30'),30)
        self.assertEqual(predict_share(s,'2025-10-30'),30)
        with self.assertRaises(ValueError):predict_share(s,'2024-01-01')

    def test_validation_uses_only_earlier_dates_for_fit(self):
        original=evaluate_models(self.history)
        changed=self.history.copy()
        changed.loc[changed.date==changed.date.max(),'share_per_10000']*=2
        newer=evaluate_models(changed)
        np.testing.assert_allclose(original['scores'].trend,newer['scores'].trend)
        np.testing.assert_allclose(original['scores'].persistence,newer['scores'].persistence)
        self.assertNotEqual(original['trend_mae'],newer['trend_mae'])

    def test_scenario_is_explicit_and_inactive_before_2030(self):
        self.assertEqual(demand_scenario(100,200,100,50,2030,False),100)
        self.assertEqual(demand_scenario(100,200,100,50,2029,True),100)
        self.assertEqual(demand_scenario(100,200,100,0,2030,True),100)
        self.assertEqual(demand_scenario(100,200,100,50,2030,True),150)
        self.assertEqual(demand_scenario(100,0,100,50,2030,True),50)
        with self.assertRaises(ValueError):demand_scenario(100,200,0,50,2030,True)

    def test_multi_section_token_match(self):
        self.assertIn('둔산꽃길 골목형상점가',filter_markets(self.markets,'4공구').market.tolist())
        self.assertIn('둔산꽃길 골목형상점가',filter_markets(self.markets,'5공구').market.tolist())
        self.assertNotIn('가수원상점가',filter_markets(self.markets,'1공구').market.tolist())

    def test_forecasts_are_finite_and_nonnegative(self):
        method=evaluate_models(self.history)['selected']
        for _,s in self.history.groupby(['station_id','radius_m','industry']):
            result=forecast_series(s,'2035-09-30',method)
            self.assertTrue(np.isfinite(result['count']))
            self.assertGreaterEqual(result['count'],0)
            self.assertLessEqual(result['count'],result['city_reference_count'])

    def test_future_page_controls(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(BASE/'prototype_app.py'),default_timeout=30).run()
        app.radio(key='active_page').set_value('트램 주변 미래 상권').run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(len(app.tabs),3)
        self.assertTrue(any('유지되는 경우' in element.value for element in app.markdown))
        app.selectbox(key='forecast_station').set_value('225')
        app.selectbox(key='forecast_industry').set_value('음식')
        app.selectbox(key='forecast_method').set_value('trend')
        app.checkbox(key='forecast_ack').check()
        app.run()
        app.slider(key='forecast_strength').set_value(25).run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        metrics={m.label:m.value for m in app.metric}
        self.assertEqual(metrics['현재 관측 점포 수'],'442개')
        self.assertNotEqual(metrics['수요 가정 적용 점포 수'],metrics['2030년 기본 추정'])
        app.selectbox(key='forecast_year').set_value(2027)
        app.selectbox(key='forecast_section').set_value('4공구')
        app.run()
        self.assertFalse(app.exception)
        metrics={m.label:m.value for m in app.metric}
        self.assertEqual(metrics['수요 가정 적용 점포 수'],metrics['2027년 기본 추정'])

    def test_outlook_separates_local_and_city_change(self):
        stats=industry_outlook(self.history,'225',500,2030)
        row=stats.loc[stats.industry=='음식'].iloc[0]
        self.assertEqual((row.first_count,row.latest_count,row.count_change,row.recent_change),(443,442,-1,18))
        self.assertGreater(row.relative_change_pct,0)
        self.assertIn('덜 줄었습니다',describe_industry(row))
        self.assertEqual(row.persistence_count,442)
        self.assertAlmostEqual(row.relative_change_pct,((442/23052)/(443/23529)-1)*100)
        self.assertEqual(len(stats),10)
        self.assertAlmostEqual(stats.mix_share_pct.sum(),100)

    def test_outlook_no_infinite_growth_from_zero(self):
        self.assertTrue(np.isnan(change_percent(0,4)))
        self.assertAlmostEqual(change_percent(100,90),-10)
        history=pd.DataFrame({'date':pd.to_datetime(['2023-09-30','2024-09-30','2025-10-30','2026-09-30']),
            'station_id':['201']*4,'radius_m':[500]*4,'industry':['음식']*4,
            'shop_count':[0,0,2,4],'city_count':[100]*4,'share_per_10000':[0.,0.,200.,400.]})
        row=industry_outlook(history,'201',500,2030).iloc[0]
        self.assertTrue(np.isnan(row.local_change_pct))
        self.assertTrue(np.isfinite(row.trend_count))
        self.assertIn('첫 시점 점포가 없어',describe_industry(row))

    def test_station_comparison_uses_same_scope_and_demand_rank(self):
        from tram_analysis import load_stations,verified_stations
        stations=verified_stations(load_stations(BASE/'data/tram_stations.csv'))
        table=station_outlook(self.history,stations,self.demand,500,'음식',2030)
        self.assertEqual(len(table),5)
        y=table.loc[table.station_id=='225'].iloc[0]
        self.assertEqual(y.latest_count,442)
        self.assertEqual(y.planned_total,13441)
        self.assertEqual(y.planned_rank,int((self.demand.total_2030>13441).sum()+1))
        self.assertGreater(y.planned_vs_median,1)


if __name__=='__main__':unittest.main()
