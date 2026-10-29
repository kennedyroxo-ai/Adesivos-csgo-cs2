"""Extract the verified sticker-only archive after validating its member paths."""
from pathlib import Path
import hashlib,py7zr

source=Path('stickers.7z')
with source.open('rb') as f:
    assert hashlib.file_digest(f,'sha256').hexdigest()=='2381ac45df58dcd5792d994ee40e18861893d3dbde2c4e2dd4f5ba0383cb70aa'
with py7zr.SevenZipFile(source) as archive:
    for entry in archive.list():
        name=entry.filename.replace('\\','/')
        assert name=='stickers' or (name.startswith('stickers/') and not name.startswith('/') and '..' not in name.split('/'))
        if not entry.is_directory:assert name.lower().endswith(('.vmt','.vtf'))
    archive.extractall('originals')
