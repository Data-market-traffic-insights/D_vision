"""현재 개발 웹사이트·좌표 관리·접근권의 기본 회귀 테스트."""
import unittest
import sys
if __name__=='__main__':
    suite=unittest.defaultTestLoader.discover('.',pattern='test_*.py')
    sys.exit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)
