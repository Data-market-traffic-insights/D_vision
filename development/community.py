"""실제 후기와 분리된 시연용 가상 게시글. 쓰기·회원가입 기능은 없다."""
from pathlib import Path
import json
import pandas as pd

BASE_DIR=Path(__file__).resolve().parent
DEMO_NOTICE='모든 게시글은 시연용 가상 콘텐츠입니다. 실제 창업자의 경험·후기나 검증된 지역 정보가 아닙니다.'
POST_TYPES=['창업 성공 경험','창업 실패 경험','재창업 경험','창업 준비 질문','창업 운영 노하우']


def load_examples(legal_regions,path=None):
    path=Path(path) if path else BASE_DIR/'data/community_examples.json'
    posts=json.loads(path.read_text(encoding='utf-8'))
    df=pd.DataFrame(posts)
    required=['id','title','region','region_basis','region_code','industry','post_type','nickname','created_at','body','is_demo']
    if not set(required).issubset(df) or not 10<=len(df)<=15:
        raise ValueError('시연 게시글은 필수 항목을 갖춘 10~15개여야 합니다.')
    if not df.id.is_unique or not df.is_demo.eq(True).all() or not df.region_basis.eq('법정동').all():
        raise ValueError('시연 표시 또는 게시글 키·지역 기준을 확인하세요.')
    if not df.body.str.startswith('[시연용 가상 콘텐츠]').all() or not df.post_type.isin(POST_TYPES).all():
        raise ValueError('게시글의 시연 표시나 유형이 올바르지 않습니다.')
    if pd.to_datetime(df.created_at,errors='coerce').isna().any():
        raise ValueError('게시글 예시 일자가 올바르지 않습니다.')
    lookup=legal_regions.set_index('법정동코드')['법정동명']
    if not df.region_code.map(lookup).eq(df.region).all():
        raise ValueError('게시글 법정동코드와 실제 데이터의 법정동명이 다릅니다.')
    return df


def filter_examples(posts,region='전체',industry='전체',post_type='전체',query=''):
    result=posts.copy()
    for column,value in [('region',region),('industry',industry),('post_type',post_type)]:
        if value!='전체': result=result.loc[result[column].eq(value)]
    if query.strip():
        text=result[['title','body','nickname']].agg(' '.join,axis=1)
        result=result.loc[text.str.contains(query.strip(),case=False,regex=False)]
    return result.sort_values(['created_at','id'],ascending=False)
