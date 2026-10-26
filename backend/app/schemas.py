import base64, io, re
from decimal import Decimal
from typing import Literal
from PIL import Image
from pydantic import BaseModel, Field, AwareDatetime, field_validator, model_validator
from .qr_image import contains_qr

class Input(BaseModel):
    model_config = {'str_strip_whitespace': True, 'extra': 'forbid'}

class Human(Input):
    challenge_id: str = ''
    answer: str = ''
    website: str = Field(default='', max_length=0)

class Credentials(Human):
    username: str = Field(min_length=3, max_length=32, pattern=r'^[a-zA-Z0-9_\u4e00-\u9fff]+$')
    password: str = Field(min_length=10, max_length=128)

class ContactInput(Input):
    wechat: str = Field(default='', max_length=80)
    qr: str = Field(default='', max_length=700000)
    @field_validator('qr')
    @classmethod
    def valid_qr(cls, value):
        if not value:
            return value
        if not value.startswith('data:image/') or ';base64,' not in value:
            raise ValueError('二维码必须为图片')
        try:
            raw = base64.b64decode(value.split(',',1)[1], validate=True)
            if len(raw) > 500000:
                raise ValueError()
            with Image.open(io.BytesIO(raw)) as img:
                if img.width * img.height > 2000000 or img.format not in ('JPEG','PNG','WEBP'):
                    raise ValueError()
                img.load()
                image=Image.new('RGB',img.size,'white')
                rgba=img.convert('RGBA');image.paste(rgba,mask=rgba.getchannel('A'))
        except Exception:
            raise ValueError('二维码图片无效或过大，请使用小于 500 KB 的 PNG/JPEG/WebP')
        if not contains_qr(image):
            raise ValueError('上传图片非二维码')
        out=io.BytesIO();image.save(out,format='PNG')
        mime='png'
        if out.tell()>500000:
            out=io.BytesIO();image.save(out,format='JPEG',quality=85);mime='jpeg'
        if out.tell()>500000:
            raise ValueError('二维码图片过大，请截取二维码区域后重试')
        return f'data:image/{mime};base64,' + base64.b64encode(out.getvalue()).decode()
    @model_validator(mode='after')
    def not_empty(self):
        if not self.wechat and not self.qr:
            raise ValueError('请填写微信号或上传二维码')
        return self

class CharacterInput(Input):
    name: str = Field(min_length=1, max_length=40)
    level: int = Field(ge=1, le=300)
    job: str = Field(default='', max_length=30)

class CardInput(Human):
    game_id: str = Field(min_length=1, max_length=40)
    level: int = Field(ge=1, le=300)
    map_name: str = Field(min_length=1, max_length=60)
    capacity: int = Field(ge=2, le=6)
    boss_slots: int | None = Field(default=None,ge=1,le=5)
    teammate_need: Literal['none','dragon_knight','priest'] | None = None
    teammate_level_min: int | None = Field(default=None,ge=1,le=300)
    teammate_level_max: int | None = Field(default=None,ge=1,le=300)
    fighter_count: int = Field(default=1, ge=1, le=5)
    priest_count: int = Field(default=0, ge=0, le=1)
    flower: Literal['none','active','afk','any']
    price_mode: Literal['hour','experience','any']
    price_currency: Literal['rmb','meso'] = 'rmb'
    price: Decimal | None = Field(default=None, gt=0, le=1000000000000, decimal_places=2)
    night_price: Decimal | None = Field(default=None, gt=0, le=1000000000000, decimal_places=2)
    level_min: int = Field(default=1, ge=1, le=300)
    level_max: int = Field(default=300, ge=1, le=300)
    exp_min: int = Field(ge=0, le=100000000)
    exp_max: int = Field(ge=1, le=100000000)
    start_time: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    end_time: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    notes: str = Field(default='', max_length=600)
    duration_hours: int = Field(default=24, ge=1, le=168)
    contact: ContactInput
    public_contact: bool = False
    version: int | None = None
    @model_validator(mode='after')
    def ranges(self):
        if self.price_currency=='meso' and self.price_mode!='hour':
            raise ValueError('游戏币仅适用于按小时收费')
        for amount in (self.price,self.night_price):
            if amount is None:continue
            if self.price_currency=='meso' and amount!=amount.to_integral_value():
                raise ValueError('游戏币收费请填写整数')
            if self.price_currency=='rmb' and amount>999999:
                raise ValueError('人民币收费或包经验数值不能超过 999999')
        if self.exp_min > self.exp_max or self.level_min > self.level_max:
            raise ValueError('范围的最小值不能大于最大值')
        if self.teammate_level_min is not None and self.teammate_level_max is not None and self.teammate_level_min > self.teammate_level_max:
            raise ValueError('队友最低等级不能大于最高等级')
        return self

class ApplyInput(Human):
    card_type: Literal['team','boss']
    card_id: int = Field(gt=0)
    offered_team_id: int | None = None
    game_id: str = Field(min_length=1, max_length=40)
    level: int = Field(ge=1, le=300)
    notes: str = Field(default='', max_length=400)
    contact: ContactInput
    requested_start_at: AwareDatetime | None = None
    duration_hours: int | None = Field(default=None,ge=1,le=168)
    @model_validator(mode='after')
    def schedule_pair(self):
        if (self.requested_start_at is None)!=(self.duration_hours is None):
            raise ValueError('请同时填写预计上车时间和挂机小时数')
        return self

class Action(Input):
    action: str = Field(max_length=30)
    version: int | None = None

class PartnerInput(Human):
    kind: Literal['recruit','job'] = 'recruit'
    role: Literal['fighter','priest']
    target_role: Literal['fighter','priest','any'] = 'fighter'
    target_job: Literal['','龙骑士'] = ''
    game_id: str = Field(min_length=1,max_length=40)
    level: int = Field(ge=1,le=300)
    job: str = Field(default='',max_length=30)
    map_name: str = Field(default='',max_length=60)
    flower: Literal['active','afk','any'] = 'any'
    hourly_rate: Decimal | None = Field(default=None,gt=0,le=1000000000000,decimal_places=2)
    price_currency: Literal['rmb','meso'] | None = None
    level_min: int = Field(default=1,ge=1,le=300)
    level_max: int = Field(default=300,ge=1,le=300)
    start_time: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    end_time: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    notes: str = Field(default='',max_length=600)
    duration_hours: int = Field(default=24,ge=1,le=168)
    contact: ContactInput
    public_contact: bool = False
    version: int | None = None
    @model_validator(mode='after')
    def consistent(self):
        if self.target_job and (self.kind!='recruit' or self.target_role!='fighter'):raise ValueError('只有招募打手时可以指定龙骑士职业')
        if self.level_min>self.level_max:raise ValueError('对方最低等级不能超过最高等级')
        if self.kind=='job':
            if self.role!='priest' or self.target_role!='any':raise ValueError('求职卡仅供祭司发布')
            if self.flower=='any':raise ValueError('求职请选择自己的活花或死花类型')
            if self.hourly_rate is None or self.price_currency is None:raise ValueError('请填写每小时收费和人民币/游戏币类型')
            if self.price_currency=='meso' and self.hourly_rate!=self.hourly_rate.to_integral_value():raise ValueError('游戏币收费请填写整数')
        elif self.target_role=='any' or self.hourly_rate is not None or self.price_currency is not None:
            raise ValueError('招募卡请选择寻找打手或祭司，收费信息在求职卡中填写')
        return self

class PartnerJoinInput(Input):
    wechat_confirmed: Literal[True]

class PartnerApplyInput(Human):
    card_id: int = Field(gt=0)
    role: Literal['fighter','priest']
    game_id: str = Field(min_length=1,max_length=40)
    level: int = Field(ge=1,le=300)
    job: str = Field(default='',max_length=30)
    flower: Literal['active','afk','none'] = 'none'
    notes: str = Field(default='',max_length=400)
    contact: ContactInput
    @model_validator(mode='after')
    def consistent(self):
        if (self.role=='fighter')!=(self.flower=='none'):raise ValueError('祭司需选择花类型，打手不填写花类型')
        return self

class ReviewInput(Input):
    tags: list[Literal['刷怪稳定','BUFF 稳定','多次断花','沟通守时']] = Field(min_length=1, max_length=4)
    body: str = Field(default='', max_length=500)

class ReportInput(Human):
    resource: Literal['team','boss','partner','review','user','appeal']
    resource_id: int = Field(gt=0)
    reason: str = Field(min_length=5, max_length=600)

class Moderation(Input):
    resource: Literal['team','boss','partner','review','report','user','match']
    resource_id: int = Field(gt=0)
    action: Literal['hide','approve','reject','ban','unban','resolve','cancel']
    reason: str = Field(min_length=3, max_length=500)

class RecoveryInput(Input):
    resource: Literal['boss','application']
    resource_id: int = Field(gt=0)
    email: str = Field(default='', max_length=200)
    code: str = Field(default='', max_length=10)
