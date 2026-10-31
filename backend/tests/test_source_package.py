"""Source delivery boundaries, using disposable Git repositories only."""
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

import pytest


@pytest.fixture
def package(tmp_path,monkeypatch):
    path=Path(__file__).resolve().parents[2]/'scripts/package.py'
    spec=importlib.util.spec_from_file_location('source_package_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    root=tmp_path/'repo';root.mkdir()
    def git(*args):
        return subprocess.run(['git',*args],cwd=root,check=True,capture_output=True)
    git('init','-q');git('config','user.name','Offline test');git('config','user.email','offline@example.invalid')
    (root/'README.md').write_text('Committed source\n',encoding='utf-8')
    (root/'.gitignore').write_text('var/\n.env*\n',encoding='utf-8')
    git('add','README.md','.gitignore');git('commit','-qm','Offline fixture')
    monkeypatch.setattr(module,'ROOT',root)
    return module,root,git


def test_archive_excludes_local_private_files_and_keeps_complete_commit_manifest(package):
    module,root,git=package
    (root/'private-notes.txt').write_text('DO-NOT-SHIP',encoding='utf-8')
    (root/'.env.llm.local').write_text('LOCAL-ONLY',encoding='utf-8')
    (root/'var').mkdir();(root/'var'/'private.sqlite3').write_bytes(b'LOCAL-DATABASE')
    target=root/'var'/'release.zip'
    module.create(target)
    report=module.verify(target)
    assert report['commit']==git('rev-parse','HEAD').stdout.decode().strip()
    with zipfile.ZipFile(target) as archive:
        assert set(archive.namelist())=={'campmate_app/','campmate_app/.gitignore',
            'campmate_app/README.md','campmate_app/PACKAGE_MANIFEST.json'}
        manifest=json.loads(archive.read('campmate_app/PACKAGE_MANIFEST.json'))
        assert manifest['recommended_launcher']=='scripts/sydney.py'
        assert b'DO-NOT-SHIP' not in b''.join(archive.read(name) for name in archive.namelist())
    assert target.with_suffix('.zip.sha256').read_text().startswith(report['sha256'])
    with pytest.raises(ValueError,match='already exists'):module.create(target)
    (root/'README.md').write_text('Unsaved release source',encoding='utf-8')
    with pytest.raises(ValueError,match='tracked source changes'):module.create(root/'var'/'next.zip')


@pytest.mark.parametrize('name',['.env','.env.llm.local','var/run.json','node_modules/a.js',
    'campmate.sqlite3','campmate.sqlite3-wal','campmate.sqlite3-shm','test.db-journal',
    'secret.SQLITE','../outside','link\\file'])
def test_runtime_and_unsafe_paths_are_never_allowed_even_if_committed(package,name):
    module,_,_=package
    with pytest.raises(ValueError):module.safe_path('campmate_app/'+name)


def test_verify_detects_tampering_and_committed_secret_file_blocks_archive(package):
    module,root,git=package
    target=root/'var'/'source.zip';module.create(target)
    with zipfile.ZipFile(target,'a') as archive:archive.writestr('campmate_app/injected.txt','Not in manifest')
    with pytest.raises(ValueError,match='file list differs'):module.verify(target)
    (root/'.env.llm.local').write_text('NOT-A-REAL-KEY',encoding='utf-8')
    git('add','-f','.env.llm.local');git('commit','-qm','Forbidden fixture')
    with pytest.raises(ValueError,match='Runtime/private'):module.create(root/'var'/'forbidden.zip')
