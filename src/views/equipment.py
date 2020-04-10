from datetime import datetime
from io import BytesIO

from aiohttp.web import Request, Response
from pymysql.err import IntegrityError

from src.meta.permission import Permission
from src.meta.response_code import ResponseOk, MissRequiredFieldsResponse, MissComputerHardwareResponse, \
    InvalidFormFIELDSResponse, RepetitionHardwareResponse
from src.utls.toolbox import PrefixRouteTableDef, ItHashids, code_response, get_query_params
from src.utls.common import set_cache_version, get_cache_version, get_qrcode

routes = PrefixRouteTableDef('/api/equipment')

PAGE_SIZE = 10
KEY_OF_VERSION = 'equipment'
EQUIPMENT_FIELDS = {
    'category',
    'brand',
    'model_number',
    'serial_number',
    'price',
    'purchasing_time',
    'guarantee',
    'remark',
    'status',
    'user',
    'admin',
    'department',
    'edit',
}
HARDWARE_FIELDS = {
    # 'eid',
    'ipAddress': 'ip_address',
    'cpu': 'cpu',
    'gpu': 'gpu',
    'disk': 'disk',
    'memory': 'memory',
    'mainBoard': 'main_board',
    'remark': 'remark',
}
StatusText = {
    0: "正常",
    2: "备用",
    3: "报废"
}


def get_equipment_id(request: Request, decode=True):
    return get_query_params(request, 'eid', decode)


@routes.get('/query')
async def query(request: Request):
    # 不做304
    # 判断root，且不做304

    try:
        page = int(request.query.get('page')) if request.query.get('page') else 1
    except ValueError:
        return code_response(MissRequiredFieldsResponse)

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
    cmd = cmd + filter_part + ' limit {}, {}'.format((page - 1) * PAGE_SIZE, PAGE_SIZE)

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


@routes.get('/queryWithoutPagination')
async def query_without_pagination(request: Request):
    # 不做304
    # 判断root，且不做304

    cmd = "SELECT * FROM equipment"
    filter_params = []

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
    filter_part = ' AND '.join(filter_params)
    if request['jwt_content'].get('rol') & Permission.SUPER and request.query.get('all'):
        pass
    else:
        filter_part = 'del_flag=0' + (' AND ' if filter_part else '') + filter_part

    if filter_part:
        filter_part = ' WHERE ' + filter_part

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(cmd + filter_part)
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

    resp = code_response(ResponseOk, data)
    return resp

# todo 规整部门，做成树状，有上下级关系
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


@routes.post('/add')
async def create(request: Request):
    data = await request.json()
    cmd = """\
INSERT INTO equipment (
    category,
    brand,
    model_number,
    serial_number,
    price,
    purchasing_time,
    guarantee,
    remark,
    status,
    user,
    `owner`,
    department,
    `edit`
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\
"""
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            _edit = request['jwt_content'].get('name')
            await cur.execute(cmd, (
                data.get('category'),
                data.get('brand'),
                data.get('modelNumber'),
                data.get('serialNumber'),
                data.get('price'),
                data.get('purchasingTime'),
                data.get('guarantee'),
                data.get('remark'),
                data.get('status'),
                data.get('user'),
                data.get('admin'),
                data.get('department'),
                _edit,
            ))

            _eid = cur.lastrowid
            _content = '{} {} 创建了设备编号为 {} 的设备记录'.format(
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'), _edit, _eid
            )
            await cur.execute("INSERT INTO edit_history (eid, content, edit) VALUES (%s, %s, %s)",
                              (_eid, _content, _edit))
            if data.get('category') == '台式电脑' and data.get('detail'):
                _detail = data.get('detail')
                _cmd = """\
INSERT INTO computer_detail (
    eid,
    ip_address,
    cpu,
    gpu,
    disk,
    `memory`,
    main_board,
    remark
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)\
"""
                await cur.execute(_cmd, (
                    _eid,
                    _detail.get('ipAddress'),
                    _detail.get('cpu'),
                    _detail.get('gpu'),
                    _detail.get('disk'),
                    _detail.get('memory'),
                    _detail.get('main_board'),
                    _detail.get('remark')
                ))

            await conn.commit()
    await set_cache_version(request, KEY_OF_VERSION)
    return code_response(ResponseOk)


@routes.patch('/update')
async def update(request: Request):  # data {key: [new, old]}
    _eid = get_equipment_id(request)

    data = await request.json()
    try:
        assert all(field in EQUIPMENT_FIELDS for field in data)
    except AssertionError:
        return code_response(InvalidFormFIELDSResponse)

    _edit = request['jwt_content'].get('name')
    fields = tuple(data.keys())
    cmd = "UPDATE equipment SET {}, `edit`=%s WHERE id=%s".format(','.join([f'`{field}`=%s' for field in fields]))

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(cmd, [data[field][0] for field in fields] + [_edit, _eid])
            _content = '{} {} 修改了设备编号为 {} 的设备记录：{}'.format(
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'), _edit, _eid,
                ', '.join(['{category}: {old} => {_new}'.format(category=field, old=data[field][1], _new=data[field][0])
                           for field in fields])
            )
            await cur.execute("INSERT INTO edit_history (eid, content, edit) VALUES (%s, %s, %s)",
                              (_eid, _content, _edit))

            await conn.commit()
    await set_cache_version(request, KEY_OF_VERSION)
    return code_response(ResponseOk)


@routes.patch('/scrap')
async def scrap(request: Request):
    _eid = get_equipment_id(request)

    _edit = request['jwt_content'].get('name')

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE equipment SET status=3, edit=%s WHERE id=%s",
                              (_edit, _eid))
            _content = '{} {} 报废了设备编号为 {} 的设备'.format(
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'), _edit, _eid
            )
            await cur.execute("INSERT INTO edit_history (eid, content, edit) VALUES (%s, %s, %s)",
                              (_eid, _content, _edit))

            await conn.commit()
    await set_cache_version(request, KEY_OF_VERSION)
    return code_response(ResponseOk)


@routes.delete('/remove')
async def delete(request: Request):
    _eid = get_equipment_id(request)

    _edit = request['jwt_content'].get('name')

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE equipment SET del_flag=1, edit=%s WHERE id=%s",
                              (_edit, _eid))
            _content = '{} {} 删除了设备编号为 {} 的设备记录'.format(
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'), _edit, _eid
            )
            await cur.execute("INSERT INTO edit_history (eid, content, edit) VALUES (%s, %s, %s)",
                              (_eid, _content, _edit))

            await conn.commit()
    await set_cache_version(request, KEY_OF_VERSION)
    return code_response(ResponseOk)


@routes.patch('/changeStatus')
async def change_status(request: Request):
    _eid = get_equipment_id(request)

    _edit = request['jwt_content'].get('name')

    try:
        data = await request.json()
        if data['status'] == 0:
            cmd = "UPDATE equipment SET status=0, user=%s, owner=%s, department=%s, edit=%s WHERE id=%s"
            params = (data['user'], data['owner'], data['department'], _edit, _eid)
        elif data['status'] in (2, 3):
            cmd = f"UPDATE equipment SET status={data['status']}, user='', owner='', department='', edit=%s WHERE id=%s"
            params = (_edit, _eid)
        else:
            return code_response(InvalidFormFIELDSResponse)
        async with request.app['mysql'].acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(cmd, params)
                _content = '{} {} 将设备编号为 {} 的设备设置为 {} 状态'.format(
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'), _edit, _eid, StatusText[data['status']]
                )
                await cur.execute("INSERT INTO edit_history (eid, content, edit) VALUES (%s, %s, %s)",
                                  (_eid, _content, _edit))

                await conn.commit()
        await set_cache_version(request, KEY_OF_VERSION)
        return code_response(ResponseOk)
    except KeyError:
        return code_response(InvalidFormFIELDSResponse)


@routes.get('/qrcode')
async def equipment_qrcode(request: Request):
    qr_io = BytesIO()
    get_qrcode(get_equipment_id(request, decode=False)).save(qr_io)
    return Response(body=qr_io.getvalue(), headers={'Content-Type': 'image/png'})


@routes.get('/hardware')
async def query_hardware(request: Request):
    _eid = get_equipment_id(request)
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM computer_detail WHERE eid=%s", (_eid,))
            try:
                row = await cur.fetchone()
                data = {
                    # 'hid': row[0],
                    # 'eid': row[1],
                    'ipAddress': row[2],
                    'cpu': row[3],
                    'gpu': row[4],
                    'disk': row[5],
                    'memory': row[6],
                    'mainBoard': row[7],
                    'remark': row[8]
                }
            except (IndexError, TypeError):
                return code_response(MissComputerHardwareResponse)
            finally:
                await conn.commit()
    return code_response(ResponseOk, data)


@routes.post('/hardware')
async def create_hardware(request: Request):
    _eid = get_equipment_id(request)
    data = await request.json()
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            _cmd = """\
    INSERT INTO computer_detail (
        eid,
        ip_address,
        cpu,
        gpu,
        disk,
        `memory`,
        main_board,
        remark
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)\
    """
            try:
                await cur.execute(_cmd, (
                    _eid,
                    data.get('ipAddress'),
                    data.get('cpu'),
                    data.get('gpu'),
                    data.get('disk'),
                    data.get('memory'),
                    data.get('main_board'),
                    data.get('remark')
                ))
            except IntegrityError:
                return code_response(RepetitionHardwareResponse)
            finally:
                await conn.commit()
    return code_response(ResponseOk)


@routes.patch('/hardware')
async def update_hardware(request: Request):  # data {key: [new, old]}
    _eid = get_equipment_id(request)
    data = await request.json()
    try:
        assert all(field in HARDWARE_FIELDS for field in data)
    except AssertionError:
        return code_response(InvalidFormFIELDSResponse)
    fields = tuple(data.keys())

    _edit = request['jwt_content'].get('name')
    cmd = "UPDATE computer_detail SET {} WHERE eid=%s".format(','.join([f'`{HARDWARE_FIELDS[field]}`=%s' for field in fields]))
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(cmd, [data[field][0] for field in fields] + [_eid])
            _content = '{} {} 修改了设备编号为 {} 的硬件配置：{}'.format(
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'), _edit, _eid,
                ', '.join(['{category}: {old} => {_new}'.format(category=HARDWARE_FIELDS[field], old=data[field][1],
                                                                _new=data[field][0]) for field in fields])
            )
            await cur.execute("INSERT INTO edit_history (eid, content, edit) VALUES (%s, %s, %s)",
                              (_eid, _content, _edit))
            await conn.commit()
    return code_response(ResponseOk)


@routes.get('/detail')
async def equipment_detail(request: Request):
    _eid = get_equipment_id(request)
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM equipment WHERE `id`=%s", (_eid,))
            row = await cur.fetchone()
            res = {
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
            }
            await conn.commit()
    return code_response(ResponseOk, res)


# todo 清单导出功能
