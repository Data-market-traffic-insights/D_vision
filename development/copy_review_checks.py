"""승인된 UI 문구 시험 변경의 이전 원본과 현재 지문을 함께 검증한다."""
from pathlib import Path
import hashlib
import json
BASE=Path(__file__).resolve().parent

def assert_preserved_source(case,filename,expected):
    manifest=json.loads((BASE/'results/ui_copy_review_20261104/approved_test_changes.json').read_text())
    path=BASE/filename
    public_manifest=BASE/'results/ui_copy_review_20261104/public_metadata_redactions.json'
    redactions=json.loads(public_manifest.read_text()) if public_manifest.exists() else {}
    if filename in redactions:
        entry=redactions[filename]
        case.assertEqual(entry['before_sha256'],expected,filename+' 기존 검증 지문')
        case.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),entry['after_sha256'],filename+' 개인 경로 제거본')
        return
    if filename in manifest:
        entry=manifest[filename]
        before=BASE/'results/ui_copy_review_20261104'/entry['before_file']
        case.assertEqual(hashlib.sha256(before.read_bytes()).hexdigest(),expected,filename+' 이전 원본')
        case.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),entry['after_sha256'],filename+' 검토된 시험')
    else:
        case.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),expected,filename)
