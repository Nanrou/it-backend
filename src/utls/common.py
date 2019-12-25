from collections import namedtuple
from datetime import datetime, timedelta

from aiohttp.web import Request
from jwt import encode as jwt_encode
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
            if r and check_password_hash(r[-1], password):
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
