"""미래 정보가 특성·모델 선택에 섞이지 않는지와 실제 평가·화면을 검사한다."""
from pathlib import Path
import json
import unittest
import numpy as np
import pandas as pd
from shop_prediction import (FEATURES,prepare_features,supervised_rows,time_splits,
                              quarter_number,quarter_label,error_metrics,baseline_prediction)

BASE=Path(__file__).resolve().parent


def fixture():
    quarters=[f'{year}{q}' for year in range(2021,2026) for q in range(1,5)]
    panel=pd.DataFrame([{'market_code':'A','sector':'음식','quarter':q,'count':20+i} for i,q in enumerate(quarters)])
    composition=pd.DataFrame([{'market_code':'A','quarter':q,'total_count':100+i,'food_count':20+i,
        'retail_count':50,'service_count':30,'coffee_count':2} for i,q in enumerate(quarters)])
    geo=pd.DataFrame([{'market_code':'A','market_name':'가상 상권','market_type':'A','gu_code':'1',
                      'new_distance_m':250.,'longitude':126.9,'latitude':37.5}])
    return panel,composition,geo


class ShopPredictionTests(unittest.TestCase):
    def test_lags_use_calendar_and_no_future_values(self):
        panel,composition,geo=fixture()
        original=prepare_features(panel,composition,geo)
        changed=panel.copy();changed.loc[changed.quarter>'20234','count']=999
        newer=prepare_features(changed,composition,geo)
        pd.testing.assert_frame_equal(original.loc[original.origin_quarter<='20234',FEATURES],
                                      newer.loc[newer.origin_quarter<='20234',FEATURES])
        row=original.loc[original.origin_quarter=='20214'].iloc[0]
        self.assertEqual((row['count'],row.lag1,row.lag2,row.lag3),(23,22,21,20))
        incomplete=panel.loc[panel.quarter!='20222']
        features=prepare_features(incomplete,composition,geo)
        self.assertNotIn('20224',set(features.origin_quarter))
        self.assertNotIn('20231',set(features.origin_quarter))

    def test_target_horizons_and_time_splits(self):
        panel,composition,geo=fixture();features=prepare_features(panel,composition,geo)
        for horizon in [1,4]:
            samples=supervised_rows(features,panel,horizon)
            self.assertTrue((samples.target_ord-samples.origin_ord).eq(horizon).all())
            train,val,test=time_splits(samples)
            self.assertLess(train.target_ord.max(),val.target_ord.min())
            self.assertLess(val.target_ord.max(),test.target_ord.min())
            self.assertTrue(test.target_quarter.str.startswith('2025').all())
        self.assertEqual(quarter_label(quarter_number('20254')+1),'20261')
        self.assertEqual(quarter_label(quarter_number('20254')+4),'20264')

    def test_baselines_and_metric_meaning(self):
        frame=pd.DataFrame({'count':[10.,0.],'lag3':[7.,1.]})
        np.testing.assert_allclose(baseline_prediction(frame,1,'trend'),[11.,0.])
        metrics=error_metrics([10,20],[12,18])
        self.assertEqual(metrics['mae'],2.)
        self.assertAlmostEqual(metrics['wape_pct'],4/30*100)
        with self.assertRaises(ValueError):error_metrics([1],[np.nan])

    def test_saved_evaluation_and_selection_provenance(self):
        folder=BASE/'data/shop_ml';meta=json.loads((folder/'manifest.json').read_text())
        self.assertFalse(meta['transfer_to_daejeon'])
        self.assertNotIn('actual',meta['features'])
        self.assertNotIn('existing_distance_m',meta['features'])
        self.assertNotIn('pre_total',meta['features'])
        predictions=pd.read_csv(folder/'test_predictions.csv',dtype={'origin_quarter':str,'target_quarter':str})
        for audit in meta['split_audit']:
            self.assertLess(audit['train_target_max'],audit['validation_target_min'])
            self.assertLess(audit['validation_target_max'],audit['test_target_min'])
            self.assertTrue(audit['all_feature_origins_before_targets'])
        for horizon in [1,4]:
            row=meta['selections'][str(horizon)]
            candidates=['ridge','random_forest','gradient_boosting']
            self.assertEqual(row['learned_model'],min(candidates,key=lambda k:row['validation_mae'][k]))
            selected=predictions.loc[predictions.horizon==horizon]
            self.assertTrue(selected.target_quarter.str.startswith('2025').all())
            self.assertTrue(np.isfinite(selected.prediction).all())
            self.assertTrue(selected.prediction.ge(0).all())
            self.assertTrue(selected.origin_quarter.map(quarter_number).lt(selected.target_quarter.map(quarter_number)).all())

    def test_ml_page_scope_horizon_and_forecast(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string('from shop_prediction_ui import prediction_page\nprediction_page()', default_timeout=30).run()
        self.assertFalse(app.exception);self.assertFalse(app.error)
        self.assertEqual(app.selectbox(key='ml_horizon').value,1)
        self.assertTrue(any('학습에 쓰지 않은 2025년' in e.value for e in app.subheader))
        app.selectbox(key='ml_horizon').set_value(4)
        app.selectbox(key='ml_sector').set_value('커피·음료')
        app.run()
        self.assertFalse(app.exception);self.assertFalse(app.error)
        app.selectbox(key='ml_scope').set_value('서울 전체 관측 상권').run()
        self.assertFalse(app.exception);self.assertFalse(app.error)


if __name__=='__main__':unittest.main()
