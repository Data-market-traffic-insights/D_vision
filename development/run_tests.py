"""웹사이트 회귀 시험. 미포함 과거 CAD 원본의 재현 시험은 별도로 실행한다."""
from pathlib import Path
import argparse
import unittest
import sys

def main():
    parser=argparse.ArgumentParser(description='D·VISION 개발용 회귀 테스트')
    parser.add_argument('--include-cad',action='store_true',help='별도 보존한 CAD 감사 자료를 복원한 경우에만 추가')
    args=parser.parse_args()
    base=Path(__file__).resolve().parent
    if args.include_cad and not (base/'results/cad_review_20261103/archive_manifest.json').exists():
        parser.error('CAD 재현 자료가 없습니다. 로컬 보관 원본·감사 자료를 복원하고 경로를 확인해 주세요.')
    modules=[p.stem for p in sorted(base.glob('test_*.py')) if args.include_cad or p.name!='test_cad_audit.py']
    if not args.include_cad:print('웹사이트 회귀 시험을 실행합니다. 과거 CAD 재현 4개 시험은 별도 자료가 필요해 기본 실행 대상에서 제외합니다.',flush=True)
    suite=unittest.defaultTestLoader.loadTestsFromNames(modules)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1

if __name__=='__main__':sys.exit(main())
