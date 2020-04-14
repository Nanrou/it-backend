import hashlib
import platform
from time import time
from re import search
from secrets import token_hex

from aiohttp import ClientSession, ClientTimeout, ServerTimeoutError, ContentTypeError
from aiohttp.web import Request

from src.settings import CONFIG

WORK_WX_TOKEN_KEY = "it:work:token"
WORK_WX_TOKEN_TIMEOUT = 7200
ACCESS_TOKEN_API = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
GET_USER_ID = "https://qyapi.weixin.qq.com/cgi-bin/user/getuserinfo"
GET_USER = "https://qyapi.weixin.qq.com/cgi-bin/user/get"
GET_JSAPI_TICKET = "https://qyapi.weixin.qq.com/cgi-bin/get_jsapi_ticket"
WORK_WX_JSAPI_TICKET_KEY = "it:work:ticket"


async def handle_wechat_api(base_url, params):
    # todo handle exception
    try:
        async with ClientSession(timeout=ClientTimeout(total=5)) as session:
            async with session.get(base_url, params=params) as resp:
                data = await resp.json()
                assert data['errcode'] == 0
                return data
    except ServerTimeoutError:
        pass
    except ContentTypeError:
        pass
    except KeyError:
        pass
    except AssertionError:
        pass


async def get_wx_access_token(request: Request) -> str:
    """ 获取access token """
    _ak = await request.app['redis'].get(WORK_WX_TOKEN_KEY)
    if _ak:
        return _ak

    data = await handle_wechat_api(ACCESS_TOKEN_API, {
        'corpid': CONFIG['wechat']['corpid'],
        'corpsecret': CONFIG['wechat']['Secret'],
    })
    await request.app['redis'].set(
        key=WORK_WX_TOKEN_KEY,
        value=data['access_token'],
        expire=WORK_WX_TOKEN_TIMEOUT,
    )

    return data['access_token']


async def get_wx_jsapi_ticket(request: Request) -> str:
    """ 获取jsapi ticket """
    _ak = await request.app['redis'].get(WORK_WX_JSAPI_TICKET_KEY)
    if _ak:
        return _ak

    data = await handle_wechat_api(GET_JSAPI_TICKET, {
        'access_token': await get_wx_access_token(request)
    })
    await request.app['redis'].set(
        key=WORK_WX_JSAPI_TICKET_KEY,
        value=data['ticket'],
        expire=WORK_WX_TOKEN_TIMEOUT,
    )

    return data['ticket']


async def get_wx_user_id(request: Request, code: str) -> str:
    data = await handle_wechat_api(GET_USER_ID, {
        'access_token': await get_wx_access_token(request),
        'code': code,
    })
    try:
        return data['UserId']
    except (KeyError, TypeError):
        return ''


# return name, work_number, mobile, u_id
async def get_wx_user_info(request: Request, user_id: str):
    data = await handle_wechat_api(GET_USER, {
        'access_token': await get_wx_access_token(request),
        'userid': user_id,
    })
    # 分割姓名和工号
    patter = search(r'\d+', data['name'])
    if patter:
        work_number = patter.group()
        data['name'] = data['name'].replace(work_number, '')
    else:
        work_number = ''
    return {
        'name': data['name'],
        'number': work_number,
        'mobile': data['mobile'],
        'wx_id': user_id,
    }


async def get_wx_user(request: Request, code: str) -> dict or None:
    if platform.system() == 'Darwin':  # for test
        return {
            'name': '邓楠跃',
            'number': '2370',
            'mobile': '13532227149',
            'wx_id': '4BF5E726A4173E6E10EBD34153A93688',
        }
    u_id = await get_wx_user_id(request, code)
    if u_id:
        return await get_wx_user_info(request, u_id)


async def handle_jsapi_config(request: Request, uri: str):
    """ 返回CONFIG的内容 """
    nonce_str = token_hex(16)
    jsapi_ticket = await get_wx_jsapi_ticket(request)
    timestamp = int(time())
    sha1 = hashlib.sha1()
    sha1.update(
        '&'.join([
            f'jsapi_ticket={jsapi_ticket}',
            f'noncestr={nonce_str}',
            f'timestamp={timestamp}',
            f'url={uri}'
        ]).encode())
    signature = sha1.hexdigest()
    return {
        'appId': CONFIG['wechat']['corpid'],
        'timestamp': timestamp,
        'nonceStr': nonce_str,
        'signature': signature
    }


if __name__ == '__main__':
    pass
