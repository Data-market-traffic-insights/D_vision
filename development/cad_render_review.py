"""4공구 소형 배치도의 선형을 검토용으로 렌더링한다. 지리좌표를 산출하지 않는다."""
import json
import os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/dvision-cad-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib import font_manager
import numpy as np

BASE=Path(__file__).resolve().parent
ROOT=BASE/'results/cad_review_20261103'
MAP={4:203,5:204,6:207,7:206,8:202,9:210,10:208,11:205,12:211,13:209}


def render(index,station_id):
    data=json.loads((ROOT/f'decoded/{index:02d}.json').read_text());objs=data['OBJECTS']
    by={o['handle'][-1]:o for o in objs if 'handle' in o}
    root=by[data['HEADER']['BLOCK_RECORD_MSPACE'][-1]]
    segments=[]
    def apply(points,matrix):
        pts=np.array(points,dtype=float)[:,:2]
        return np.column_stack([pts[:,0]*matrix[0,0]+pts[:,1]*matrix[0,1]+matrix[0,2],
                                pts[:,0]*matrix[1,0]+pts[:,1]*matrix[1,1]+matrix[1,2]])
    def entity(o,matrix,depth=0):
        if depth>8:return
        typ=o.get('entity');points=None
        if typ=='LINE':points=[o['start'],o['end']]
        elif typ=='LWPOLYLINE':
            points=o.get('points',[])
            if o.get('flag',0)&512 and points:points=points+[points[0]]
        elif typ in ['CIRCLE','ARC']:
            c=o.get('center');r=o.get('radius',0)
            if c is not None:
                angles=np.linspace(o.get('start_angle',0),o.get('end_angle',2*np.pi),48)
                points=np.column_stack([c[0]+r*np.cos(angles),c[1]+r*np.sin(angles)])
        elif typ=='INSERT':
            block=by.get(o.get('block_header',[None])[-1])
            if not block:return
            scale=o.get('scale',[1,1,1]);rotation=o.get('rotation',0);c,s=np.cos(rotation),np.sin(rotation)
            m=np.array([[c*scale[0],-s*scale[1],o['ins_pt'][0]],[s*scale[0],c*scale[1],o['ins_pt'][1]],[0,0,1.]])
            base=block.get('base_pt',[0,0,0]);m[:2,2]-=m[:2,0]*base[0]+m[:2,1]*base[1]
            for ref in block.get('entities',[]):
                child=by.get(ref[-1])
                if child:entity(child,np.einsum('ij,jk->ik',matrix,m,optimize=False),depth+1)
        if points is not None and len(points)>=2:
            pts=apply(points,matrix)[:,:2]
            if np.isfinite(pts).all():segments.append(pts)
    for ref in root.get('entities',[]):
        o=by.get(ref[-1])
        if o:entity(o,np.eye(3))
    fig,axes=plt.subplots(1,2,figsize=(16,7))
    ax=axes[0];ax.add_collection(LineCollection(segments,colors='#25424d',linewidths=.35))
    bounds=np.array([data['HEADER']['EXTMIN'][:2],data['HEADER']['EXTMAX'][:2]])
    ax.set_xlim(bounds[0,0],bounds[1,0]);ax.set_ylim(bounds[0,1],bounds[1,1]);ax.set_aspect('equal')
    ax.set_title(f'CAD {station_id} | drawing XY only (not geographic)')
    ax.set_xlabel('Drawing X (INSUNITS=4)');ax.set_ylabel('Drawing Y')
    image=plt.imread(BASE/f'data/tram_reference/station_{station_id}.png')
    axes[1].imshow(image);axes[1].axis('off');axes[1].set_title(f'Official reference PDF | page {station_id-198}')
    fig.suptitle('Partial 2D geometry preview: CRS unconfirmed, no WGS84 conversion',fontsize=14)
    fig.tight_layout();fig.savefig(ROOT/f'cad_pdf_review_{station_id}.png',dpi=140);plt.close(fig)
    return len(segments)


if __name__=='__main__':
    rows=[]
    for index,station_id in MAP.items():
        count=render(index,station_id);rows.append({'index':index,'station_id':station_id,'rendered_paths':count,'geographic_validation':False})
    (ROOT/'visual_review_index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    print('검토 이미지 10개 생성. 지리 좌표 검증 결과가 아님.')
