"""시점 분리·동일 출처 집계·보류 평가·대전 화면 검증."""
from pathlib import Path
import json
import unittest
import numpy as np
import pandas as pd
from daejeon_transfer import (FEATURES, NUMERIC, feature_rows, paired_rows,
                              elapsed_years, restore_counts, outside_training)
from shop_prediction import error_metrics

BASE = Path(__file__).resolve().parent
FOLDER = BASE/'data/daejeon_transfer'


class DaejeonTransferTests(unittest.TestCase):
    def test_features_do_not_consume_future_and_dates_are_not_quarters(self):
        panel = pd.read_csv(FOLDER/'panel.csv',dtype={'anchor_id':str})
        changed = panel.copy()
        changed.loc[changed.date.eq('2026-09-30'),'food_count'] = 0
        left,right = feature_rows(panel),feature_rows(changed)
        pd.testing.assert_frame_equal(left.loc[left.date<'2026-09-30',FEATURES],right.loc[right.date<'2026-09-30',FEATURES])
        rows = paired_rows(left,'2025-10-30','2026-09-30')
        self.assertAlmostEqual(rows.elapsed_years.iloc[0],335/365.25)
        np.testing.assert_allclose(restore_counts(rows['count'],rows.annual_log_change,rows.elapsed_years),rows.actual,atol=1e-8)
        self.assertNotIn('actual',FEATURES)
        self.assertNotIn('date',FEATURES)
        with self.assertRaises(ValueError): elapsed_years('2026-09-30','2025-10-30')

    def test_daejeon_common_source_counts_match_original_aggregation(self):
        panel = pd.read_csv(FOLDER/'panel.csv',dtype={'anchor_id':str})
        prior = pd.read_csv(BASE/'data/forecast/station_history.csv',dtype={'station_id':str})
        prior = prior.loc[prior.radius_m.eq(500)]
        for sector,column in [('음식','food_count'),('소매','retail_count'),('수리·개인','service_count')]:
            check = panel.loc[panel.city.eq('대전')].merge(prior.loc[prior.industry.eq(sector)],
                         left_on=['anchor_id','date'],right_on=['station_id','date'],validate='one_to_one')
            self.assertEqual(len(check),20)
            np.testing.assert_array_equal(check[column],check.shop_count)
        self.assertTrue(panel.coffee_count.le(panel.food_count).all())

    def test_selection_uses_only_seoul_validation_and_test_scores_recompute(self):
        meta = json.loads((FOLDER/'manifest.json').read_text())
        self.assertFalse(meta['daejeon_used_for_training'])
        self.assertFalse(meta['tram_causal_effect'])
        self.assertFalse(meta['quarterly_model_reused'])
        self.assertLess(meta['train_target'],meta['validation_target'])
        self.assertLess(meta['refit_target_max'],meta['test_target'])
        metrics = pd.read_csv(FOLDER/'metrics.csv')
        val = metrics.loc[metrics.split.eq('seoul_validation_2025')].set_index('model').mae
        self.assertEqual(meta['selected_learned_model'],val.loc[['ridge','random_forest','gradient_boosting']].idxmin())
        self.assertEqual(meta['validation_recommendation'],val.idxmin())
        tests = pd.read_csv(FOLDER/'test_predictions.csv')
        for city,group in tests.groupby('city'):
            for name,col in [(meta['selected_learned_model'],'prediction'),(meta['selected_baseline'],'baseline_prediction')]:
                row = metrics.loc[metrics.split.eq(city+'_test_2026')&metrics.model.eq(name)].iloc[0]
                self.assertAlmostEqual(row.mae,error_metrics(group.actual,group[col])['mae'])
                self.assertEqual(row.rows,len(group))
        self.assertEqual(len(tests.loc[tests.city.eq('대전')]),20)
        future = pd.read_csv(FOLDER/'latest_predictions.csv')
        self.assertEqual(len(future),20)
        self.assertTrue(future.origin_date.eq('2026-09-30').all())
        self.assertTrue(future.target_date.eq('2027-09-30').all())
        self.assertTrue(np.isfinite(future.prediction).all())
        self.assertTrue(future.prediction.ge(0).all())
        self.assertNotIn('actual',future.columns)

    def test_training_range_warning(self):
        reference = pd.DataFrame({key:[0.,1.] for key in NUMERIC})
        inputs = pd.DataFrame({key:[.5,1.] for key in NUMERIC})
        inputs.loc[1,'food_share'] = 1.1
        np.testing.assert_array_equal(outside_training(inputs,reference),[False,True])

    def test_page_shows_negative_evaluation_and_switches_station_sector(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string('from daejeon_transfer_ui import transfer_page\ntransfer_page()', default_timeout=30).run()
        self.assertFalse(app.exception); self.assertFalse(app.error)
        self.assertTrue(any('못했습니다' in w.value for w in app.warning))
        self.assertEqual(len(app.selectbox(key='transfer_station').options),5)
        self.assertEqual(len(app.selectbox(key='transfer_sector').options),4)
        app.selectbox(key='transfer_station').set_value('225')
        app.selectbox(key='transfer_sector').set_value('카페')
        app.run()
        self.assertFalse(app.exception); self.assertFalse(app.error)
        self.assertTrue(any('2027년 9월 30일' in item.value for item in app.markdown))
        self.assertTrue(any(m.value=='59개' for m in app.metric))


if __name__=='__main__': unittest.main()
