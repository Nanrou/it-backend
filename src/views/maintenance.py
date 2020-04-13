from datetime import datetime
from json import JSONDecodeError

from aiohttp.web import Request
from aiohttp.web_exceptions import HTTPForbidden
from pymysql.err import IntegrityError

from src.meta.permission import Permission
from src.meta.response_code import ResponseOk, MissRequiredFieldsResponse, ConflictStatusResponse, \
    InvalidFormFIELDSResponse, InvalidCaptchaResponse, RepetitionOrderIdResponse, InvalidWorkerInformationResponse, \
    EmtpyPatrolPlanResponse, OrderMissContentResponse, DispatchSuccessWithoutSendEmailResponse, \
    MissEmailContentResponse, SendEmailTimeoutResponse, AlreadySendEmailResponse, SmsLimitResponse, SendSmsErrorResponse
from src.views.equipment import get_equipment_id
from src.meta.exception import SmsLimitException
from src.utls.toolbox import PrefixRouteTableDef, ItHashids, code_response, get_query_params
from src.utls.common import get_cache_version, send_maintenance_order_email, check_sms_captcha, create_captcha, \
    send_patrol_email, send_sms

routes = PrefixRouteTableDef('/api/maintenance')

PAGE_SIZE = 10
KEY_OF_VERSION = 'maintenance'
TABLE_NAME = '`order`'
ORDER_ID_EXPIRE_TIME = 60 * 60 * 24  # 记录当天的条数 order id 的过期时间，就是一天
# REPORT_FORM_FIELDS = {'name': 'name', 'phone': 'phone', 'reason': 'reason',
#                       'remark': 'remark', 'captcha': 'captcha'}
# APPRAISAL_FORM_FIELDS = {'name': 'name', 'phone': 'phone', 'rank': 'rank',
#                          'remark': 'remark', 'captcha': 'captcha'}
REPORT_FORM_FIELDS = {'name', 'phone', 'reason', 'remark', 'captcha', 'workNumber'}
APPRAISAL_FORM_FIELDS = {'name', 'phone', 'rank', 'remark', 'captcha'}
REMOTE_HANDLE_FIELDS = {'eid', 'method', 'remark'}
MAINTENANCE_STATUS = 1


def get_maintenance_id(request: Request):
    return get_query_params(request, 'oid')


@routes.get('/query')
async def query(request: Request):
    try:
        page = int(request.query.get('page')) or 1
    except ValueError:
        return code_response(MissRequiredFieldsResponse)

    cmd = f"SELECT * FROM {TABLE_NAME}"
    filter_params = []
    # 暂时不做单个部门的过滤

    # 对过滤项进行组合处理
    for type_, col_format in zip(
            ['department', 'equipment', 'status'],
            ['department="{}"', 'category="{}"', 'status="{}"']  # 注意这里，equipment的status是int，maintenance是string
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

    # 翻页逻辑
    cmd += filter_part
    cmd += ' ORDER BY id DESC' + ' limit {}, {}'.format((page - 1) * PAGE_SIZE, PAGE_SIZE)

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            # 计算总页数
            await cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}" + filter_part)
            sum_of_equipment = (await cur.fetchone())[0]
            total_page = sum_of_equipment // PAGE_SIZE
            if sum_of_equipment % PAGE_SIZE:
                total_page += 1

            await cur.execute(cmd)
            data = []
            for row in await cur.fetchall():
                data.append({
                    'oid': ItHashids.encode(row[0]),
                    'orderId': row[1],
                    'status': row[2],
                    'pid': ItHashids.encode(row[3]) if row[3] else row[3],
                    'name': row[4],
                    'eid': ItHashids.encode(row[5]),
                    'equipment': row[6],
                    'department': row[7],
                    # 'content': row[8],
                    'reason': row[9],
                    'rank': row[10],
                    'del_flag': row[11],
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
            for type_ in ['department', 'equipment']:
                # group by 出过滤项
                await cur.execute(f"SELECT {type_} FROM {TABLE_NAME} GROUP BY {type_}")
                for row in await cur.fetchall():
                    res[type_].append({
                        'label': row[0],
                        'value': row[0]
                    })
            await conn.commit()
    return code_response(ResponseOk, res)


@routes.get('/workers')
async def get_maintenance_workers(request: Request):
    res = []
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"SELECT `id`, `name`, `phone`, `email`, `role` FROM profile WHERE role & {Permission.MAINTENANCE}")
            for row in await cur.fetchall():
                if row[-1] & Permission.SUPER:
                    continue
                res.append({
                    "pid": ItHashids.encode(row[0]),
                    "name": row[1],
                    "phone": row[2],
                    "email": row[3],
                })
    return code_response(ResponseOk, res)


async def get_order_id(request: Request):
    """ 获取当前order id，已经加 1 的了 """
    _date_str = datetime.now().strftime('%Y%m%d')
    order_id = await request.app['redis'].get(f'it:orderID:{_date_str}')
    if order_id is None:
        async with request.app['mysql'].acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM {} WHERE order_id LIKE '{}%'".format(TABLE_NAME, _date_str))
                order_id = await cur.fetchone()
                await conn.commit()
        order_id = order_id[0]
    # await request.app['redis'].set(f'it:orderID:{_date_str}', int(order_id) + 1, 3600)  # +1
    return '{date}{oid:0>3}'.format(date=_date_str, oid=int(order_id) + 1)


async def set_order_id(request: Request, order_id: str):
    await request.app['redis'].set(
        key='it:orderID:{}'.format(order_id[:-3]),
        value=order_id[-3:],
        expire=ORDER_ID_EXPIRE_TIME,
    )


# 写入order history
H_CMD = """\
INSERT INTO order_history (
    oid,
    status,
    `name`,
    phone,
    remark,
    content
) VALUES (%s, %s, %s, %s, %s, %s)\
"""

# 写入equipment history
E_CMD = "INSERT INTO edit_history (eid, content, edit) VALUES (%s, %s, %s)"

STATUS = ('R', 'D', 'H', 'E', 'F', 'C')


async def handle_order_history(cursor, oid, status, edit, phone, remark, content):
    """ 写入order history """
    assert status in STATUS
    await cursor.execute(H_CMD, (oid, status, edit, phone, remark, content))


async def handle_equipment_history(cursor, eid, edit, content):
    """ 写入equipment history """
    await cursor.execute(E_CMD, (eid, content, edit))


@routes.get('/flow')
async def get_flow(request: Request):
    """ 获取工作流 """
    _oid = get_maintenance_id(request)
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT status, content FROM `order_history` WHERE oid=%s", (_oid,))
            res = []
            for row in await cur.fetchall():
                res.append({
                    'status': row[0],
                    'content': row[1]
                })
            await conn.commit()
    return code_response(ResponseOk, res)


@routes.post('/report')
async def report_order(request: Request):  # {eid, reportForm}
    try:
        _data = await request.json()
        _eid = ItHashids.decode(_data['eid'])
        _report_form = _data['reportForm']
        assert all(k in REPORT_FORM_FIELDS for k in _report_form)
    except (KeyError, AssertionError, JSONDecodeError):
        return code_response(InvalidFormFIELDSResponse)
    _time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 不上传验证码时就不检验了
    if _report_form.get('captcha') == '' or await check_sms_captcha(request, _eid, _report_form['phone'],
                                                                    _report_form['captcha']):
        async with request.app['mysql'].acquire() as conn:
            async with conn.cursor() as cur:
                # 确认设备状态为正常
                await cur.execute("SELECT `department`, `category` FROM equipment WHERE `id`=%s AND `status`=0",
                                  (_eid,))
                if cur.rowcount == 0:
                    return code_response(ConflictStatusResponse)
                else:
                    row = await cur.fetchone()
                    _department = row[0]
                    _equipment = row[1]
                    _content = "{time} {department} {name}({phone}) 上报了 {equipment} 故障，原因是{reason}".format(
                        time=_time_str, department=_department, name=_report_form['name'],
                        phone=_report_form['phone'], equipment=_equipment, reason=_report_form['reason']
                    )
                    _edit = _report_form['name']
                    try:
                        _order_id = await get_order_id(request)
                        m_cmd = """\
                        INSERT INTO `order` (
                            order_id,
                            eid,
                            equipment,
                            department,
                            content,
                            reason
                        ) VALUES (%s, %s, %s, %s, %s, %s)\
                        """
                        await cur.execute(m_cmd, (
                            _order_id, _eid, _equipment, _department, _content, _report_form['reason']))
                    except IntegrityError:
                        return code_response(RepetitionOrderIdResponse)
                    _last_row_id = cur.lastrowid
                    await handle_order_history(cur, _last_row_id, 'R', _report_form['name'], _report_form['phone'],
                                               _report_form.get('remark'), _content)
                    # await cur.execute(H_CMD, (
                    #     _last_row_id, 'R', _report_form['name'], _report_form['phone'], _report_form.get('remark'),
                    #     _content))
                    # 更新equipment
                    # await cur.execute("UPDATE equipment SET oid=%s, status=1, edit=%s WHERE id=%s",
                    #                   (_last_row_id, _edit, _eid))
                    await cur.execute("UPDATE equipment SET status=1, edit=%s WHERE id=%s",
                                      (_edit, _eid))
                    await handle_equipment_history(cur, _eid, _edit,
                                                   '{} {} 上报了编号为 {} 的设备故障'.format(_time_str, _edit, _eid))
                    # await cur.execute("INSERT INTO edit_history (eid, content, edit) VALUES (%s, %s, %s)",
                    #                   (_eid,
                    #                    '{} {} 上报了编号为 {} 的设备故障'.format(_time_str, _edit, _eid),
                    #                    _edit))
                    await conn.commit()

                # 更新redis中的order id和order版本
                # await set_cache_version(request, 'order')
                # await set_cache_version(request, 'equipment')
                return code_response(ResponseOk)
    else:
        return code_response(InvalidCaptchaResponse)


@routes.post('/create')
async def create_order(request: Request):
    pass


@routes.get('/captcha')
async def get_captcha(request: Request):
    _eid = get_equipment_id(request)
    try:
        _phone = request.query['phone']
    except KeyError:
        raise HTTPForbidden(text='Miss phone')

    try:
        await send_sms(request, _eid, _phone)
    except RuntimeError:
        return code_response(SendSmsErrorResponse)
    except SmsLimitException:
        return code_response(SmsLimitResponse)

    return code_response(ResponseOk)


@routes.patch('/remote')
async def remote_handle(request: Request):  # data {eid, method, remark}
    """ R -> E 远程解决问题 """
    _oid = get_maintenance_id(request)
    data = await request.json()
    try:
        assert all(k in data for k in REMOTE_HANDLE_FIELDS)
    except AssertionError:
        return code_response(InvalidFormFIELDSResponse)
    _time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    _eid = ItHashids.decode(data['eid'])
    _phone = request['jwt_content'].get('pho')
    _edit = request['jwt_content'].get('name')
    _pid = ItHashids.decode(request['jwt_content'].get('uid'))
    _content = "{time} {name}({phone}) 远程解决了故障".format(
        time=_time_str, name=_edit, phone=_phone
    )
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            # todo 将更新状态抽象出来
            # 更新order
            m_cmd = f"UPDATE {TABLE_NAME} SET status='E', pid=%s, name=%s, content=%s WHERE id=%s AND status='R'"
            await cur.execute(m_cmd, (_pid, _edit, _content, _oid))
            if cur.rowcount == 0:
                return code_response(ConflictStatusResponse)
            # 更新equipment
            await cur.execute("UPDATE equipment SET status=0, edit=%s WHERE id=%s AND status=1", (_edit, _eid))
            if cur.rowcount == 0:
                return code_response(ConflictStatusResponse)
            await handle_order_history(cur, _oid, 'E', _edit, _phone, f"{data['method']}|{data['remark']}", _content)
            # await cur.execute(H_CMD, (_oid, 'E', _edit, _phone, f"{data['method']}|{data['remark']}", _content))
            await handle_equipment_history(cur, _eid, _edit, '{} {} 修复设备故障'.format(_time_str, _edit))
            # await cur.execute("INSERT INTO edit_history (eid, content, edit) VALUES (%s, %s, %s)",
            #                   (_eid,
            #                    '{} {} 修复设备故障'.format(_time_str, _edit),
            #                    _edit))
            await conn.commit()
    return code_response(ResponseOk)


@routes.patch('/dispatch')
async def dispatch(request: Request):  # data { worker: {pid, name, phone, email}, remark }
    """ R -> D 派单 """
    _oid = get_maintenance_id(request)
    data = await request.json()

    _time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        _worker = data['worker']
        _pid = ItHashids.decode(_worker['pid'])
        _edit = request['jwt_content'].get('name')
        _order_id = data['orderId']
        _content = "{time} {name} 将工单分派给了 {worker}".format(
            time=_time_str, name=_edit, worker=_worker['name']
        )
    except KeyError:
        return code_response(InvalidFormFIELDSResponse)

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            # 更新order
            m_cmd = f"UPDATE {TABLE_NAME} SET status='D', pid=%s, name=%s, content=%s WHERE id=%s AND status='R'"
            await cur.execute(m_cmd, (_pid, _worker['name'], _content, _oid))
            if cur.rowcount == 0:
                return code_response(ConflictStatusResponse)
            await handle_order_history(cur, _oid, 'D', _worker['name'], None, data.get('remark'), _content)
            # await cur.execute(H_CMD, (_oid, 'D', _worker['name'], None, data.get('remark'), _content))
            # 应该在history中记录被指派人的信息
            await conn.commit()
    try:
        await send_maintenance_order_email(request, _oid, _order_id, create_captcha(), _worker['email'])
    except RuntimeError:
        return code_response(OrderMissContentResponse)
    except TimeoutError:
        return code_response(DispatchSuccessWithoutSendEmailResponse)
    return code_response(ResponseOk)


@routes.patch('/arrival')
async def arrival(request: Request):  # data { name, phone, remark }
    """ D -> H 到达现场并开始处理 """
    _oid = get_maintenance_id(request)
    data = await request.json()

    _time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        _edit = data['name']
        _phone = data['phone']
        _content = "{time} {name}({phone}) 到达现场进行处理".format(
            time=_time_str, name=_edit, phone=_phone,
        )
    except KeyError:
        return code_response(InvalidFormFIELDSResponse)

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            # 校验预留信息
            o_cmd = f"SELECT pid FROM {TABLE_NAME} WHERE id=%s"
            await cur.execute(o_cmd, (_oid,))
            if cur.rowcount == 0:
                return code_response(InvalidWorkerInformationResponse)
            row = await cur.fetchone()
            try:
                p_cmd = "SELECT name, phone FROM `profile` WHERE id=%s"
                await cur.execute(p_cmd, (row[0],))
                if cur.rowcount == 0:
                    return code_response(InvalidWorkerInformationResponse)
                row = await cur.fetchone()
                if row[0] != _edit or row[1] != _phone:
                    return code_response(InvalidWorkerInformationResponse)
            except IndexError:
                return code_response(InvalidWorkerInformationResponse)
            # 更新order
            m_cmd = f"UPDATE {TABLE_NAME} SET status='H', content=%s WHERE id=%s AND status='D'"
            await cur.execute(m_cmd, (_content, _oid))
            if cur.rowcount == 0:
                return code_response(ConflictStatusResponse)
            await handle_order_history(cur, _oid, 'H', _edit, _phone, data.get('remark'), _content)
            # await cur.execute(H_CMD, (_oid, 'H', _edit, _phone, data.get('remark'), _content))
            await conn.commit()

    return code_response(ResponseOk)


@routes.patch('/fix')
async def fix(request: Request):  # data { name, phone, remark }
    """ H -> E 到达现场并开始处理 """
    _oid = get_maintenance_id(request)
    _eid = get_equipment_id(request)
    data = await request.json()

    _time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        _edit = data['name']
        _phone = data['phone']
        _content = "{time} {name}({phone}) 已解决上报问题".format(
            time=_time_str, name=_edit, phone=_phone,
        )
    except KeyError:
        return code_response(InvalidFormFIELDSResponse)

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            # 校验预留信息
            o_cmd = f"SELECT pid FROM {TABLE_NAME} WHERE id=%s"
            await cur.execute(o_cmd, (_oid,))
            if cur.rowcount == 0:
                return code_response(InvalidWorkerInformationResponse)
            row = await cur.fetchone()
            try:
                p_cmd = "SELECT name, phone FROM `profile` WHERE id=%s"
                await cur.execute(p_cmd, (row[0],))
                if cur.rowcount == 0:
                    return code_response(InvalidWorkerInformationResponse)
                row = await cur.fetchone()
                if row[0] != _edit or row[1] != _phone:
                    return code_response(InvalidWorkerInformationResponse)
            except IndexError:
                return code_response(InvalidWorkerInformationResponse)
            # 更新order
            m_cmd = f"UPDATE {TABLE_NAME} SET `status`='E', `content`=%s WHERE id=%s AND status='H'"
            await cur.execute(m_cmd, (_content, _oid))
            if cur.rowcount == 0:
                return code_response(ConflictStatusResponse)
            # 更新equipment
            await cur.execute("UPDATE equipment SET status=0, edit=%s WHERE id=%s AND status=0", (_edit, _eid))
            if cur.rowcount == 0:
                return code_response(ConflictStatusResponse)
            await handle_order_history(cur, _oid, 'E', _edit, _phone, data.get('remark'), _content)
            # await cur.execute(H_CMD, (_oid, 'E', _edit, _phone, data.get('remark'), _content))
            await handle_equipment_history(cur, _eid, _edit, '{} {} 修复设备故障'.format(_time_str, _edit))
            # await cur.execute("INSERT INTO edit_history (eid, content, edit) VALUES (%s, %s, %s)",
            #                   (_eid,
            #                    '{} {} 修复设备故障'.format(_time_str, _edit),
            #                    _edit))
            await conn.commit()

    return code_response(ResponseOk)


@routes.patch('/appraisal')
async def appraisal(request: Request):
    """ E -> F 评分，结束工单 """
    _oid = get_maintenance_id(request)
    try:
        _appraisal_form = await request.json()
        assert all(k in APPRAISAL_FORM_FIELDS for k in _appraisal_form)
    except (KeyError, AssertionError, JSONDecodeError):
        return code_response(InvalidFormFIELDSResponse)

    if await check_sms_captcha(request, _oid, _appraisal_form['phone'], _appraisal_form['captcha']):
        _time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        _name = _appraisal_form['name']
        _phone = _appraisal_form['phone']
        _rank = _appraisal_form['rank']
        _content = "{time} {name}({phone})对工单打了{rank}分评价".format(
            time=_time_str, name=_name, phone=_phone, rank=_rank
        )
        async with request.app['mysql'].acquire() as conn:
            async with conn.cursor() as cur:
                # 更新order
                m_cmd = f"UPDATE {TABLE_NAME} SET `status`='F', `rank`=%s, `content`=%s WHERE `id`=%s AND `status`='E'"
                await cur.execute(m_cmd, (_rank, _content, _oid))
                if cur.rowcount == 0:
                    return code_response(ConflictStatusResponse)
                await handle_order_history(cur, _oid, 'F', _name, _phone, _appraisal_form.get('remark'), _content)
                # await cur.execute(H_CMD, (_oid, 'F', _name, _phone, _appraisal_form.get('remark'), _content))
                await conn.commit()
        return code_response(ResponseOk)
    else:
        return code_response(InvalidCaptchaResponse)


@routes.patch('/cancel')
async def cancel(request: Request):  # data { name, phone, remark, captcha }
    """ *(E/F) -> C 取消工单 """
    _oid = get_maintenance_id(request)
    _eid = get_equipment_id(request)
    data = await request.json()

    _time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        _edit = data['name']
        _phone = data['phone']
        _captcha = data['captcha']
        _content = "{time} {name}({phone}) 已取消工单".format(
            time=_time_str, name=_edit, phone=_phone,
        )
    except KeyError:
        return code_response(InvalidFormFIELDSResponse)
    if await check_sms_captcha(request, _eid, _phone, _captcha):
        async with request.app['mysql'].acquire() as conn:
            async with conn.cursor() as cur:
                # 更新order
                m_cmd = f"UPDATE {TABLE_NAME} SET `status`='C', `content`=%s WHERE `id`=%s AND `status` NOT IN ('E', 'F')"
                await cur.execute(m_cmd, (_content, _oid))
                if cur.rowcount == 0:
                    return code_response(ConflictStatusResponse)
                # 更新equipment
                await cur.execute("UPDATE equipment SET status=0, edit=%s WHERE id=%s AND status=0", (_edit, _eid))
                if cur.rowcount == 0:
                    return code_response(ConflictStatusResponse)
                await handle_order_history(cur, _oid, 'C', _edit, _phone, data.get('remark'), _content)
                # await cur.execute(H_CMD, (_oid, 'C', _edit, _phone, data.get('remark'), _content))
                await handle_equipment_history(cur, _eid, _edit, '{} {} 取消工单'.format(_time_str, _edit))
                # await cur.execute("INSERT INTO edit_history (eid, content, edit) VALUES (%s, %s, %s)",
                #                   (_eid,
                #                    '{} {} 取消工单'.format(_time_str, _edit),
                #                    _edit))
                await conn.commit()
        return code_response(ResponseOk)
    else:
        return code_response(InvalidCaptchaResponse)


PATROL_TABLE = "patrol_meta"


async def get_patrol_id(request: Request):
    """ 获取当前order id，已经加 1 的了 """
    _date_str = datetime.now().strftime('%Y%m')
    patrol_id = await request.app['redis'].get(f'it:patrolID:{_date_str}')
    if patrol_id is None:
        async with request.app['mysql'].acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM {} WHERE patrol_id LIKE '{}%'".format(PATROL_TABLE, _date_str))
                patrol_id = await cur.fetchone()
                await conn.commit()
        patrol_id = patrol_id[0]
    # await request.app['redis'].set(f'it:orderID:{_date_str}', int(order_id) + 1, 3600)  # +1
    return '{date}{pid:0>3}'.format(date=_date_str, pid=int(patrol_id) + 1)


async def set_patrol_id(request: Request, order_id: str):
    await request.app['redis'].set(
        key='it:patrolID:{}'.format(order_id[:-3]),
        value=order_id[-3:],
        expire=ORDER_ID_EXPIRE_TIME,
    )


@routes.post('/patrol')
async def create_patrol(request: Request):  # { pid: str, eids: [] }
    try:
        _data = await request.json()
        _eids = [ItHashids.decode(_eid) for _eid in _data['eids']]
        _pid = ItHashids.decode(_data['pid'])
        _email = _data['email']
    except (KeyError, AssertionError, JSONDecodeError):
        return code_response(InvalidFormFIELDSResponse)

    _patrol_id = await get_patrol_id(request)

    m_cmd = """\
        INSERT INTO `patrol_meta` (
            patrol_id,
            pid,
            total,
            unfinished
        ) VALUES (%s, %s, %s, %s)\
"""
    d_cmd = """
        INSERT INTO `patrol_detail` (
            pid,
            eid
        ) VALUES (%s, %s)\
"""

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            try:
                await cur.execute(m_cmd, (_patrol_id, _pid, len(_eids), len(_eids)))
            except IntegrityError:
                return code_response(RepetitionOrderIdResponse)
            _last_row_id = cur.lastrowid
            await cur.executemany(d_cmd, [(_last_row_id, _eid) for _eid in _eids])
            await conn.commit()
    await send_patrol_email(request, _last_row_id, _patrol_id, create_captcha(), _email)
    return code_response(ResponseOk)


@routes.get('/patrolPlan')
async def get_patrol_plan(request: Request):
    try:
        page = int(request.query.get('page')) or 1
    except ValueError:
        return code_response(MissRequiredFieldsResponse)

    cmd = f"""\
    SELECT a.id, a.patrol_id, b.name, a.total, a.status, a.unfinished
    FROM {PATROL_TABLE} a 
    JOIN `profile` b ON a.pid = b.id
    WHERE a.del_flag = 0
"""
    cmd += ' ORDER BY id DESC' + ' LIMIT {}, {}'.format((page - 1) * PAGE_SIZE, PAGE_SIZE)
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            # 计算总页数
            await cur.execute(f"SELECT COUNT(*) FROM {PATROL_TABLE} WHERE del_flag = 0")
            sum_of_equipment = (await cur.fetchone())[0]
            total_page = sum_of_equipment // PAGE_SIZE
            if sum_of_equipment % PAGE_SIZE:
                total_page += 1

            await cur.execute(cmd)
            data = []
            for row in await cur.fetchall():
                data.append({
                    'pid': ItHashids.encode(row[0]),
                    'patrolId': row[1],
                    'name': row[2],
                    'total': row[3],
                    'status': row[4],
                    'unfinished': row[5],
                })
            await conn.commit()

    resp = code_response(ResponseOk, {
        'totalPage': total_page,
        'tableData': data
    })
    # resp.set_cookie(f'{KEY_OF_VERSION}-version', await get_cache_version(request, KEY_OF_VERSION))
    return resp


def get_patrol_id_in_uri(request: Request):
    return get_query_params(request, 'pid')


@routes.delete('/patrol')
async def delete_patrol(request: Request):
    pid = get_patrol_id_in_uri(request)

    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE `patrol_meta` SET del_flag=1 WHERE id=%s", pid)
            await cur.execute("UPDATE `patrol_detail` SET del_flag=1 WHERE pid=%s", pid)
            await conn.commit()
    return code_response(ResponseOk)


def get_patrol_detail_id(request: Request):
    return get_query_params(request, 'pid')


@routes.get('/patrolDetail')
async def get_patrol_detail(request: Request):
    """ 查看巡检计划的所有设备 """
    pid = get_patrol_detail_id(request)
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""\
            SELECT b.`department`, b.`category`, a.`check`, a.`gmt_modified`, a.`id`, a.`pid`
            FROM `patrol_detail` a
            JOIN `equipment` b ON a.`eid` = b.`id` 
            WHERE `pid`=%s\
""", pid)
            data = []
            for row in await cur.fetchall():
                data.append({
                    'department': row[0],
                    'category': row[1],
                    'check': row[2],
                    'checkTime': row[3].strftime('%Y-%m-%d'),
                    'pdId': ItHashids.encode(row[4]),
                    'pid': ItHashids.encode(int(row[5])),
                })
            await conn.commit()
    return code_response(ResponseOk, data)


@routes.get('/singlePatrolPlanList')
async def get_patrol_detail(request: Request):
    """ 查看单个设备的巡检记录 """
    eid = get_equipment_id(request)
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
            SELECT b.id, b.patrol_id 
            FROM patrol_detail a 
            JOIN patrol_meta b ON a.pid = b.id 
            WHERE a.eid = %s AND a.`check` = 0;
""", eid)
            data = []
            for row in await cur.fetchall():
                data.append({
                    'pid': ItHashids.encode(row[0]),
                    'patrolId': row[1],
                })
            await conn.commit()
    return code_response(ResponseOk, data) if len(data) else code_response(EmtpyPatrolPlanResponse)


@routes.patch('/patrolCheck')
async def patrol_check(request: Request):
    pid = get_query_params(request, 'pid')
    pd_id = get_query_params(request, 'pdId')
    eid = get_query_params(request, 'eid')
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE `patrol_detail` SET `check`=1 WHERE `id`=%s AND `pid`=%s AND `eid`=%s",
                              (pd_id, pid, eid))
            if cur.rowcount == 0:
                return code_response(ConflictStatusResponse)
            await cur.execute("SELECT COUNT(*) FROM `patrol_detail` WHERE `pid`=%s AND `check`=0", pid)
            row = await cur.fetchone()
            if row:
                if row[0] == 0:  # 如果全部check了则更新plan
                    await cur.execute("UPDATE `patrol_meta` SET `status`=1, `unfinished`=0 WHERE `id`=%s", pid)
                else:
                    await cur.execute("UPDATE `patrol_meta` SET `unfinished`=%s WHERE `id`=%s", (row[0], pid))
            await conn.commit()
    return code_response(ResponseOk)


def get_case_id(request: Request):
    return get_query_params(request, 'caseId', decode=False)


@routes.get('/emailContent')
async def get_email_content(request: Request):  # case id 就是长的那个id
    case_id = get_case_id(request)
    _content = ""
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT `content` FROM `email_history` WHERE `case_id`=%s", case_id)
            row = await cur.fetchone()
            await conn.commit()
            if row:
                _content = row[0]
            else:
                return code_response(MissEmailContentResponse)
    return code_response(ResponseOk, {'content': _content})


async def get_email_meta(request, case_id, table):
    assert table in ('order', 'patrol_meta')
    fd = 'order_id' if table == 'order' else 'patrol_id'
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(f"""\
SELECT a.`id`, b.`email`, c.`captcha` 
FROM `{table}` a 
JOIN `profile` b ON a.pid=b.id 
JOIN `captcha_meta` c ON a.`{fd}` = c.`case_id` 
WHERE a.`{fd}`=%s\
""", case_id)
            row = await cur.fetchone()
            await conn.commit()
            if row:
                return row
            else:
                raise RuntimeError


@routes.patch('/resendMaintenanceEmail')
async def resend_maintenance_email(request: Request):
    case_id = get_case_id(request)
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT `content` FROM `email_history` WHERE `case_id`=%s", case_id)
            row = await cur.fetchone()
            await conn.commit()
            if row:
                return code_response(AlreadySendEmailResponse)
    try:
        _mid, _to_address, _captcha = await get_email_meta(request, case_id, 'order')
        try:
            await send_maintenance_order_email(request, _mid, case_id, _captcha, _to_address)
            return code_response(ResponseOk)
        except RuntimeError:
            return code_response(SendEmailTimeoutResponse)
    except RuntimeError:
        return code_response(ConflictStatusResponse)


@routes.patch('/resendPatrolEmail')
async def resend_patrol_email(request: Request):
    case_id = get_case_id(request)
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT `content` FROM `email_history` WHERE `case_id`=%s", case_id)
            row = await cur.fetchone()
            await conn.commit()
            if row:
                return code_response(AlreadySendEmailResponse)
    try:
        _mid, _to_address, _captcha = await get_email_meta(request, case_id, 'patrol_meta')
        try:
            await send_patrol_email(request, _mid, case_id, _captcha, _to_address)
            return code_response(ResponseOk)
        except RuntimeError:
            return code_response(SendEmailTimeoutResponse)
    except RuntimeError:
        return code_response(ConflictStatusResponse)


@routes.get('/personalPatrol')
async def get_personal_patrol_plan(request: Request):
    uid = ItHashids.decode(request['jwt_content']['uid'])
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""\
SELECT * FROM `patrol_meta`
WHERE `pid`=%s AND `status`=0 AND `del_flag`=0
ORDER BY `id`
DESC LIMIT 20\
""",
                              uid)
            res = []
            for row in await cur.fetchall():
                res.append({
                    'pid': ItHashids.encode(row[0]),
                    'patrolId': row[1],
                    'total': row[3],
                    'unfinished': row[4],
                    'status': row[5],
                    'gmt': row[7].strftime('%Y-%m-%d')
                })
            await conn.commit()
        return code_response(ResponseOk, res)


@routes.get('/personalMaintenance')
async def get_personal_maintenance(request: Request):
    uid = ItHashids.decode(request['jwt_content']['uid'])
    async with request.app['mysql'].acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""\
SELECT a.`id`, a.`order_id`, a.`status`, a.`eid`, a.`equipment`, a.`department`, a.`reason`, b.`name`, b.`phone` 
FROM `order` a
JOIN `order_history` b
ON a.`id` = b.`oid`
WHERE a.`pid`=%s AND (a.`status` IN ('D', 'H')) AND a.`del_flag`=0 AND b.`status`='R'
ORDER BY `id` 
DESC LIMIT 20\
            """, uid)
            res = []
            for row in await cur.fetchall():
                res.append({
                    'oid': ItHashids.encode(row[0]),
                    'orderId': row[1],
                    'status': row[2],
                    'eid': row[3],
                    'equipment': row[4],
                    'department': row[5],
                    'reason': row[6],
                    'name': row[7],
                    'phone': row[8],
                })
            await conn.commit()
        return code_response(ResponseOk, res)
