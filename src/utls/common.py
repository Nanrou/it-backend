import base64
from collections import namedtuple
from datetime import datetime, timedelta
from email.message import EmailMessage
from hashlib import sha1
import hmac
from json import loads
import socket
import platform
from random import random

from aliyunsdkcore.auth.composer.rpc_signature_composer import get_signed_url
from aiohttp import ClientSession, ClientTimeout, ClientError, ContentTypeError
from aiohttp.web import Request
from aiosmtplib import SMTP, SMTPTimeoutError
from jwt import encode as jwt_encode
from qrcode import make as qrcode_make
from pymysql.err import IntegrityError
from werkzeug.security import check_password_hash

from src.meta.exception import SmsLimitException
from src.settings import config

CACHE_EXPIRE_TIME = 15 * 60


def dict_to_object(name: str, keys: tuple or list, values: tuple or list):
    _name = namedtuple(name, keys)
    return _name(*values)


async def verify_login(pool, username_tuple, password) -> namedtuple:
    """

    :param pool: 连接池
    :param username_tuple: (列名，值)
    :param password:
    :return:
    """
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM profile WHERE {}=%s".format(username_tuple[0]),
                (username_tuple[1],)
            )
            r = await cur.fetchone()
            await conn.commit()
            if r and check_password_hash(r[-2], password):  # todo 避免写死
                return dict_to_object('profile', [d[0] for d in cur.description], r)


async def update_token(content: dict, old_token: str, app):
    """ 设置新的颁发时间和过期时间 """
    content['iat'] = round(datetime.now().timestamp()),
    content['exp'] = round((datetime.now() + timedelta(hours=24)).timestamp())

    new_token = jwt_encode(content, app['config']['jwt-secret'], algorithm='HS256').decode('utf-8')

    await app['black_bf'].insert(old_token)

    # 更新token时预留的缓冲时间
    await app['redis'].set(
        key='it:tmp-list:{}'.format(old_token),
        value=new_token,
        expire=30,
    )
    return new_token


async def set_cache_version(request: Request, key: str):
    """

    :param request:
    :param key: 缓存数据的类别
    :return:
    """
    _key = f'{key}-version'
    await request.app['redis'].set(
        key=_key,
        value=str(int(datetime.now().timestamp() * 1000)),
        expire=CACHE_EXPIRE_TIME,
    )


async def get_cache_version(request: Request, key: str):
    """

    :param request:
    :param key: 缓存数据的类别
    :return:
    """
    _key = f'{key}-version'
    version = await request.app['redis'].get(_key)
    if version:
        return version
    else:
        await request.app['redis'].set(key=_key,
                                       value=str(int(datetime.now().timestamp() * 1000)),
                                       expire=CACHE_EXPIRE_TIME)
        return await request.app['redis'].get(_key)


def get_host_ip():
    """ 获取本机ip """
    _s = None
    try:
        _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _s.connect(('8.8.8.8', 80))
        ip = _s.getsockname()
    finally:
        if _s:
            _s.close()
    return ip[0]


if platform.system() == 'Darwin':
    HOST = '{}:8082'.format(get_host_ip())
else:
    HOST = 'mobile.it.aquazhuhai.com'


def get_qrcode(eid):
    """ 生成二维码 """
    return qrcode_make('https://{}/query?eid={}'.format(HOST, eid), box_size=5)


SMS_REDIS_KEY = 'eid:{eid}:report'
SMS_REDIS_VALUE = '{phone}|{captcha}'
SEND_SMS_INTERVAL = 300


async def send_ali_sms(phone: str, captcha: str):
    params = {
        # "AccessKeyId": config['sms']['ali']['AccessKeyId'],
        # "Timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        # "Format": "JSON",
        # "SignatureMethod": "HMAC-SHA1",
        # "SignatureVersion": "1.0",
        # "SignatureNonce": uuid4().hex,
        # "Signature": "",
        "Action": "SendSms",
        "Version": "2017-05-25",
        "RegionId": "cn-hangzhou",
        "PhoneNumbers": phone,
        "SignName": config['sms']['ali']['SignName'],
        "TemplateCode": config['sms']['ali']['TemplateCode'],
        "TemplateParam": {"code": captcha},
    }
    uri = config['sms']['ali']['uri'] + get_signed_url(params, config['sms']['ali']['AccessKeyId'],
                                                       config['sms']['ali']['Secret'], 'JSON', 'GET', {})[0]
    try:
        async with ClientSession(timeout=ClientTimeout(total=3)) as session:
            async with session.get(uri) as resp:
                try:
                    data = await resp.json()
                except ContentTypeError:
                    data = loads(await resp.text())
    except ClientError:
        raise RuntimeError
    try:
        assert data['Code'] == 'OK'
    except KeyError:
        raise RuntimeError
    except AssertionError:
        if 'LIMIT' in data['Code']:
            raise SmsLimitException
        else:
            raise RuntimeError


async def send_sms(request, eid, phone):
    _key = SMS_REDIS_KEY.format(eid=eid)
    _exist = await request.app['redis'].get(_key)
    if _exist:
        raise SmsLimitException
    else:
        _captcha = create_captcha()
        await send_ali_sms(phone, _captcha)
        await request.app['redis'].set(key=_key,
                                       value=SMS_REDIS_VALUE.format(phone=phone, captcha=_captcha),
                                       expire=SEND_SMS_INTERVAL)


async def check_sms_captcha(request: Request, eid: str, phone: str, captcha: str) -> bool:
    _key = SMS_REDIS_KEY.format(eid=eid)
    _value = await request.app['redis'].get(_key)
    if _value:
        _p, _c = _value.split('|')
        return (_p == phone) and (_c == captcha)
    else:
        return False


# 邮件发送是做持久化记录的，短信不记录


try:
    SMTP_DATA = {
        'username': config['smtp']['username'],
        'password': config['smtp']['password'],
        'server': config['smtp']['server'],
        'port': config['smtp']['port'],
        'From': config['smtp']['From']
    }
except KeyError:
    raise RuntimeError('Cant send email without smtp data')

ORDER_TITLE = "{id_}故障工单"
ORDER_CONTENT = "  {content}，请及时处理。处理验证码为：{captcha}"

PATROL_TITLE = "{id_}巡检计划"
PATROL_CONTENT = "有新的巡检计划，合计 {total} 台设备。巡检验证码为：{captcha}"


def create_captcha() -> str:  # 生成和更新验证码
    return str(random())[2: 8]


async def set_captcha(request, case_id, captcha):
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO `captcha_meta` (case_id, captcha) VALUES (%s, %s)", (case_id, captcha))
            await conn.commit()


async def update_captcha(request, case_id, captcha):
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE `captcha_meta` SET captcha=%s WHERE case_id=%s)", (captcha, case_id))
            await conn.commit()


async def send_maintenance_order_email(request, oid: str, case_id: str, captcha: str, to_address: str):
    msg = EmailMessage()
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT `content` FROM `order_history` WHERE `status`='R' AND oid=%s", oid)
            row = await cur.fetchone()
            if row:
                msg['Subject'] = ORDER_TITLE.format(id_=case_id)
                content = ORDER_CONTENT.format(content=row[0], captcha=captcha)
                msg.set_content(content)
                await conn.commit()
            else:  # 没有对应工单的内容
                raise RuntimeError
    await send_email(msg, to_address)
    await store_email_content(request, case_id, to_address, captcha, content)
    try:  # 重发的时候会重复插入
        await set_captcha(request, case_id, captcha)
    except IntegrityError:
        pass


async def send_patrol_email(request, pid: str, case_id: str, captcha: str, to_address: str):
    msg = EmailMessage()
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT `total` FROM `patrol_meta` WHERE id=%s", pid)
            row = await cur.fetchone()
            if row:
                msg['Subject'] = PATROL_TITLE.format(id_=case_id)
                content = PATROL_CONTENT.format(total=row[0], captcha=captcha)
                msg.set_content(content)
                await conn.commit()
            else:  # 没有对应工单的内容
                raise RuntimeError
    await send_email(msg, to_address)
    await store_email_content(request, case_id, to_address, captcha, content)
    try:  # 重发的时候会重复插入
        await set_captcha(request, case_id, captcha)
    except IntegrityError:
        pass


async def store_email_content(request, case_id, email, captcha, content):
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO `email_history` (case_id, email, captcha, content) VALUES (%s, %s, %s, %s)",
                              (case_id, email, captcha, content))
            await conn.commit()


async def send_email(msg: EmailMessage, to_address: str):  # 超时raise Timeout
    msg['From'] = SMTP_DATA['From']
    # msg['To'] = to_address
    try:
        async with SMTP(hostname=SMTP_DATA['server'], port=SMTP_DATA['port'], use_tls=True) as smtp_client:
            await smtp_client.login(SMTP_DATA['username'], SMTP_DATA['password'])
            await smtp_client.send_message(msg, recipients=to_address, timeout=6)
    except SMTPTimeoutError:
        raise TimeoutError


async def set_config(request: Request, key: str, value: str):
    _key = f'it:config:{key}'
    await request.app['redis'].set(
        key=_key,
        value=value,
        expire=CACHE_EXPIRE_TIME,
    )


async def get_config(request: Request, key: str):
    """

    :param request:
    :param key: 缓存数据的类别
    :return:
    """
    _key = f'it:config:{key}'
    config = await request.app['redis'].get(_key)
    if config:
        return config
    else:
        async with request.app['mysql'].acquire() as conn:
            async with conn.cursor() as cur:
                cmd = "SELECT `value` from `it_config` where `key=%s`"
                await cur.execute(cmd, (key,))
                row = await cur.fetchone()
                if row:
                    _config = row[0]
                    await set_config(request, key, _config)
                    await conn.commit()
                    return _config
                else:
                    await conn.commit()


# cache 版本号+内容缓存 服务端


if __name__ == '__main__':
    # pass
    #     smtp_server = "smtp.exmail.qq.com"
    #     smtp_port = 465
    #     smtp_name = 'admin@aquazhuhai.com'
    #     smtp_password = 'Aa2968932'
    #
    #     msg = EmailMessage()
    #     msg.set_content("""\
    # {department}的{equipment}出现故障，请尽快处理。验证码为：{captcha}
    # """.format(department="a", equipment='b', captcha='c'))
    #     msg['Subject'] = '{order_id}故障工单'.format(order_id='202002004')
    #     msg['From'] = '珠海市供水有限公司<admin@aquazhuhai.com>'
    #     msg['To'] = 'kkkcomkkk@qq.com'
    #     with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
    #         server.login(smtp_name, smtp_password)
    #         server.send_message(msg, from_addr='admin@aquazhuhai.com')
    import asyncio

    loop = asyncio.get_event_loop()
    loop.run_until_complete(send_ali_sms('13532227149', '123456'))

