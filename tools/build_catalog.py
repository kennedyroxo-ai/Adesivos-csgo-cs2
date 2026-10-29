import csv, json, re
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'source-index.txt'
files = []
for line in source.read_text().splitlines():
    m = re.fullmatch(r'\s*(\d+)\s+(stickers/[^\r\n]+)', line)
    if not m:
        raise ValueError(line)
    size, path = m.groups()
    files.append({'path': path, 'bytes': int(size)})
assert len({f['path'] for f in files}) == len(files)
groups = defaultdict(list)
for f in files:
    groups[str(Path(f['path']).parent)].append(f)
catalog = []
def effect(name):
    for key in ('holo', 'foil', 'gold', 'glitter', 'lenticular'):
        if re.search(r'(^|_)'+key+r'($|_)', name):
            return key
    return 'nao_identificado'
for folder, resources in sorted(groups.items()):
    key = folder.removeprefix('stickers/').replace('/', '__')
    entries = []
    by_path = {x['path']: x for x in resources}
    for f in resources:
        if not f['path'].endswith('.vmt'):
            continue
        stem = Path(f['path']).stem
        # Same-basename VTF is only a candidate, not a parsed VMT dependency.
        candidate = f['path'][:-4]+'.vtf'
        entry = {'id': f['path'][9:-4], 'technical_name': stem,
                 'search_name': stem.replace('_', ' '), 'collection': folder[9:],
                 'material': f['path'], 'material_bytes': f['bytes'],
                 'effect_hint': effect(stem), 'effect_verified': False,
                 'same_name_texture': candidate if candidate in by_path else None,
                 'download_ready': False, 'package_url': None}
        entries.append(entry)
    catalog.extend(entries)
    out = ROOT / 'collections' / key
    out.mkdir(parents=True, exist_ok=True)
    (out/'catalog.json').write_text(json.dumps({'collection': folder[9:], 'entries': entries, 'resources': resources},ensure_ascii=False,separators=(',', ':'))+'\n')
    lines = [f'# {folder[9:]}', '', f'{len(entries)} materiais candidatos a adesivo; {len(resources)} arquivos.', '',
             'Nomes técnicos do pacote. Efeito indicado pelo nome, ainda não confirmado pela leitura do VMT. Textura de mesmo nome é candidata; referências reais exigem leitura do material.', '',
             '| Nome técnico | Tipo sugerido | Material | Textura de mesmo nome | Bytes VMT |', '|---|---|---|---|---:|']
    for e in entries:
        lines.append(f"| {e['technical_name']} | {e['effect_hint']} | {Path(e['material']).name} | {Path(e['same_name_texture']).name if e['same_name_texture'] else 'referência a resolver'} | {e['material_bytes']} |")
    (out/'LISTA.md').write_text('\n'.join(lines)+'\n')
summary = {'source_files': len(files), 'material_entries': len(catalog), 'texture_files': sum(f['path'].endswith('.vtf') for f in files), 'collections':len(groups), 'uncompressed_bytes':sum(f['bytes'] for f in files), 'effect_hints':dict(Counter(e['effect_hint'] for e in catalog)), 'download_ready':0, 'scope':'Inventário do pacote fornecido; não é catálogo completo oficial nem lista de nomes comerciais.'}
(ROOT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
lines = ['# Catálogo de adesivos CS:GO / CS2', '', 'Inventário organizado do pacote stickers_july_2026.7z fornecido pelo usuário.', '',
         f"**{len(catalog):,} materiais VMT**, **{summary['texture_files']:,} texturas VTF**, **{len(groups)} pastas**; total **{len(files):,} arquivos**.", '',
         'Os materiais são candidatos a adesivos: não representam necessariamente itens comerciais únicos. Nomes são técnicos; tipos são inferidos pelo nome. Não há confirmação de procedência byte a byte com o jogo nem separação comprovada entre CS:GO e CS2.', '',
         'Este commit organiza o índice. Os binários permanecem no pacote original; download_ready=false evita oferecer pacotes individuais inexistentes. É necessário extrair e ler cada VMT para resolver texturas, máscaras e espectros compartilhados antes de publicar downloads. O Dignitas já testado no SkinMaker é independente deste inventário.', '',
         '## Lista por coleção', '', '| Pasta | Materiais | Arquivos | Lista detalhada | Dados |', '|---|---:|---:|---|---|']
for folder, resources in sorted(groups.items()):
    key=folder[9:].replace('/', '__')
    n=sum(f['path'].endswith('.vmt') for f in resources)
    lines.append(f'| {folder[9:]} | {n} | {len(resources)} | [Lista](collections/{key}/LISTA.md) | [JSON](collections/{key}/catalog.json) |')
lines += ['', '## Reprodução', '', '`python3 tools/build_catalog.py` reconstrói as listas a partir de source-index.txt. Usa apenas Python padrão.', '', '## Integridade da fonte', '', 'Arquivo original: 2404673923 bytes. SHA-256: `2381ac45df58dcd5792d994ee40e18861893d3dbde2c4e2dd4f5ba0383cb70aa` (registrado na release de origem). Índice preservado em source-index.txt.']
(ROOT/'README.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary,ensure_ascii=False))
