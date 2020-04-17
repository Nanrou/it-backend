from aiohttp.web import Request, Response

from src.meta.permission import Permission
from src.meta.response_code import ResponseOk
from src.utls.toolbox import PrefixRouteTableDef, Tree, code_response, get_query_params
from src.utls.common import set_cache_version, get_cache_version

routes = PrefixRouteTableDef('/api/organization')

KEY_OF_VERSION = 'organization'


@routes.get('/query')
async def query(request: Request):
    """ relation的cache分两类，无后缀的是全局，细分的话后缀是部门 """
    # 检查cache，全局是局部的充分条件
    # if request['jwt_content'].get('rol') & Permission.SUPER:
    #     pass
    # elif request.cookies.get(f'{KEY_OF_VERSION}-version') and (request.cookies.get(
    #         f'{KEY_OF_VERSION}-version') == await get_cache_version(request, KEY_OF_VERSION)):
    #     return Response(status=304)

    ancestor = request.query.get('ancestor') if request.query.get('ancestor') else 1

    tree = Tree(pool=request.app['mysql'])
    resp = code_response(ResponseOk, await tree.get_children_node(ancestor, False))
    resp.set_cookie(f'{KEY_OF_VERSION}-version', await get_cache_version(request, KEY_OF_VERSION))
    return resp


@routes.post('/add')
async def add(request: Request):
    tree = Tree(pool=request.app['mysql'])
    data = await request.json()
    await tree.add_node(data['label'], data['parentId'])
    await set_cache_version(request, KEY_OF_VERSION)
    return code_response(ResponseOk)


def get_organization_id(request: Request):
    return get_query_params(request, 'did')


@routes.patch('/update')
async def update(request: Request):
    tree = Tree(pool=request.app['mysql'])
    data = await request.json()
    await tree.update_node(get_organization_id(request), data['label'])
    await set_cache_version(request, KEY_OF_VERSION)
    return code_response(ResponseOk)


@routes.delete('/remove')
async def remove(request: Request):
    tree = Tree(pool=request.app['mysql'])
    await tree.delete_node(get_organization_id(request))
    await set_cache_version(request, KEY_OF_VERSION)
    return code_response(ResponseOk)
