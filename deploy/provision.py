"""Run as root on the NEW application host. No secrets are printed."""
import os, secrets, base64, subprocess
from pathlib import Path

def run(*args,**kwargs): return subprocess.run(args,check=True,**kwargs)
for user in ('rabbit','rabbitocr'):
    if subprocess.run(['id',user],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
        run('useradd','--system','--home',f'/var/lib/{user}','--create-home','--shell','/usr/sbin/nologin',user)
run('install','-d','-m','750','-o','root','-g','rabbit','/etc/rabbit')
run('install','-d','-m','750','-o','rabbit','-g','rabbit','/var/lib/rabbit')
run('install','-d','-m','750','-o','root','-g','rabbit','/var/backups/rabbit')
run('install','-d','-m','755','/opt/rabbit-platform/releases')
for name,env_path,mode in [('rabbit_platform','/etc/rabbit/app.env','prod'),('rabbit_test','/home/ubuntu/rabbit-test.env','test')]:
    path=Path(env_path)
    if path.exists(): continue
    password=secrets.token_hex(32)
    dbuser='rabbit_app' if mode=='prod' else 'rabbit_test'
    sql=f"CREATE DATABASE IF NOT EXISTS {name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; CREATE USER IF NOT EXISTS '{dbuser}'@'127.0.0.1' IDENTIFIED BY '{password}'; GRANT ALL PRIVILEGES ON {name}.* TO '{dbuser}'@'127.0.0.1';"
    run('mysql',input=sql,text=True,stdout=subprocess.DEVNULL)
    contents=f'DATABASE_URL=mysql+pymysql://{dbuser}:{password}@127.0.0.1/{name}?charset=utf8mb4\nSECRET_KEY={secrets.token_hex(32)}\nCONTACT_KEY={base64.urlsafe_b64encode(os.urandom(32)).decode()}\nPUBLIC_ORIGIN={"https://mushroom-king-timer.online" if mode=="prod" else "http://testserver"}\nCOOKIE_SECURE={"true" if mode=="prod" else "false"}\nOCR_URL=http://127.0.0.1:8102\nOCR_SECRET={secrets.token_hex(32)}\n'
    path.write_text(contents);path.chmod(0o640 if mode=='prod' else 0o600)
    run('chown','root:rabbit' if mode=='prod' else 'ubuntu:ubuntu',str(path))
prod=dict(line.split('=',1) for line in Path('/etc/rabbit/app.env').read_text().splitlines() if '=' in line)
ocr=Path('/etc/rabbit/ocr.env');ocr.write_text('OCR_SECRET='+prod['OCR_SECRET']+'\n');ocr.chmod(0o640);run('chown','root:rabbitocr',str(ocr))
print('Isolated databases, service users and protected environment files prepared.')
