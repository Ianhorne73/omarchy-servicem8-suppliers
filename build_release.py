"""Allowlisted release: never package local connection/cache data."""
import json
import re
from pathlib import Path
import zipfile
root=Path(__file__).resolve().parent
version=json.loads((root/'manifest.json').read_text())['version']
if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?', version):
    raise ValueError('Invalid release version')
(root/'dist').mkdir(exist_ok=True)
out=root/'dist'/f'servicem8-suppliers-{version}.zip'
files=['manifest.json','BarWidget.qml','suppliers.py','README.md','LICENSE','i18n/en.json']
for name in files:
    candidate = root/name
    parts = Path(name).parts
    if not candidate.is_file() or any((root/Path(*parts[:i])).is_symlink() for i in range(1,len(parts)+1)):
        raise ValueError('Missing or symlinked release file: ' + name)
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
    for name in files:
        item=zipfile.ZipInfo(name, (2026,1,1,0,0,0)); item.external_attr=0o100644 << 16
        archive.writestr(item,(root/name).read_bytes(),compress_type=zipfile.ZIP_DEFLATED)
print(out)
