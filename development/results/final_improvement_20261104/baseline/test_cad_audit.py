"""CAD 검사 근거와 원본 보존·미검증 좌표 제외를 확인한다."""
from pathlib import Path
import hashlib
import gzip
import json
import tempfile
import unittest
from unittest.mock import patch

import cad_audit
from tram_analysis import load_stations,verified_stations,radius_shops
from dashboard_data import load_dashboard_data

ROOT=Path(__file__).resolve().parent/'results/cad_review_20261103'


class CadAuditTests(unittest.TestCase):
    def test_13_sources_preserved_and_audited(self):
        manifest=json.loads((ROOT/'archive_manifest.json').read_text())
        self.assertEqual(manifest['dwg_count'],13)
        self.assertEqual(hashlib.sha256(Path(manifest['archive']).read_bytes()).hexdigest(),manifest['archive_sha256'])
        self.assertEqual(len({r['name'] for r in manifest['files']}),13)
        for n,row in enumerate(manifest['files'],1):
            self.assertEqual(hashlib.sha256(Path(row['extracted_path']).read_bytes()).hexdigest(),row['sha256'])
            self.assertEqual(row['version'],'AC1021')
            audit=json.loads((ROOT/f'audit_{n:02d}.json').read_text())
            self.assertEqual(audit['sha256'],row['sha256'])
            self.assertEqual(audit['name'],row['name'])
            self.assertEqual(audit['header']['INSUNITS'],4)
            self.assertGreater(audit['object_count'],0)
            self.assertTrue(audit['station_texts'])

    def test_crs_not_inferred_from_default_location_or_drawing_xy(self):
        for n in range(1,14):
            audit=json.loads((ROOT/f'audit_{n:02d}.json').read_text())
            self.assertFalse(audit['coordinate_system_confirmed'])
            self.assertEqual(audit['geodata_count'],0)
            self.assertFalse(audit['crs_declarations'])
            self.assertAlmostEqual(audit['header']['LATITUDE'],37.795)
            self.assertAlmostEqual(audit['header']['LONGITUDE'],-122.394)
        fallback=json.loads((ROOT/'audit_03.json').read_text())
        self.assertIn('JSON serialization failed',fallback['reader'])
        self.assertIn('json_decode_error',fallback)

    def test_preserved_data_and_cad_unverified_coordinates_blocked(self):
        snapshot=json.loads((ROOT/'operational_files_audit.json').read_text())
        for name,record in snapshot.items():
            path=Path(name)
            if not path.is_absolute():path=ROOT.parents[2]/path
            # 4단계에서 앱·정거장 파일 수정이 승인됨. 원본 상가·군집 자료 보존은 계속 검사.
            if path.name in {'tram_stations.csv','tram_sources.json','app.py','stage3_ui.py','tram_analysis.py','test_tram_analysis.py','README.md'}: continue
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),record['sha256'])
        stations=load_stations()
        stations=stations.loc[stations.coordinate_status.eq('unavailable')].copy()
        self.assertEqual(len(verified_stations(stations)),0)
        self.assertTrue(stations.latitude.eq('').all())
        self.assertTrue(stations.longitude.eq('').all())
        shops=load_dashboard_data()['shops'].head(1)
        for _,station in stations.iterrows():
            with self.assertRaisesRegex(ValueError,'반경 분석 대상'):
                radius_shops(shops,station,500)

    def test_dxf_header_and_text_parsing(self):
        content='0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n4\n9\n$INSBASE\n10\n12.5\n20\n-3\n30\n0\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n0\nTEXT\n5\nAB1\n8\nTEST\n10\n100\n20\n200\n1\n시험 정거장\n0\nENDSEC\n0\nEOF\n'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'decoded').mkdir()
            path=root/'sample.dxf';path.write_text(content)
            with patch.object(cad_audit,'ROOT',root):result=cad_audit.inspect_dxf(path)
            self.assertEqual(result['header']['INSUNITS'],4)
            self.assertEqual(result['header']['INSBASE'],[12.5,-3,0])
            self.assertEqual(result['station_texts'][0]['text'],'시험 정거장')
            self.assertFalse(result['crs_declarations'])
            with gzip.open(str(path)+'.gz','wt',encoding='utf-8') as out:out.write(content)
            path.unlink()
            with patch.object(cad_audit,'ROOT',root):compressed=cad_audit.inspect_dxf(path)
            self.assertEqual(compressed['header'],result['header'])
            json_path=root/'sample.json'
            minimal={'HEADER':{'INSUNITS':4},'OBJECTS':[{'entity':'TEXT','text_value':'시험 정거장','handle':[0,1,7],'ins_pt':[10,20]}]}
            with gzip.open(str(json_path)+'.gz','wt',encoding='utf-8') as out:json.dump(minimal,out,ensure_ascii=False)
            with patch.object(cad_audit,'ROOT',root):compressed_json=cad_audit.inspect_json(json_path)
            self.assertEqual(compressed_json['header']['INSUNITS'],4)
            self.assertEqual(compressed_json['station_texts'][0]['text'],'시험 정거장')


if __name__=='__main__':unittest.main(verbosity=2)
