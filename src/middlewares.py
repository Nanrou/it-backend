from datetime import datetime, timedelta
from re import match

from aiohttp.web import middleware, Request
from jwt import decode as jwt_decode
from jwt.exceptions import InvalidSignatureError, ExpiredSignatureError, DecodeError

from src.utls.common import update_token
from src.utls.toolbox import code_response
from src.meta.permission import Permission
from src.meta.response_code import InvalidTokenResponse, RepetitionLoginResponse

"""
检查登陆状态 -> 是否重复登录 -> 检查权限
"""

WITHOUT_VERIFY = [
    ('/api/user/login', 'POST'),
    ('/api/user/logout', 'GET'),
    # 以下都是为移动端服务的
    ('/api/maintenance/report', 'POST'),
    ('/api/maintenance/arrival', 'PATCH'),
    ('/api/maintenance/fix', 'PATCH'),
    ('/api/maintenance/appraisal', 'PATCH'),
    # ('/api/order', 'POST'),
    # ('/api/equipment', 'GET'),
    # ('/api/captcha', 'GET'),
    # ('/api/order/special-captcha', 'GET'),
    # ('/api/order', 'GET'),
    # ('/api/order/arrival', 'PATCH'),
    # ('/api/order/handle', 'PATCH'),
    # ('/api/order/cancel', 'PATCH'),
    # ('/api/history-order-wap', 'GET'),
    # ('/api/order-flow-wap', 'GET'),
]

MODULE_PERMISSION = {
    '/api/equipment': Permission.WRITE,
    '/api/relation/(?!(search))': Permission.SUPER,
    '/api/user/(query|reset_password|create|permission)': Permission.SUPER,
    '/api/user/dispatch-query': Permission.MAINTENANCE_HIGHER,
}


@middleware
async def verify_jwt_token(request: Request, handler):
    if any([request.path == path and request.method == method for path, method in WITHOUT_VERIFY]):
        resp = await handler(request)
        return resp

    else:  # 对jwt token检验
        try:
            if match('/ws/.*', request.path):
                token = request.query['token']
            else:
                token = request.headers.get('Authorization').split(' ')[-1]
            app = request.app
        except (AttributeError, KeyError, IndexError):
            return code_response(InvalidTokenResponse)

        try:
            content = jwt_decode(token, app['config']['jwt-secret'], algorithms=['HS256'])
            # 检查功能模块的权限
            for pattern in MODULE_PERMISSION.keys():
                if match(pattern, request.path):
                    if content.get('rol') & MODULE_PERMISSION[pattern]:
                        break
                    else:
                        return code_response(RepetitionLoginResponse)
            # 检测重复登录
            try:
                _key = '{}:{}:jwt'.format(content.get('name'), content.get('dep'))
                _value = await request.app['redis'].get(_key)
                if _value:
                    assert token == _value
            except AssertionError:
                return code_response(InvalidTokenResponse)

            request['jwt_content'] = content
            if await app['black_bf'].is_contain(token):
                # 是否在缓冲表中
                if await app['redis'].exists('it:tmp-list:{}'.format(token)):
                    resp = await handler(request)
                    resp.headers['jwt_new_token'] = await app['redis'].get('it:tmp-list:{}'.format(token))
                    return resp
                else:
                    return code_response(InvalidTokenResponse)
            else:
                resp = await handler(request)
                # 离过期不足5分钟，更新token
                if content.get('exp') <= (datetime.now() + timedelta(minutes=5)).timestamp():
                    # 在header加上新token，通过前端axios拦截下来，然后更新
                    resp.headers['jwt_new_token'] = await update_token(content, token, app)
                return resp
        except (InvalidSignatureError, ExpiredSignatureError, DecodeError):
            return code_response(InvalidTokenResponse)


if __name__ == '__main__':
    # for u in ['/api/user/login', '/api/equipment', '/api/relation/add', '/api/user/query']:
    #     for _u in WITHOUT_VERIFY:
    #         print('uri: {}, pattern: {}, match: {}'.format(u, _u, bool(match(_u, u))))
    #     for _u in MODULE_PERMISSION:
    #         print('uri: {}, pattern: {}, match: {}'.format(u, _u, bool(match(_u, u))))
    pass
