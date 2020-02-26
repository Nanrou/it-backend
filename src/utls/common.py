from collections import namedtuple
from datetime import datetime, timedelta
import socket
import platform

from aiohttp.web import Request
from jwt import encode as jwt_encode
from qrcode import make as qrcode_make
from werkzeug.security import check_password_hash

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


async def send_email(phone):
    pass


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
                await cur.execute(cmd, (key, ))
                row = await cur.fetchone()
                if row:
                    _config = row[0]
                    await set_config(request, key, _config)
                    await conn.commit()
                    return _config
                else:
                    await conn.commit()


# cache 版本号+内容缓存 服务端

