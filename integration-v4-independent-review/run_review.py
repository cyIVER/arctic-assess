"""Reviewer-owned adapter: exact frozen source, outputs only in own directory."""
from pathlib import Path
import os,sys,tempfile
SOURCE=Path('/home/iveri/work/vindler-e2.SftLYa2R/continuation/coordination-20261119/integration-repair-v4')
OWN=Path(__file__).resolve().parent
scratch=tempfile.mkdtemp(prefix='iv4r-',dir='/home/iveri/.hermes/cache/scratch')
os.environ['TMPDIR']=scratch
tempfile.tempdir=scratch
(OWN/'scratch-location.txt').write_text(scratch+'\n')
(OWN/'evidence').mkdir(mode=0o700,exist_ok=True)
text=(SOURCE/'run_tests.py').read_text()
text=text.replace('ROOT=Path(__file__).resolve().parent','ROOT=SOURCE')
text=text.replace('fixture_migration.install(ROOT)','fixture_migration.install(OWN)')
text=text.replace("(ROOT/'evidence'/", "(OWN/'evidence'/")
exec(compile(text,str(SOURCE/'run_tests.py'),'exec'),globals())
