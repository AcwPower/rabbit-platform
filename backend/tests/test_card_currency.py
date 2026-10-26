from decimal import Decimal
import uuid
import pytest
from pydantic import ValidationError
from app.schemas import CardInput
from conftest import signup,post,card_data,guest,apply_guest


@pytest.mark.parametrize('kind',['team','boss'])
def test_currency_roundtrip_create_edit_and_public_reads(client,kind):
    signup(client)
    payload=card_data(client,price_currency='meso',price='1500000',night_price='9000000')
    response=post(client,f'/api/{kind}-cards',payload)
    assert response.status_code==201,response.text
    card=response.json()
    for saved in (card,guest().get(f'/api/{kind}-cards').json()['items'][0],
                  client.get(f"/api/{kind}-cards/{card['id']}").json(),client.get('/api/me').json()['cards'][0]):
        assert saved['price_currency']=='meso'
        assert Decimal(str(saved['price']))==1500000
        assert Decimal(str(saved['night_price']))==9000000
    if kind=='team':
        boss=guest();aid,_=apply_guest(boss,card)
        assert client.get(f'/api/applications/{aid}').json()['card']['price_currency']=='meso'
    payload.update(price='2000000',night_price='12000000',version=card['version'])
    changed=client.put(f"/api/{kind}-cards/{card['id']}",json=payload,headers={'X-Idempotency-Key':str(uuid.uuid4())})
    assert changed.status_code==200,changed.text
    assert changed.json()['price_currency']=='meso'
    assert Decimal(str(changed.json()['price']))==2000000
    payload.update(price_currency='rmb',price='12.50',night_price='60',version=changed.json()['version'])
    changed=client.put(f"/api/{kind}-cards/{card['id']}",json=payload,headers={'X-Idempotency-Key':str(uuid.uuid4())})
    assert changed.status_code==200,changed.text
    assert changed.json()['price_currency']=='rmb' and Decimal(str(changed.json()['price']))==Decimal('12.50')


def test_legacy_rmb_default_and_protection_from_old_editor(client):
    signup(client)
    original=post(client,'/api/team-cards',card_data(client)).json()
    assert original['price_currency']=='rmb' and Decimal(str(original['price']))==Decimal('8.50')
    coin=post(client,'/api/team-cards',card_data(client,price_currency='meso',price=500)).json()
    response=client.put(f"/api/team-cards/{coin['id']}",json=card_data(client,price=500,version=coin['version']),
                        headers={'X-Idempotency-Key':str(uuid.uuid4())})
    assert response.status_code==409,response.text
    assert client.get(f"/api/team-cards/{coin['id']}").json()['price_currency']=='meso'


def test_currency_validation_bounds_and_mode(client):
    payload=card_data(client)
    for overrides in ({'price_currency':'usd'}, {'price_currency':'meso','price':'1.5'},
                      {'price_currency':'meso','night_price':'3.25','price':'100'},
                      {'price_currency':'meso','price':0}, {'price_currency':'meso','price':1000000000001},
                      {'price_currency':'meso','price_mode':'experience'},
                      {'price_currency':'meso','price_mode':'any'},
                      {'price_currency':'rmb','price':1000000}, {'price_currency':'rmb','night_price':1000000}):
        with pytest.raises(ValidationError):CardInput(**(payload|overrides))
    for currency,price in [('meso',1),('meso',1000000000000),('rmb','0.01'),('rmb',999999)]:
        assert CardInput(**(payload|{'price_currency':currency,'price':price})).price==Decimal(str(price))


def test_game_coin_maximum_and_boss_unspecified_amount(client):
    signup(client)
    result=post(client,'/api/team-cards',card_data(client,price_currency='meso',price=1000000000000,night_price=1000000000000))
    assert result.status_code==201,result.text
    saved=client.get(f"/api/team-cards/{result.json()['id']}").json()
    assert Decimal(str(saved['price']))==1000000000000
    result=post(client,'/api/boss-cards',card_data(client,price_currency='meso',price=None))
    assert result.status_code==201,result.text
    assert result.json()['price_currency']=='meso' and result.json()['price'] is None
