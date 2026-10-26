"""Root-only deployment check against the real HTTPS endpoint; creates no content."""
import httpx,re,json
from pathlib import Path
credentials=dict(line.split(': ',1) for line in Path('/etc/rabbit/admin-initial.txt').read_text().splitlines())
origin='https://mushroom-king-timer.online'
with httpx.Client(base_url=origin+'/party/api',headers={'Origin':origin},timeout=15) as client:
    assert client.get('/admin/overview').status_code==401
    challenge=client.get('/challenge').json()
    values=re.findall(r'\d+',challenge['question'])
    response=client.post('/auth/login',json={'username':credentials['Username'],'password':credentials['Password'],'challenge_id':challenge['id'],'answer':str(sum(map(int,values)))})
    assert response.status_code==200,response.status_code
    cookie=response.headers['set-cookie'].lower()
    assert all(x in cookie for x in ('httponly','secure','samesite=lax','path=/party'))
    csrf=response.json()['csrf']
    assert client.get('/auth/session').json()['user']['is_admin']
    overview=client.get('/admin/overview');assert overview.status_code==200
    schema=client.get('/admin/openapi');assert schema.status_code==200
    Path('/home/ubuntu/rabbit-openapi.json').write_text(json.dumps(schema.json(),ensure_ascii=False,indent=2))
    assert client.post('/auth/logout').status_code==403
    assert client.post('/auth/logout',headers={'X-CSRF-Token':csrf}).status_code==200
    assert client.get('/admin/overview').status_code==401
print('HTTPS login, secure cookie, session, admin ACL, OpenAPI and CSRF/logout checks passed. No cards or applications created.')
