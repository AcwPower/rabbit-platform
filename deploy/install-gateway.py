"""Add /party/ routing on the existing gateway; preserve all timer routes."""
import argparse, hashlib, shutil, subprocess, datetime
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--expected-sha',required=True);p.add_argument('--snippet',required=True);p.add_argument('--certificate',required=True);args=p.parse_args()
config=Path('/etc/nginx/sites-enabled/mushroom-timer').resolve()
old=config.read_bytes()
if hashlib.sha256(old).hexdigest()!=args.expected_sha: raise SystemExit('Gateway config changed; inspect and retry with the newly reviewed hash.')
line='    include /etc/nginx/snippets/rabbit-platform.conf;'
text=old.decode()
if line in text: raise SystemExit('Route already installed; review existing config before updating.')
anchor='    include /etc/nginx/snippets/mushroom-pre.conf;'
if text.count(anchor)!=1: raise SystemExit('Expected HTTPS anchor missing or ambiguous')
backup=Path('/var/backups/rabbit-gateway')/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup.mkdir(parents=True,mode=0o700)
shutil.copy2(config,backup/'mushroom-timer.conf')
shutil.copy2(args.snippet,'/etc/nginx/snippets/rabbit-platform.conf')
shutil.copy2(args.certificate,'/etc/nginx/rabbit-backend.crt')
Path('/etc/nginx/rabbit-backend.crt').chmod(0o644)
try:
    config.write_text(text.replace(anchor,anchor+'\n'+line))
    subprocess.run(['nginx','-t'],check=True)
    subprocess.run(['systemctl','reload','nginx'],check=True)
except Exception:
    config.write_bytes(old)
    subprocess.run(['nginx','-t'],check=True)
    subprocess.run(['systemctl','reload','nginx'],check=True)
    raise
print('Gateway route installed; backup:',backup)
