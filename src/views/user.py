from datetime import datetime, timedelta
from re import match

from aiohttp.web import json_response, Response, Request
from aiohttp.web_exceptions import HTTPForbidden
from jwt import encode as jwt_encode
from pymysql.err import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

from src.meta.permission import Permission
from src.meta.response_code import InvalidUserDataResponse, ResponseOk, InvalidOriginPasswordResponse, RepetitionUserResponse
from src.utls.toolbox import PrefixRouteTableDef, ItHashids, code_response, get_query_params
from src.utls.common import verify_login

routes = PrefixRouteTableDef('/api/user')


@routes.post('/login')
async def login(request: Request):
    data = await request.json()
    if match(r'^\d+', data.get('username')):
        _username = ('work_number', data.get('username'))
    else:
        _username = ('username', data.get('username'))
    user = await verify_login(request.app['mysql'], _username, data.get('password'))
    if user:
        jwt_token = jwt_encode({
            'uid': ItHashids.encode(user.id),
            'name': user.name,
            'dep': user.department,
            'rol': user.role,
            'pho': user.phone,
            'iat': round(datetime.now().timestamp()),
            'exp': round((datetime.now() + timedelta(hours=24)).timestamp())
        }, request.app['config']['jwt-secret'], algorithm='HS256').decode('utf-8')
        await request.app['redis'].set('{}:{}:jwt'.format(user.name, user.department), jwt_token,
                                       expire=60 * 60 * 24)  # 这是为了禁止重复登录
        return code_response(ResponseOk, {
            'token': jwt_token,
            'user': {
                'name': user.name,
                'department': user.department,
                'role': user.role,
                'phone': user.phone,
            }
        })
    else:
        return code_response(InvalidUserDataResponse)


@routes.get('/logout')
async def logout(request: Request):
    await request.app['black_bf'].insert(request.headers.get('Authorization').split(' ')[-1])
    return code_response(ResponseOk)


@routes.get('/alive')
async def alive(request: Request):
    # uid 是藏在jwt中的
    return code_response(ResponseOk, {
        'name': request['jwt_content']['name'],
        'department': request['jwt_content']['dep'],
        'role': request['jwt_content']['rol'],
        'phone': request['jwt_content']['pho'],
    })


@routes.patch('/change_password')
async def change_password(request: Request):
    data = await request.json()
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM profile WHERE id=%s", (request['jwt_content'].get('uid'),))
            r = await cur.fetchone()
            await conn.commit()
            if r and check_password_hash(r[-1], data.get('originPassword')):
                await cur.execute('UPDATE profile SET password_hash=%s WHERE id=%s',
                                  (generate_password_hash(data.get('newPassword')), request['jwt_content'].get('uid')))
                await conn.commit()
                return code_response(ResponseOk)
            else:
                return code_response(InvalidOriginPasswordResponse)

#
# @routes.get('/blacklist-length')
# async def get_blacklist_length(request: Request):
#     _number = await request.app['redis'].scard(key='it:blacklist')
#     return json_response({'number': _number})
#
#
# @routes.post('/remove-expire-jwt')
# async def remove_expire_jwt(request: Request):
#     _timestamp = datetime.now().timestamp()
#     _count = 0
#     # 去blacklist中看每个jwt的过期时间，如果现在已经过了其本身的过期时间，就删掉
#     for member in await request.app['redis'].smembers('it:blacklist'):
#         content = jwt_decode(member, request.app['config']['jwt-secret'], algorithms=['HS256'])
#         if content.get('exp') < _timestamp:
#             await request.app['redis'].srem('it:blacklist', member)
#             _count += 1
#     return json_response({'number': _count})


@routes.get('/admin')
async def query(request: Request):
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM profile")  # todo 根据权限来看，不能直接是所有

            data = []
            for row in await cur.fetchall():
                if row[6] & Permission.SUPREME:
                    continue
                data.append({
                    'uid': ItHashids.encode(row[0]),
                    'username': row[1],
                    'workNumber': row[2],
                    'name': row[3],
                    'department': row[4],
                    'phone': row[5],
                    'role': row[6],
                })
            await conn.commit()
    return code_response(ResponseOk, data)


def get_user_id(request: Request):
    return get_query_params(request, 'uid')


@routes.patch('/reset_password')
async def reset_password(request: Request):
    _uid = get_user_id(request)
    data = await request.json()
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute('UPDATE profile SET password_hash=%s WHERE id=%s',
                              (generate_password_hash(data.get('password') or "8888"), _uid))
            await conn.commit()
    return code_response(ResponseOk)


@routes.patch('/permission')
async def reset_password(request: Request):
    _uid = get_user_id(request)
    data = await request.json()
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute('UPDATE profile SET role=%s WHERE id=%s',
                              (data.get('permission'), _uid))
            await conn.commit()
    return code_response(ResponseOk)


@routes.post('/create')
async def create(request: Request):
    data = await request.json()
    cmd = """\
INSERT INTO profile (
username,
work_number,
name,
department,
role,
phone,
password_hash
) VALUES (%s, %s, %s, %s, %s, %s, %s)\
"""
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            try:
                await cur.execute(cmd, (
                    data.get('username'),
                    data.get('number'),
                    data.get('name'),
                    data.get('department'),
                    data.get('role'),
                    data.get('phone'),
                    generate_password_hash('8888')
                ))
                await conn.commit()
            except IntegrityError:
                return code_response(RepetitionUserResponse)
    return code_response(ResponseOk)


@routes.get('/dispatch-query')
async def dispatch_query(request: Request):
    """ 获取维修人员名单 """
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            cmd = "SELECT * FROM profile WHERE role & {}".format(Permission.MAINTENANCE)
            await cur.execute(cmd)
            data = []
            for row in await cur.fetchall():
                if row[6] & Permission.SUPREME:
                    pass
                data.append({
                    'pid': ItHashids.encode(row[0]),
                    'name': row[3],
                    'phone': row[5]
                })
            await conn.commit()
    return code_response(ResponseOk, data)

