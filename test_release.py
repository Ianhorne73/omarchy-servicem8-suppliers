"""Ensure release packaging cannot pick up credentials or follow symlinks."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
import json

FILES={'manifest.json','BarWidget.qml','suppliers.py','README.md','LICENSE','i18n/en.json'}
class ReleaseTests(unittest.TestCase):
    def fixture(self,path):
        root=Path(__file__).parent
        for name in FILES | {'build_release.py'}:
            target=path/name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(root/name,target)
    def test_release_uses_allowlist_and_excludes_private_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);self.fixture(path)
            (path/'credentials.json').write_text('{"api_key":"synthetic-secret"}')
            result=subprocess.run([sys.executable,str(path/'build_release.py')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            with zipfile.ZipFile(next((path/'dist').glob('*.zip'))) as archive:
                self.assertEqual(set(archive.namelist()),FILES)
                self.assertFalse(any(b'synthetic-secret' in archive.read(n) for n in archive.namelist()))
    def test_release_refuses_symlinked_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);self.fixture(path)
            (path/'README.md').unlink()
            (path/'README.md').symlink_to(path/'LICENSE')
            result=subprocess.run([sys.executable,str(path/'build_release.py')],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('symlinked release file',result.stderr)
    def test_release_refuses_unsafe_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);self.fixture(path)
            manifest=json.loads((path/'manifest.json').read_text());manifest['version']='../unsafe'
            (path/'manifest.json').write_text(json.dumps(manifest))
            result=subprocess.run([sys.executable,str(path/'build_release.py')],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)

if __name__=='__main__':unittest.main()
