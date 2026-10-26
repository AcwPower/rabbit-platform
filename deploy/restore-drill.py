"""Root-only isolated restore rehearsal; never imports into the live database."""
import gzip, subprocess, sys, re
from pathlib import Path
backup=Path(sys.argv[1]).resolve()
if not backup.is_relative_to('/var/backups/rabbit'): raise SystemExit('Use a local rabbit backup')
subprocess.run(['sha256sum','-c',str(backup/'SHA256SUMS')],check=True)
sql=gzip.decompress((backup/'database.sql.gz').read_bytes())
if re.search(rb'(?im)^\s*(USE\s|CREATE DATABASE)',sql): raise SystemExit('Dump must not select another database')
name='rabbit_restore_test'
def query(statement):return subprocess.run(['mysql','--batch','--skip-column-names'],input=statement,text=True,check=True,capture_output=True).stdout.strip()
if query(f"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME='{name}'"):
    raise SystemExit('Restore test database already exists; inspect it before retrying')
query(f'CREATE DATABASE {name} CHARACTER SET utf8mb4')
try:
    subprocess.run(['mysql',name],input=sql,check=True)
    count=query(f"SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='{name}'")
    revision=query(f'SELECT version_num FROM {name}.alembic_version')
    assert int(count)>=16 and revision
    print(f'Restore rehearsal passed: {count} tables, migration {revision}; live database untouched.')
finally:
    query(f'DROP DATABASE {name}')
