"""실제 CSV 집계와 Streamlit 사용자 흐름의 회귀 검증. 추가 패키지 불필요."""
from pathlib import Path
import json
import shutil
import tempfile
import unittest
import warnings

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard_data import (BASE_DIR, load_dashboard_data, industry_profile, entropy,
                            exploration_table, select_shops, map_points, make_map,
                            validate_run, region_table, file_hash)


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_dashboard_data()

    def app(self):
        app = AppTest.from_file(str(BASE_DIR / 'app.py'), default_timeout=30).run()
        self.assertFalse(app.exception)
        return app

    def clean(self, app):
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertFalse(app.error, [e.value for e in app.error])

    def test_actual_data_and_saved_summary(self):
        d = self.data
        self.assertEqual((len(d['shops']), len(d['admin']), len(d['industries'])), (79691, 82, 10))
        self.assertEqual(d['admin'].groupby('군집').size().tolist(), [35, 22, 25])
        counts = d['shops'].groupby('시군구명').size().to_dict()
        self.assertEqual(counts, {'대덕구': 8351, '동구': 11666, '서구': 27421, '유성구': 19035, '중구': 13218})
        self.assertEqual(d['admin']['전체상가수'].sum(), 79691)
        for row in d['admin'].itertuples():
            shops = select_shops(d['shops'], dong=row.행정동코드)
            self.assertAlmostEqual(entropy(industry_profile(shops, d['industries'])), row.업종다양성)

    def test_legal_regions_do_not_inherit_admin_cluster(self):
        d = self.data
        self.assertNotIn('군집', d['legal'])
        for name in ['궁동', '봉명동', '둔산동', '은행동', '관저동']:
            regions = d['legal'].loc[d['legal']['법정동명'].eq(name)]
            self.assertEqual(len(regions), 1)
            code = regions.iloc[0]['법정동코드']
            shops = d['shops'].loc[d['shops']['법정동코드'].eq(code)]
            self.assertEqual(len(shops), regions.iloc[0]['전체상가수'])
        bong = d['shops'].loc[d['shops']['법정동명'].eq('봉명동')]
        self.assertEqual(set(bong['행정동명']), {'온천1동', '원신흥동'})
        self.assertEqual(set(d['shops'].loc[d['shops']['법정동명'].eq('둔산동'), '행정동명']), {'둔산1동','둔산2동','둔산3동'})

    def test_exploration_denominator_and_zero_counts(self):
        d = self.data
        table = exploration_table(d['shops'], d['admin'], '음식')
        self.assertEqual(table['선택업종상가수'].sum(), 23052)
        self.assertTrue(np.allclose(table['선택업종비율(%)'], table['선택업종상가수']/table['전체상가수']*100))
        self.assertTrue(exploration_table(d['shops'], d['admin'], '음식', min_shops=99999).empty)
        zero = exploration_table(d['shops'], d['admin'], '음식', medium='존재하지 않는 업종')
        self.assertEqual(len(zero), 82)
        self.assertEqual(zero['선택업종상가수'].sum(), 0)

    def test_map_full_counts_sampling_and_invalid_coordinates(self):
        d = self.data
        points, excluded, located = map_points(d['shops'], 1000)
        self.assertEqual((len(points), excluded, located), (1000, 0, 79691))
        self.assertTrue(points.equals(map_points(d['shops'], 1000)[0]))
        payload = json.loads(make_map(points).to_json())
        self.assertEqual(len(payload['layers'][0]['data']), 1000)
        invalid = d['shops'].head(3).copy()
        invalid.loc[invalid.index[0], '경도'] = np.nan
        invalid.loc[invalid.index[1], '위도'] = 1000
        self.assertEqual(map_points(invalid, 1000)[1:], (2, 1))
        self.assertEqual(industry_profile(d['shops'].iloc[:0], d['industries'])['비율'].sum(), 0)

    def test_corrupt_result_rejected_and_fallback(self):
        d = self.data
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'data').symlink_to(BASE_DIR / 'data', target_is_directory=True)
            (base / 'results').mkdir()
            good = base / 'results/good'
            bad = base / 'results/new_but_broken'
            shutil.copytree(d['run_dir'], good)
            shutil.copytree(d['run_dir'], bad)
            meta = json.loads((bad / 'run_metadata.json').read_text())
            meta['run_at'] = '2099-01-01T00:00:00+09:00'
            (bad / 'run_metadata.json').write_text(json.dumps(meta))
            csv = pd.read_csv(bad / 'clustered_dongs.csv')
            csv.loc[0, '전체상가수'] += 1
            csv.to_csv(bad / 'clustered_dongs.csv', index=False)
            loaded = load_dashboard_data(base)
            self.assertEqual(loaded['run_dir'].name, 'good')
            self.assertTrue(loaded['skipped_runs'])
            (good / 'clustered_dongs.csv').unlink()
            with self.assertRaisesRegex(ValueError, '유효한 K=3'):
                load_dashboard_data(base)

    def test_all_menus_and_detail_selection(self):
        app = self.app()
        self.assertEqual(app.metric[0].value, '79,691개')
        for page in ['지역별 상세 분석','AI 상권 유형 분석','지역 비교','업종별 입지 탐색','상가 분포 지도']:
            app.radio(key='navigation').set_value(page).run()
            self.clean(app)
        app.radio(key='navigation').set_value('지역별 상세 분석').run()
        app.selectbox(key='region_gu').select('서구').run()
        row = self.data['admin'].query('시군구명 == "서구" and 행정동명 == "둔산2동"').iloc[0]
        app.selectbox(key='region_dong_서구').select(row['행정동코드']).run()
        self.clean(app)
        self.assertEqual(app.metric[0].value, '3,003개')
        app.radio(key='navigation').set_value('상가 분포 지도').run()
        self.clean(app)
        self.assertEqual(app.metric[0].value, '3,003개')
        app.selectbox(key='map_industry').select('음식').run()
        expected = len(select_shops(self.data['shops'], '서구', row['행정동코드'], '음식'))
        self.assertEqual(app.metric[0].value, f'{expected:,}개')
        self.clean(app)

    def test_compare_basis_and_medium_industry_and_empty_state(self):
        app = self.app()
        app.radio(key='navigation').set_value('지역 비교').run()
        self.assertIn('법정동 단위', app.info[0].value)
        a = app.selectbox(key='compare_a_법정동').value
        app.selectbox(key='compare_a_법정동').select(app.selectbox(key='compare_b_법정동').value).run()
        self.clean(app)
        self.assertNotEqual(app.selectbox(key='compare_a_법정동').value, app.selectbox(key='compare_b_법정동').value)
        app.radio(key='compare_basis').set_value('행정동').run()
        self.clean(app)
        app.radio(key='navigation').set_value('업종별 입지 탐색').run()
        app.selectbox(key='explore_industry').select('교육').run()
        medium = app.selectbox(key='explore_medium_교육').options[1]
        app.selectbox(key='explore_medium_교육').select(medium).run()
        self.clean(app)
        app.selectbox(key='explore_gu').select('대덕구').run()
        app.slider(key='explore_minimum').set_value(3409).run()
        self.clean(app)
        self.assertTrue(any('없습니다' in i.value for i in app.info))


if __name__ == '__main__':
    unittest.main(verbosity=2)
