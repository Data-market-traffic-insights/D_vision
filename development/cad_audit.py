"""LibreDWG가 만든 변환본의 좌표계 근거를 감사한다. 원본 DWG/운영 CSV는 수정하지 않는다."""
from collections import Counter
import csv
import hashlib
import gzip
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent/'results/cad_review_20261103'
CRS_PATTERN=re.compile(r'EPSG|WGS\s*84|GRS\s*80|BESSEL|KOREA2000|KOREA\.\w+|PROJCS|GEOGCS|PROJCRS|GEODCRS|좌표계|중부원점|세계측지|측지계|Korean1985',re.I)
STATION_PATTERN=re.compile(r'정거장|승강장|플랫폼|\b(?:20[1-9]|21\d|22\d|23\d|24[0-5])\s*정')
HEADER_KEYS=['INSUNITS','LUNITS','AUNITS','INSBASE','EXTMIN','EXTMAX','UCSORG','UCSXDIR','UCSYDIR','UCSNAME','LATITUDE','LONGITUDE','NORTHDIRECTION','PROJECTNAME']


def strings(o):
    for key in ['name','text_value','text','xref_pname','coordinate_system_definition','description','table_name']:
        if isinstance(o.get(key),str):yield key,o[key]
    for e in o.get('eed',[]):
        if isinstance(e.get('value'),str):yield 'eed',e['value']
    for code,value,*_ in o.get('xdata',[]):
        if code in [1,2,3,1000] and isinstance(value,str):yield 'xdata',value


def inspect_json(path):
    stream=path.open() if path.exists() else gzip.open(str(path)+'.gz','rt')
    with stream:
        data=json.load(stream)
    objects=data['OBJECTS'];header=data['HEADER']
    lookup={o['handle'][-1]:o for o in objects if 'handle' in o}
    layers={h:o.get('name','') for h,o in lookup.items() if o.get('object')=='LAYER'}
    blocks={h:o.get('name','') for h,o in lookup.items() if o.get('object')=='BLOCK_HEADER'}
    texts=[];references=[];station_blocks=[];crs=[];types=Counter();dict_keys=set();unsupported=Counter()
    for o in objects:
        typ=o.get('entity',o.get('object','UNKNOWN'));types[typ]+=1
        if typ in ['UNKNOWN_OBJ','PROXY_OBJECT','PROXY_ENTITY']:unsupported[typ]+=1
        handle=o.get('handle',[None])[-1]
        for field,text in strings(o):
            if CRS_PATTERN.search(text):crs.append({'handle':handle,'type':typ,'field':field,'text':text[:2000]})
        if typ in ['TEXT','MTEXT','ATTRIB','ATTDEF']:
            text=o.get('text_value',o.get('text',''))
            texts.append({'handle':handle,'type':typ,'text':text,'point':o.get('ins_pt',o.get('insertion_pt')),'layer':layers.get(o.get('layer',[None])[-1],''),'owner':o.get('ownerhandle',[None])[-1]})
        if typ=='INSERT':
            name=blocks.get(o.get('block_header',[None])[-1],'')
            if STATION_PATTERN.search(name):station_blocks.append({'handle':handle,'block_name':name,'insertion':o.get('ins_pt'),'scale':o.get('scale'),'rotation':o.get('rotation'),'layer':layers.get(o.get('layer',[None])[-1],'')})
        if typ=='BLOCK_HEADER' and (o.get('blkisxref') or o.get('xref_pname')):
            references.append({'handle':handle,'name':o.get('name'),'path':o.get('xref_pname'),'base':o.get('base_pt')})
        if typ=='DICTIONARY':dict_keys.update(o.get('items',{}))
    ROOT.joinpath('decoded',path.stem+'.texts.json').write_text(json.dumps(texts,ensure_ascii=False,indent=2))
    return {'reader':'LibreDWG JSON','header':{k:header.get(k) for k in HEADER_KEYS},'object_count':len(objects),
            'entity_types':dict(types),'unsupported':dict(unsupported),'geodata_count':types['GEODATA'],
            'crs_declarations':crs,'external_references':references,'named_dictionary_keys':sorted(dict_keys),
            'station_blocks':station_blocks,'station_texts':[t for t in texts if STATION_PATTERN.search(t['text'])],
            'station_layers':[name for name in layers.values() if STATION_PATTERN.search(name)]}


def dxf_records(path):
    """ASCII DXF를 순서대로 읽어 전체 도형을 메모리에 쌓지 않는다."""
    stream=(path.open(encoding='utf-8',errors='replace') if path.exists()
            else gzip.open(str(path)+'.gz','rt',encoding='utf-8',errors='replace'))
    with stream:
        typ=None;tags=[]
        while True:
            a=stream.readline();b=stream.readline()
            if not a or not b:break
            try:code=int(a.strip())
            except ValueError:continue
            value=b.rstrip('\r\n')
            if code==0:
                if typ is not None:yield typ,tags
                typ=value;tags=[]
            else:tags.append((code,value))
        if typ is not None:yield typ,tags


def unescape_dxf(text):
    return re.sub(r'\\U\+([0-9a-fA-F]{4})',lambda m:chr(int(m[1],16)),text)


def inspect_dxf(path):
    header={};types=Counter();texts=[];crs=[];references=[];station_blocks=[];dict_keys=set();section=''
    for typ,tags in dxf_records(path):
        if typ=='SECTION':
            section=next((value for code,value in tags if code==2),'')
            if section=='HEADER':
                key=None;values=[]
                for code,value in tags:
                    if code==9:
                        if key:header[key]=values
                        key=value.lstrip('$');values=[]
                    elif key:values.append((code,value))
                if key:header[key]=values
            continue
        if typ=='ENDSEC':section='';continue
        if section not in ['ENTITIES','BLOCKS','OBJECTS','TABLES']:continue
        types[typ]+=1;by={}
        for code,value in tags:by.setdefault(code,[]).append(value)
        handle=by.get(5,[''])[0]
        for code,raw in tags:
            if code in [1,2,3,1000]:
                text=unescape_dxf(raw)
                if CRS_PATTERN.search(text):crs.append({'handle':handle,'type':typ,'field':str(code),'text':text[:2000]})
        if typ in ['TEXT','MTEXT','ATTRIB','ATTDEF']:
            text=unescape_dxf(''.join(by.get(3,[]))+''.join(by.get(1,[])))
            point=[by.get(code,[''])[0] for code in [10,20,30]]
            texts.append({'handle':handle,'type':typ,'text':text,'point':point,'layer':by.get(8,[''])[0]})
        if typ=='INSERT':
            name=unescape_dxf(by.get(2,[''])[0])
            if STATION_PATTERN.search(name):station_blocks.append({'handle':handle,'block_name':name,'insertion':[by.get(c,[''])[0] for c in [10,20,30]],'scale':[by.get(c,['1'])[0] for c in [41,42,43]],'rotation_degrees':by.get(50,['0'])[0]})
        if typ=='BLOCK_RECORD' and by.get(1):references.append({'handle':handle,'path':by[1]})
        if typ=='DICTIONARY':dict_keys.update(unescape_dxf(v) for v in by.get(3,[]))
    def value(key):
        items=header.get(key,[])
        if not items:return None
        if any(c==10 for c,_ in items):return [float(next((v for c,v in items if c==code),'0')) for code in [10,20,30]]
        raw=items[0][1]
        try:return float(raw) if '.'in raw else int(raw)
        except ValueError:return raw
    ROOT.joinpath('decoded',path.stem+'.texts.json').write_text(json.dumps(texts,ensure_ascii=False,indent=2))
    return {'reader':'LibreDWG DXF (JSON serialization failed; geometry not repaired)',
            'header':{k:value(k) for k in HEADER_KEYS},'object_count':sum(types.values()),'entity_types':dict(types),
            'unsupported':{k:v for k,v in types.items() if 'PROXY' in k or 'UNKNOWN' in k},'geodata_count':types['GEODATA'],
            'crs_declarations':crs,'external_references':references,'named_dictionary_keys':sorted(dict_keys),
            'station_blocks':station_blocks,'station_texts':[t for t in texts if STATION_PATTERN.search(t['text'])]}


def main():
    manifest=json.loads((ROOT/'archive_manifest.json').read_text());rows=[]
    for idx,f in enumerate(manifest['files'],1):
        path=ROOT/'decoded'/f'{idx:02d}.json'
        try:audit=inspect_json(path)
        except json.JSONDecodeError as error:
            audit=inspect_dxf(path.with_suffix('.dxf'));audit['json_decode_error']=str(error)
        audit['name']=f['name'];audit['sha256']=f['sha256'];audit['coordinate_system_confirmed']=False
        (ROOT/f'audit_{idx:02d}.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
        rows.append({'file':f['name'],'units_code':audit['header'].get('INSUNITS'),'units_label':'mm' if audit['header'].get('INSUNITS')==4 else '미확인',
                     'INSBASE':json.dumps(audit['header'].get('INSBASE')),'UCSORG':json.dumps(audit['header'].get('UCSORG')),
                     'EXTMIN':json.dumps(audit['header'].get('EXTMIN')),'EXTMAX':json.dumps(audit['header'].get('EXTMAX')),
                     'geodata_count':audit['geodata_count'],'crs_declaration_matches':len(audit['crs_declarations']),
                     'station_text_count':len(audit['station_texts']),'station_block_insert_count':len(audit['station_blocks']),
                     'coordinate_system':'미확인','sha256':f['sha256'],'reader':audit['reader']})
        print(idx,f['name'],'station texts',len(audit['station_texts']),'CRS matches',len(audit['crs_declarations']),flush=True)
    with (ROOT/'dwg_audit_summary.csv').open('w',encoding='utf-8-sig',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


if __name__=='__main__':main()
