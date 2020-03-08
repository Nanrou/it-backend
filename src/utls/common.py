from collections import namedtuple
from datetime import datetime, timedelta
from email.message import EmailMessage
import socket
import platform
from random import random

from aiosmtplib import SMTP, SMTPTimeoutError
from aiohttp.web import Request
from jwt import encode as jwt_encode
from qrcode import make as qrcode_make
from pymysql.err import IntegrityError
from werkzeug.security import check_password_hash

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
    return qrcode_make('http://{}/query?eid={}'.format(HOST, eid), box_size=5)


async def send_sms(phone):
    pass


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
PATROL_CONTENT = "有新的巡检计划。巡检验证码为：{captcha}\n{patrol_plan}"


def create_captcha() -> str:  # 生成和更新验证码
    return str(random())[2: 8]


async def set_captcha(request, mid, captcha):
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO `captcha_meta` (case_id, captcha) VALUES (%s, %s)", (mid, captcha))
            await conn.commit()


async def update_captcha(request, mid, captcha):
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE `captcha_meta` SET captcha=%s WHERE case_id=%s)", (captcha, mid))
            await conn.commit()


async def send_maintenance_order_email(request, oid: str, order_id: str, captcha: str, to_address: str):
    msg = EmailMessage()
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT `content` FROM `order_history` WHERE `status`='R' AND oid=%s", oid)
            row = await cur.fetchone()
            if row:
                msg['Subject'] = ORDER_TITLE.format(id_=order_id)
                content = ORDER_CONTENT.format(content=row[0], captcha=captcha)
                msg.set_content(content)
                await conn.commit()
            else:  # 没有对应工单的内容
                raise RuntimeError
    await send_email(msg, to_address)
    await store_email_content(request, order_id, to_address, captcha, content)
    try:  # 重发的时候会重复插入
        await set_captcha(request, order_id, captcha)
    except IntegrityError:
        pass


async def store_email_content(request, order_id, email, captcha, content):
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO `email_history` (case_id, email, captcha, content) VALUES (%s, %s, %s, %s)",
                              (order_id, email, captcha, content))
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


async def check_captcha(request: Request, phone: str, captcha: str) -> bool:
    return True


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
    pass
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
