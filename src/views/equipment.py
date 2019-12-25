from aiohttp.web import Request, Response

from src.meta.permission import Permission
from src.meta.response_code import ResponseOk
from src.utls.toolbox import PrefixRouteTableDef, ItHashids, code_response, get_query_params
from src.utls.common import set_cache_version, get_cache_version

routes = PrefixRouteTableDef('/api/equipment')

KEY_OF_VERSION = 'equipment'


def get_equipment_id(request: Request):
    return get_query_params(request, 'eid')


PAGE_SIZE = 10


@routes.get('/query')
async def query(request: Request):
    # 不做304
    # 判断root，且不做304

    filter_params = []
    page = request.query.get('page') or 1
    if request['jwt_content'].get('rol') & Permission.SUPER and request.query.get('all'):
        cmd = "SELECT * FROM equipment"
        pass
    else:
        filter_params.append('del_flag=0')
        cmd = "SELECT * FROM equipment WHERE "
        # 暂不做global
        if request['jwt_content'].get('rol') & Permission.HIGHER:
            cmd = "SELECT * FROM equipment WHERE del_flag=0"
        else:
            cmd = "SELECT * FROM equipment WHERE del_flag=0 AND department='{}'".format(
                request['jwt_content'].get('dep'))

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(cmd)
            data = []
            for row in await cur.fetchall():
                data.append({
                    'eid': ItHashids.encode(row[0]),
                    'category': row[1],
                    'brand': row[2],
                    'modelNumber': row[3],
                    'serialNumber': row[4],
                    'price': row[5],
                    'purchasingTime': row[6].strftime('%Y-%m-%d'),
                    'guarantee': row[7],
                    'remark': row[8],
                    'status': row[9],
                    'user': row[11],
                    'owner': row[12],
                    'department': row[13],
                    'edit': row[14],
                    'del_flag': row[15],
                })
            await conn.commit()

    resp = code_response(ResponseOk, data)
    resp.set_cookie(f'{KEY_OF_VERSION}-version', await get_cache_version(request, KEY_OF_VERSION))
    return resp


@routes.get('/options')
async def query_options(request: Request):
    res = {
        'department': [],
        'equipment': []
    }
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            for col, type_ in zip(['department', 'category'], ['department', 'equipment']):
                # group by 出过滤项
                await cur.execute(f"SELECT {col} FROM equipment GROUPBY {col}")
                for row in await cur.fetchall():
                    res[type_].append({
                        'label': row[0],
                        'value': row[0]
                    })
            await conn.commit()

    return code_response(ResponseOk, res)
