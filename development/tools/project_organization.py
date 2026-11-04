# -*- coding: utf-8 -*-
"""자료 조사→문서 이동 계획→보존 압축→링크 수정→검증. 데이터·앱·시험 이동/삭제 없음."""
import argparse
import ast
import csv
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import urllib.parse
import zipfile

BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'results/project_cleanup_20261104'
LINK=re.compile(r'(!?\[[^\]\n]*\]\()([^\n)]*)(\))')
REVIEWS={'CAD_정거장_검사보고서.md','트램_정거장_좌표_최종검증보고서.md'}


def dump(name,data):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def paths():
    for root,dirs,files in os.walk(BASE,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d!='.git')
        for name in sorted(files):yield Path(root)/name


def markdown():
    return [p for p in paths() if p.suffix=='.md' and '.venv' not in p.parts and 'archive' not in p.relative_to(BASE).parts]


def imports():
    modules={p.stem:p for p in BASE.glob('*.py')}
    graph={}
    for name,path in modules.items():
        tree=ast.parse(path.read_text(encoding='utf-8'))
        edges=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):edges.update(a.name.split('.')[0] for a in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module:edges.add(node.module.split('.')[0])
        graph[name]=sorted(edges.intersection(modules))
    runtime=set();pending=['prototype_app','app']
    while pending:
        name=pending.pop()
        if name in runtime:continue
        runtime.add(name);pending.extend(graph.get(name,[]))
    dump('local_import_graph.json',{'method':'AST로 로컬 import를 조사. 전처리·군집 스크립트를 실행하지 않음.',
         'graph':graph,'application_closure':sorted(runtime)})
    return graph,runtime


def local_target(source,raw):
    raw=raw.strip()
    if raw.startswith('<') and raw.endswith('>'):raw=raw[1:-1]
    # 제목이 붙은 Markdown 링크의 경로 부분만 구별한다.
    raw=re.split(r'\s+["\']',raw,maxsplit=1)[0]
    split=urllib.parse.urlsplit(raw)
    if split.scheme or split.netloc or not split.path:return None
    decoded=urllib.parse.unquote(split.path)
    target=Path(decoded) if decoded.startswith('/') else source.parent/decoded
    return Path(os.path.abspath(target)),split


def broken_links():
    broken=[]
    for source in markdown():
        for match in LINK.finditer(source.read_text(encoding='utf-8')):
            parsed=local_target(source,match.group(2))
            if parsed and not parsed[0].exists():
                broken.append({'source':str(source.relative_to(BASE)),'target':str(parsed[0]),'link':match.group(2)})
    return broken


def inventory(label):
    OUT.mkdir(exist_ok=True,parents=True)
    graph,runtime=imports()
    code_sources={str(p.relative_to(BASE)):p.read_text(encoding='utf-8') for p in BASE.glob('*.py')}
    code_sources['run.sh']=(BASE/'run.sh').read_text(encoding='utf-8')
    if (BASE/'README.md').exists():code_sources['README.md']=(BASE/'README.md').read_text(encoding='utf-8')
    rows=[];counts={};sizes={}
    for p in paths():
        rel=p.relative_to(BASE);parts=rel.parts;name=p.name;stat=p.lstat()
        refs=[src for src,text in code_sources.items() if src!=str(rel) and name in text]
        if '.venv' in parts:
            category='실행 필수';purpose='설치된 Python 실행환경·제3자 의존성';action='유지 · 이동/삭제 금지';refs=['run.sh → .venv/bin/python']
        elif '__pycache__' in parts or p.suffix=='.pyc' or name=='.DS_Store':
            category='임시 파일';purpose='Python/운영체제 캐시·메타데이터';action='삭제 보류 · 사용자 확인 전 유지'
        elif name.startswith('test_') and p.suffix=='.py':
            category='테스트';purpose='자동 테스트 또는 보존된 이전 테스트';action='기존 위치 유지'
        elif parts[0]=='data':
            category='원본 데이터';purpose='상가·ML·운영 좌표·출처·공식 PDF·좌표 이력·도면 이미지';action='기존 위치·내용 유지';refs+=['dashboard_data / tram_analysis / coordinate_ui의 고정·동적 데이터 경로']
        elif p.suffix=='.md':
            category='문서';purpose='보고서·검토·사용 안내';action='계획에 명시된 루트 보고서만 이동; 나머지는 유지'
        elif parts[0]=='results':
            category='검증 증빙' if p.suffix in ['.png','.jpg','.jpeg','.log'] or any(v in str(rel) for v in ['review','audit','evidence','baseline']) else '분석 결과'
            purpose='분석·좌표 후보·CAD 검토·지도·테스트·이전 코드의 재현/감사 자료';action='기존 경로 유지 · 이동/삭제 금지';refs+=['분석/시험/문서의 고정 경로 또는 보존 자료']
        elif p.suffix=='.py' and len(parts)==1:
            category='실행 필수' if p.stem in runtime or p.stem in ['clustering','data_preprocessing'] else '분석 결과'
            purpose='사용자/기존 앱의 로컬 모듈' if p.stem in runtime else '전처리·군집·검토·재현용 실행 도구'
            action='기존 위치 유지 · __file__ 기준 경로/지문 의존성 보존'
        elif p.suffix=='.py' and parts[0]=='tools':
            category='검증 증빙';purpose='이번 검토·정리 재현 도구';action='tools/ 유지'
        elif name in ['run.sh','requirements.txt','.gitignore'] or parts[0] in ['.streamlit','.vscode']:
            category='실행 필수';purpose='실행·환경·개발 도구 설정';action='위치 유지'
        elif parts[0]=='archive':
            category='문서';purpose='이동/링크 수정 전 원문 보관';action='보관 · 자동 삭제 금지'
        else:
            category='용도 불명';purpose='자동 분류만으로 용도 확정 불가';action='유지 · 삭제/이동 금지'
        rows.append({'현재경로':str(rel),'파일명':name,'분류':category,'용도':purpose,'바이트':stat.st_size,
                     'mtime_ns':stat.st_mtime_ns,'심볼릭링크':p.is_symlink(),'참조근거':' / '.join(sorted(set(refs))),
                     '정리판단':action})
        counts[category]=counts.get(category,0)+1;sizes[parts[0]]=sizes.get(parts[0],0)+stat.st_size
    with (OUT/f'file_inventory_{label}.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    dump(f'inventory_summary_{label}.json',{'files':len(rows),'counts':counts,'bytes_by_top':sizes,
         'scope':'프로젝트 전체(설치 환경 .venv 포함); .git 내부 제외; 심볼릭 링크를 따라 외부 폴더를 순회하지 않음',
         'reference_limit':'정적 로컬 import·파일명 문자열과 동적 경로 계열을 분리해 기록. 문자열 미검출은 미사용 증명이 아니므로 삭제 근거로 쓰지 않음.'})
    print(json.dumps({'inventory':label,'files':len(rows),'non_environment_files':sum(not str(r['현재경로']).startswith('.venv/') for r in rows),'counts':counts},ensure_ascii=False))


def plan():
    moves={str(p.relative_to(BASE)):str(Path('docs')/('reviews' if p.name in REVIEWS else 'reports')/p.name)
           for p in sorted(BASE.glob('*.md')) if p.name!='README.md'}
    for target in moves.values():
        if (BASE/target).exists():raise ValueError('대상 파일이 이미 있어 이동을 중단합니다: '+target)
    dump('move_plan.json',moves)
    # 데이터·기존 결과·기존 Python·시험 파일의 변경을 구별하기 위한 메타데이터/지문.
    protected={}
    for p in paths():
        rel=p.relative_to(BASE)
        if rel.parts[0] in ['.venv','.git','archive'] or OUT in p.parents or str(rel) in moves or str(rel)=='README.md':continue
        info={'size':p.lstat().st_size,'mtime_ns':p.lstat().st_mtime_ns}
        if p.suffix in ['.py','.csv','.pdf','.sh'] or rel.parts[0]=='data' or (p.name in ['run_metadata.json','cluster_summary.csv','silhouette_scores.csv','clustered_dongs.csv']):
            info['sha256']=sha(p)
        protected[str(rel)]=info
    dump('protected_before.json',protected)
    dump('broken_links_before.json',broken_links())
    text='# 안전한 파일 정리 계획\n\n루트 보고서 '+str(len(moves))+'개만 docs/로 이동합니다. 기존 Python·테스트·data/·results/는 이동하지 않습니다. 캐시 포함 삭제 작업은 수행하지 않습니다. 이동/링크 수정 전 모든 기존 Markdown 원문을 archive ZIP으로 보관합니다.\n\n'
    text+='| 현재 경로 | 이동 경로 |\n| --- | --- |\n'+''.join(f'| {a} | {b} |\n' for a,b in moves.items())
    (OUT/'정리_계획.md').write_text(text,encoding='utf-8')
    print('이동 계획:',len(moves),'개 · 보호 파일:',len(protected),'개')


def organize():
    moves=json.loads((OUT/'move_plan.json').read_text(encoding='utf-8'))
    mapping={BASE/a:BASE/b for a,b in moves.items()}
    sources=markdown()
    original={p:p.read_text(encoding='utf-8') for p in sources}
    archive=BASE/'archive/document_originals_20261104.zip'
    if archive.exists():raise ValueError('원문 보관 ZIP을 덮어쓰지 않습니다.')
    archive.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for path in sources:z.write(path,str(path.relative_to(BASE)))
    dump('archived_markdown_sha256.json',{str(p.relative_to(BASE)):sha(p) for p in sources})
    changes=[]
    for old,new in mapping.items():
        new.parent.mkdir(exist_ok=True,parents=True)
        shutil.move(str(old),str(new))
    for old,body in original.items():
        new=mapping.get(old,old)
        def replace(match):
            parsed=local_target(old,match.group(2))
            if not parsed:return match.group(0)
            target,split=parsed;target=mapping.get(target,target)
            if old==new and target==parsed[0]:return match.group(0)
            relative=os.path.relpath(target,new.parent).replace(os.sep,'/')
            target_text=relative+('?' + split.query if split.query else '')+('#'+split.fragment if split.fragment else '')
            if ' ' in target_text:target_text='<'+target_text+'>'
            changes.append({'source_before':str(old.relative_to(BASE)),'source_after':str(new.relative_to(BASE)),
                            'link_before':match.group(2),'link_after':target_text})
            return match.group(1)+target_text+match.group(3)
        updated=LINK.sub(replace,body)
        if updated!=body:new.write_text(updated,encoding='utf-8')
    dump('link_changes.json',changes)
    print('보고서 이동:',len(moves),'개 · 링크 수정:',len(changes),'건 · 삭제: 0개')


def verify():
    moves=json.loads((OUT/'move_plan.json').read_text(encoding='utf-8'))
    protected=json.loads((OUT/'protected_before.json').read_text(encoding='utf-8'))
    failures=[]
    for name,info in protected.items():
        p=BASE/name
        if not p.is_file():failures.append(name+': 누락');continue
        if 'sha256' in info:
            if sha(p)!=info['sha256']:failures.append(name+': 지문 변경')
        elif p.lstat().st_size!=info['size'] or p.lstat().st_mtime_ns!=info['mtime_ns']:
            # Markdown의 링크 수정은 허용하되 원문 ZIP 보존 여부를 별도 확인한다.
            if p.suffix!='.md':failures.append(name+': 크기/수정일 변경')
    archive=BASE/'archive/document_originals_20261104.zip'
    snapshots=json.loads((OUT/'archived_markdown_sha256.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(archive) as z:
        for name,expected in snapshots.items():
            if hashlib.sha256(z.read(name)).hexdigest()!=expected:failures.append(name+': 원문 보관 지문 불일치')
    before=json.loads((OUT/'broken_links_before.json').read_text(encoding='utf-8'))
    expected={(moves.get(r['source'],r['source']),str(BASE/moves.get(str(Path(r['target']).relative_to(BASE)),str(Path(r['target']).relative_to(BASE)))))
              for r in before if Path(r['target']).is_relative_to(BASE)} if hasattr(Path,'.is_relative_to') else set()
    # Python 3.9에서도 프로젝트 외부 링크를 안전하게 비교한다.
    expected=set()
    for r in before:
        target=r['target']
        try:rel=str(Path(target).relative_to(BASE));target=str(BASE/moves.get(rel,rel))
        except ValueError:pass
        expected.add((moves.get(r['source'],r['source']),target))
    after=broken_links();new_broken=[r for r in after if (r['source'],r['target']) not in expected]
    dump('link_validation.json',{'before_broken':before,'after_broken':after,'new_broken':new_broken})
    dump('preservation_check.json',{'protected_count':len(protected),'archived_original_count':len(snapshots),
         'moved_count':len(moves),'deleted_count':0,'failures':failures,'new_broken_links':len(new_broken)})
    if failures or new_broken:raise ValueError(json.dumps({'files':failures,'new_broken':new_broken},ensure_ascii=False))
    print('기존 파일 보존·원문 ZIP 지문·새 링크 오류 없음 확인. 기존 링크 오류:',len(after))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['inventory_before','inventory_after','plan','organize','verify'])
    action=parser.parse_args().action
    if action.startswith('inventory_'):inventory(action.split('_')[1])
    else:globals()[action]()
