from urllib.parse import urlencode

from aiohttp import ClientSession, ClientTimeout, ServerTimeoutError, ContentTypeError
from aiohttp.web import Request

from src.settings import CONFIG

WORK_WX_TOKEN_KEY = "it:work:token"
WORK_WX_TOKEN_TIMEOUT = 7200
ACCESS_TOKEN_API = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
GET_USER_ID = "https://qyapi.weixin.qq.com/cgi-bin/user/getuserinfo"
GET_USER = "https://qyapi.weixin.qq.com/cgi-bin/user/get"


async def handle_wechat_api(base_url, params):
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


async def get_wx_user_id(request: Request, code: str) -> str:
    data = await handle_wechat_api(GET_USER_ID, {
        'access_token': await get_wx_access_token(request),
        'code': code,
    })
    try:
        return data['UserId']
    except (KeyError, TypeError):
        return ''


# return name, mobile, u_id
async def get_wx_user_info(request: Request, user_id: str):
    data = await handle_wechat_api(GET_USER, {
        'access_token': await get_wx_access_token(request),
        'userid': user_id,
    })
    return {
        'name': data['name'],
        'mobile': data['mobile'],
        'wx_id': user_id,
    }


async def get_wx_user(request: Request, code: str) -> dict or None:
    u_id = await get_wx_user_id(request, code)
    if u_id:
        return get_wx_user_info(request, u_id)


if __name__ == '__main__':
    uri = ACCESS_TOKEN_API + urlencode({
        'corpid': CONFIG['wechat']['corpid'],
        'corpsecret': CONFIG['wechat']['Secret'],
    })
    print(uri)
