"""Resolve VMT resources and publish verified individually-addressed ZIP records.

Records share immutable release bundles; HTTP Range fetches only one ZIP.
No credentials are stored in catalogs. Requires gh only when --publish is used.
"""
import argparse,hashlib,io,json,re,subprocess,zipfile,urllib.request,time
from pathlib import Path
from collections import Counter
from vtf_png import png

def digest(b):return hashlib.sha256(b).hexdigest()
SOURCE_ALIASES={
    'stickers/cluj2015/sig_ninjasinpyjamas.vtf':'stickers/cluj2015/ninjasinpyjamas.vtf',
    'stickers/cluj2015/sig_ninjasinpyjamas_normal.vtf':'stickers/cluj2015/ninjasinpyjamas_normal.vtf',
    **{f'stickers/sha2024/sig_{n}_glitter_mask.vtf':f'stickers/sha2024/sig_{n}_glitter_mas.vtf'
       for n in ('bodyy','ex3rcice','im','jdc','liazz','teses')}
}
def properties(text):
    text=re.sub(r'//[^\r\n]*','',text)
    tokens=re.findall(r'"([^"\r\n]*)"|([^\s{}"]+)|([{}])',text)
    t=[next(x for x in group if x) for group in tokens]
    return {t[i].lower():t[i+1] for i in range(len(t)-1) if t[i] not in ('{','}') and t[i+1] not in ('{','}')}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path);ap.add_argument('--out',type=Path,default=Path('delivery'))
    ap.add_argument('--publish',action='store_true');ap.add_argument('--repo',default='kennedyroxo-ai/Adesivos-csgo-cs2')
    ap.add_argument('--tag',default='packages-july-2026-v1');ap.add_argument('--limit',type=int,default=0)
    ap.add_argument('--discard-bundles',action='store_true',help='Local validation only: retain metadata, discard binary bundles')
    ap.add_argument('--material',action='append',default=[])
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    resources={p.relative_to(a.root).as_posix().lower():p for p in a.root.rglob('*') if p.is_file()}
    aliases={}
    def resolve(v,ext):
        p=v.lower().replace('\\','/').removeprefix('materials/').removeprefix('models/weapons/customization/')
        if not p.endswith(ext):p+=ext
        if p.startswith('/') or '..' in p.split('/'):raise ValueError('Unsafe material path')
        if p not in resources and p in SOURCE_ALIASES and SOURCE_ALIASES[p] in resources:
            # Curated filename repairs verified against the supplied archive.
            # Keep original VTF bytes and original filenames as well as the alias.
            aliases[p]=SOURCE_ALIASES[p];resources[p]=resources[aliases[p]]
        if p not in resources:raise ValueError('Missing resource '+p)
        return p
    def material(path,seen=None):
        seen=set() if seen is None else seen
        if path in seen:raise ValueError('Cyclic material include')
        seen.add(path);p=properties(resources[path].read_text(errors='replace'));deps={path}
        if 'include' in p:
            parent=resolve(p['include'],'.vmt');base,more=material(parent,seen);deps|=more;base.update(p);p=base
        for k,v in p.items():
            value=v.lower().replace('\\','/')
            if 'stickers/' in value and k!='include' and not value.startswith('['): deps.add(resolve(v,'.vtf'))
        return p,deps
    default=resources.get('stickers/default/holowarp_default.vtf')
    default_hash=digest(default.read_bytes()) if default else None
    entries=[];failures=[];bundles=[];buffer=bytearray();records=[];bundle_n=0
    if a.publish:subprocess.run(['gh','release','create',a.tag,'--repo',a.repo,'--title','Pacotes de adesivos julho 2026','--notes','Pacotes individuais em bundles com offsets, tamanhos e SHA-256. Catálogo publicado somente após concluir todos os uploads.'],check=True)
    def flush():
        nonlocal buffer,records,bundle_n
        if not buffer:return
        name=f'stickers-{bundle_n:04d}.bin';path=a.out/name;path.write_bytes(buffer)
        sha=digest(buffer)
        if a.publish:
            subprocess.run(['gh','release','upload',a.tag,str(path),'--repo',a.repo],check=True)
            path.unlink()
        elif a.discard_bundles:path.unlink()
        for record in records:
            record['url']=f'https://github.com/{a.repo}/releases/download/{a.tag}/{name}'
            record['bundle_size']=len(buffer)
        bundles.append({'name':name,'bytes':len(buffer),'sha256':sha,'records':len(records)})
        print(json.dumps({'bundle':name,'records':len(records),'total':len(entries)}),flush=True)
        bundle_n+=1;buffer=bytearray();records=[]
    mats=sorted(p for p in resources if p.endswith('.vmt'))
    if a.material:mats=[p for p in mats if p in a.material]
    for path in mats[:a.limit or len(mats)]:
        try:
            props,deps=material(path)
            base=resolve(props['$basetexture'],'.vtf');deps.add(base)
            tint=None
            if '$colortint' in props:
                values=[float(v) for v in re.findall(r'-?\d+(?:\.\d+)?',props['$colortint'])]
                if len(values)!=3:raise ValueError('Unsupported material color tint')
                tint=values
            image,info=png(resources[base].read_bytes(),max_edge=512,tint=tint)
            if info['frames']>1:raise ValueError('Animated base requires animation support')
            mask=props.get('$holomask');spectrum=props.get('$holospectrum')
            extra={};holo=False;effect='static'
            if mask and spectrum:
                mask=resolve(mask,'.vtf');spectrum=resolve(spectrum,'.vtf');deps|={mask,spectrum}
                extra['mask.png']=png(resources[mask].read_bytes(),max_edge=512)[0]
                extra['spectrum.png']=png(resources[spectrum].read_bytes())[0]
                extra['spectrum.vtf']=resources[spectrum].read_bytes()
                holo=True
                effect='holo'
            elif props.get('$decalstyle') not in (None,'0','1'):effect='material_effect_static'
            deps|={aliases[d] for d in list(deps) if d in aliases}
            content={'image.png':image,**extra}
            total=sum(resources[d].stat().st_size for d in deps)+sum(map(len,content.values()))
            if total>48*1024*1024 or len(deps)+len(content)>120:raise ValueError('Package exceeds client limits')
            meta={'id':path[9:-4],'material':path,'properties':props,'textures':sorted(deps),'effect':effect,'image_info':info,
                  'filename_aliases':{d:aliases[d] for d in deps if d in aliases}}
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
                for d in sorted(deps):z.writestr(d,resources[d].read_bytes())
                for n,data in content.items():z.writestr(n,data)
                z.writestr('package.json',json.dumps(meta,separators=(',',':')))
            data=out.getvalue()
            if len(data)>32*1024*1024:raise ValueError('Compressed package exceeds client limits')
            if buffer and len(buffer)+len(data)>64*1024*1024:flush()
            stem=Path(path).stem
            item={'id':path[9:-4],'name':stem.replace('_',' '),'aliases':path[9:-4].replace('/',' '),
                  'collection':str(Path(path).parent)[9:],'effect':effect,'holo':holo,'sha256':digest(data),
                  'size':len(data),'offset':len(buffer),'url':'','bundle_size':0,'image':'image.png',
                  'mask':'mask.png' if holo else None,'spectrum':'spectrum.png' if holo else None,
                  'spectrum_vtf':'spectrum.vtf' if holo else None,
                  'spectrum_sha256':digest(extra['spectrum.vtf']) if holo else None,'material':path}
            buffer.extend(data);records.append(item);entries.append(item)
        except Exception as e:failures.append({'material':path,'reason':str(e)})
    flush()
    report={'schema':1,'source_sha256':'2381ac45df58dcd5792d994ee40e18861893d3dbde2c4e2dd4f5ba0383cb70aa',
            'materials':len(mats[:a.limit or len(mats)]),'ready':len(entries),'failed':len(failures),'effects':dict(Counter(x['effect'] for x in entries)),
            'bundles':bundles,'failures':failures}
    catalog={'schema':1,'version':a.tag,'items':entries}
    (a.out/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,separators=(',',':'))+'\n')
    (a.out/'package-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    assert len({e['id'] for e in entries})==len(entries)
    assert len(entries)+len(failures)==report['materials']
    if not entries:raise RuntimeError('No downloadable stickers generated')
    if a.publish:
        # Verify the exact transport used by Android before advertising the catalog.
        for item in [entries[0],entries[-1]]:
            for attempt in range(3):
                try:
                    req=urllib.request.Request(item['url'],headers={'Range':f"bytes={item['offset']}-{item['offset']+item['size']-1}",'Accept-Encoding':'identity'})
                    with urllib.request.urlopen(req,timeout=60) as response:
                        expected=f"bytes {item['offset']}-{item['offset']+item['size']-1}/{item['bundle_size']}"
                        if response.status!=206 or response.headers.get('Content-Range')!=expected:raise ValueError('Server did not honor package byte range')
                        downloaded=response.read(item['size']+1)
                    if len(downloaded)!=item['size'] or digest(downloaded)!=item['sha256']:raise ValueError('Published package checksum mismatch')
                    break
                except Exception:
                    if attempt==2:raise
                    time.sleep(3)
        subprocess.run(['gh','release','upload',a.tag,str(a.out/'catalog.json'),str(a.out/'package-report.json'),'--repo',a.repo],check=True)
    print(json.dumps({k:v for k,v in report.items() if k not in ('bundles','failures')}),flush=True)
if __name__=='__main__':main()
