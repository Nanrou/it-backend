from datetime import datetime, timedelta

from aiohttp.web import Request

from src.meta.response_code import ResponseOk
from src.utls.toolbox import PrefixRouteTableDef, ItHashids, code_response, get_query_params

routes = PrefixRouteTableDef('/api/statistics')


@routes.get('/department')
async def stats_of_department(request: Request):

    cmd = "SELECT `department`, count(*) FROM equipment"
    filter_params = []

    if request.query.get('department'):
        for _d in request.query.get('department').split(','):
            filter_params.append(f'`department`="{_d}"')
        if len(filter_params) > 1:
            filter_params = ' OR '.join(filter_params)
        elif len(filter_params) == 1:
            filter_params = filter_params[0]

        if filter_params:
            cmd += f' WHERE {filter_params}'
    cmd += ' GROUP BY `department`'

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            data = []
            count = 0
            await cur.execute(cmd)
            for row in await cur.fetchall():
                data.append({
                    'name': row[0],
                    'value': row[1]
                })
                count += row[1]
            await conn.commit()

    return code_response(ResponseOk, {'total': count, 'sourceData': data})


@routes.get('/category')
async def stats_of_category(request: Request):

    cmd = "SELECT `category`, count(*) FROM equipment"
    filter_params = []

    if request.query.get('category'):
        for _d in request.query.get('category').split(','):
            filter_params.append(f'`category`="{_d}"')
        if len(filter_params) > 1:
            filter_params = ' OR '.join(filter_params)
        elif len(filter_params) == 1:
            filter_params = filter_params[0]

        if filter_params:
            cmd += f' WHERE {filter_params}'
    cmd += ' GROUP BY `category`'

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            data = []
            count = 0
            await cur.execute(cmd)
            for row in await cur.fetchall():
                data.append({
                    'name': row[0],
                    'value': row[1]
                })
                count += row[1]
            await conn.commit()

    return code_response(ResponseOk, {'total': count, 'sourceData': data})


@routes.get('/purchasingTime')
async def stats_of_department(request: Request):
    # todo department
    cmd = "SELECT count(*) FROM equipment WHERE (`category`='台式电脑' OR `category`='笔记本电脑')"
    filter_params = ' AND `purchasing_time`<"{}"'
    _year = 7

    if request.query.get('year'):
        try:
            _year = int(request.query.get('year'))
        except ValueError:
            pass

    filter_params.format((datetime.now() - timedelta(days=_year * 365)).strftime("%Y-%m-%d"))

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            # total, expiration = 0, 0
            await cur.execute(cmd)
            row = await cur.fetchone()
            total = row[0]
            await cur.execute(cmd + filter_params)
            expiration = row[0]
            await conn.commit()

    return code_response(ResponseOk, {'total': total, 'expiration': expiration})
