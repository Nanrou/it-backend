from aiohttp.web import Request, Response

from src.meta.permission import Permission
from src.meta.response_code import ResponseOk, MissRequiredFields
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

    try:
        page = int(request.query.get('page')) or 1
    except ValueError:
        return code_response(MissRequiredFields)

    cmd = "SELECT * FROM equipment"
    filter_params = []
    # 暂时不做单个部门的过滤
    # if request['jwt_content'].get('rol') & Permission.HIGHER:
    #     cmd = "SELECT * FROM equipment WHERE del_flag=0"
    # else:
    #     cmd = "SELECT * FROM equipment WHERE del_flag=0 AND department='{}'".format(
    #         request['jwt_content'].get('dep'))

    # 对过滤项进行组合处理
    for type_, col_format in zip(
        ['department', 'equipment', 'status'],
        ['department="{}"', 'category="{}"', 'status={}']
    ):
        if request.query.get(type_):
            _tmp = []
            for d in request.query.get(type_).split(','):
                _tmp.append(col_format.format(d))
            if len(_tmp) > 1:
                filter_params.append("({})".format(' OR '.join(_tmp)))
            elif len(_tmp) == 1:
                filter_params.append(_tmp[0])
    # if request.query.get('equipment'):
    #     _tmp = []
    #     for d in request.query.get('equipment').split(','):
    #         filter_params.append(f'category="{d}"')
    #     filter_params.append(' OR '.join(_tmp))
    # if request.query.get('status'):
    #     _tmp = []
    #     for d in request.query.get('status').split(','):
    #         filter_params.append(f'status={d}')
    #     filter_params.append(' OR '.join(_tmp))
    filter_part = ' AND '.join(filter_params)
    if request['jwt_content'].get('rol') & Permission.SUPER and request.query.get('all'):
        pass
    else:
        filter_part = 'del_flag=0' + (' AND ' if filter_part else '') + filter_part
    if filter_part:
        filter_part = ' WHERE ' + filter_part

    # 翻页逻辑
    cmd = cmd + filter_part + ' limit {}, {}'.format((page-1) * PAGE_SIZE, PAGE_SIZE)

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            # 计算总页数
            await cur.execute("SELECT COUNT(*) FROM equipment" + filter_part)
            sum_of_equipment = (await cur.fetchone())[0]
            total_page = sum_of_equipment // PAGE_SIZE
            if sum_of_equipment % PAGE_SIZE:
                total_page += 1

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
                    'user': row[10],
                    'owner': row[11],
                    'department': row[12],
                    'edit': row[13],
                    'del_flag': row[14],
                })
            await conn.commit()

    resp = code_response(ResponseOk, {
        'totalPage': total_page,
        'tableData': data
    })
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
                await cur.execute(f"SELECT {col} FROM equipment GROUP BY {col}")
                for row in await cur.fetchall():
                    res[type_].append({
                        'label': row[0],
                        'value': row[0]
                    })
            await conn.commit()

    return code_response(ResponseOk, res)
