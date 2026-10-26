"""Local administrator bootstrap. Run using the protected application environment."""
import argparse, secrets, getpass
from pathlib import Path
from sqlalchemy import select
from .db import Session
from .models import User, Audit
from .security import hash_password

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['bootstrap','password','promote'])
    parser.add_argument('--username',default='admin');args=parser.parse_args()
    with Session.begin() as db:
        user=db.scalar(select(User).where(User.username==args.username))
        if args.action=='bootstrap':
            if user: print('Administrator already exists; unchanged.'); return
            password=secrets.token_urlsafe(22)
            db.add(User(username=args.username,password_hash=hash_password(password),is_admin=True))
            path=Path('/etc/rabbit/admin-initial.txt');path.write_text(f'URL: https://mushroom-king-timer.online/party/\nUsername: {args.username}\nPassword: {password}\n');path.chmod(0o600)
            print('Administrator initialized; credentials are in /etc/rabbit/admin-initial.txt (root-only).')
        elif args.action=='password':
            if not user: raise SystemExit('User does not exist')
            password=getpass.getpass('New password (10+ characters): ')
            if len(password)<10: raise SystemExit('Password too short')
            user.password_hash=hash_password(password)
        else:
            if not user: raise SystemExit('Register the user first')
            user.is_admin=True
        db.add(Audit(actor='local-admin',action=args.action,resource='user:'+args.username))

if __name__=='__main__': main()
