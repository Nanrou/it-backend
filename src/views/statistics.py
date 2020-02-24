from datetime import datetime, timedelta

from aiohttp.web import Request

from src.meta.response_code import ResponseOk
from src.utls.toolbox import PrefixRouteTableDef, ItHashids, code_response, get_query_params

routes = PrefixRouteTableDef('/api/statistics')


# todo cache


@routes.get('/department')
async def stats_of_department(request: Request):
    # cmd = "SELECT `department`, count(*) FROM equipment"
    # filter_params = []
    filter_flag = False

    if request.query.get('department'):
        cmd = "SELECT `department`, count(*) FROM equipment"
        filter_params = []
        for _d in request.query.get('department').split(','):
            filter_params.append(f'`department`="{_d}"')
        if len(filter_params) > 1:
            filter_params = ' OR '.join(filter_params)
        elif len(filter_params) == 1:
            filter_params = filter_params[0]

        if filter_params:
            cmd += f' WHERE {filter_params}'
        cmd += ' GROUP BY `department`'
        filter_flag = True
    else:
        cmd = """\
SELECT j.ancestor, k.department, k.num
FROM (
    SELECT e.name AS ancestor, f.name AS department 
    FROM department_meta e 
    JOIN  (
        SELECT c.name, d.ancestor
        FROM department_meta c 
        JOIN
            (
            SELECT b.ancestor, a.depth, a.descendant
            FROM department_relation a
            LEFT JOIN (
                SELECT * FROM department_relation WHERE depth = 1
            ) b
            ON a.descendant = b.descendant
            WHERE a.ancestor = 1
            ) d
        ON c.id = d.descendant
        ) f
    ON e.id = f.ancestor
)  j
RIGHT JOIN (
    SELECT department, count(*) AS num 
    FROM equipment GROUP BY department
) k
ON j.department = k.department; \
"""

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            data = []
            count = 0
            await cur.execute(cmd)
            for row in await cur.fetchall():
                if filter_flag:
                    data.append({
                        'name': row[0],
                        'value': row[1]
                    })
                else:
                    data.append({
                        'ancestor': row[0] if row[0] and row[0] != '供水公司' else row[1],
                        'name': row[1],
                        'value': row[2]
                    })
                count += row[-1]
            await conn.commit()
    return code_response(ResponseOk, {'total': count, 'sourceData': data, 'doubleCircle': not filter_flag})


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
async def stats_of_department(request: Request):  # category: [...], department: [...], year: int
    cmd = "SELECT count(*) FROM equipment"
    filter_params = []
    # year
    _year = 5

    if request.query.get('year'):
        try:
            _year = int(request.query.get('year'))
        except ValueError:
            pass

    filter_params.append(
        '`purchasing_time`<"{}"'.format((datetime.now() - timedelta(days=_year * 365)).strftime("%Y-%m-%d")))

    # department
    for field in ('department', 'category'):
        if request.query.get(field):
            _tmp = request.query.get(field).split(',')
            if len(_tmp) > 0:
                filter_params.append('({})'.format(' OR '.join(['`{}`="{}"'.format(field, v) for v in _tmp])))

    filter_params = ' WHERE ' + ' AND '.join(filter_params)

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            # total, expiration = 0, 0
            await cur.execute(cmd)
            row = await cur.fetchone()
            total = row[0]
            await cur.execute(cmd + filter_params)
            row = await cur.fetchone()
            expiration = row[0]
            await conn.commit()
    data = [
        {
            "name": "超过{}年".format(_year),
            "value": expiration
        },
        {
            "name": "{}年以内".format(_year),
            "value": total - expiration
        },
    ]

    return code_response(ResponseOk, {'total': total, 'sourceData': data})


@routes.get('/preview')
async def preview_stats(request: Request):
    pass


@routes.get('/download')
async def download_stats(request: Request):
    pass