from peewee import MySQLDatabase, CharField, BooleanField, Field, DateTimeField, IntegerField, SQL, Model, DateField
from werkzeug.security import generate_password_hash

from src.settings import CONFIG

MySQL_DB = MySQLDatabase(
    host=CONFIG["mysql"]["host"],
    port=CONFIG["mysql"]["port"],
    user=CONFIG["mysql"]["user"],
    password=CONFIG["mysql"]["password"],
    database=CONFIG["mysql"]["database"]
)


class TinyInt(Field):
    field_type = 'TINYINT'


class ModelBase(Model):
    class Meta:
        database = MySQL_DB


class Profile(ModelBase):
    """
    账号配置

    username:          登陆名，姓名加工号
    work_number:       只是工号
    name:              真名
    department:        所属部门
    phone:             电话
    role:              角色
    password_hash:
    email:             邮箱地址，派工维修的时候再设为必填
    wx_id:             企业微信的user id
    """
    username = CharField(max_length=16, unique=True)
    work_number = CharField(max_length=8)
    name = CharField(max_length=16)
    department = CharField(max_length=32, null=True)
    phone = CharField(max_length=16, null=True)
    role = TinyInt()
    password_hash = CharField(max_length=128)
    email = CharField(max_length=128, null=True)
    wx_id = CharField(max_length=128, null=True)

    @property
    def password(self):
        raise AttributeError("Cant't visit password")

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    # 数据量太少，做索引没意义


# todo 别人的唯一ID
class Equipment(ModelBase):
    """
    设备资料

    category:                 设备分类
    brand:                    品牌厂家
    model_number:             品牌型号
    serial_number:            序列号
    price:                    资产价格
    purchasing_time:          购买时间
    guarantee:                保修时长
    remark:                   备注

    status:                   状态码：0 使用中；1 维修中；2 备用；3 报废

    user:                     使用人
    owner:                    责任人
    department:               所属部门
    edit:                     最后编辑人 每次都会更新

    del_flag:                 删除标记
    """
    category = CharField(max_length=32)
    brand = CharField(max_length=32, null=True)
    model_number = CharField(max_length=64, null=True)
    serial_number = CharField(max_length=64, null=True)
    price = IntegerField(null=True, constraints=[SQL('DEFAULT 0')])
    purchasing_time = DateField(null=True)
    guarantee = TinyInt(null=True)
    remark = CharField(max_length=128, null=True)

    status = TinyInt(constraints=[SQL('DEFAULT 0')])

    user = CharField(max_length=16, null=True)
    owner = CharField(max_length=16, null=True)
    department = CharField(max_length=32, null=True)
    edit = CharField(max_length=16)

    del_flag = BooleanField(constraints=[SQL('DEFAULT 0')])

    gmt_modified = DateTimeField(formats='%Y-%m-%d %H:%M:%S',
                                 constraints=[SQL('DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')])

    class Meta:
        indexes = (
            (('category', 'department'), False),
        )


class EditHistory(ModelBase):
    """
    修改历史

    eid:                 对应的设备ID
    content:             修改的内容
    edit:                编辑人
    """
    eid = IntegerField()
    content = CharField(max_length=1023)
    edit = CharField(max_length=16)
    gmt_modified = DateTimeField(formats='%Y-%m-%d %H:%M:%S',
                                 constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])

    class Meta:
        indexes = (
            (('eid',), False),
        )
        table_name = 'edit_history'


class ComputerDetail(ModelBase):
    """
    电脑细节

    eid:                 对应的设备ID
    ip_address:          ip地址
    cpu:                 cpu
    gpu:                 显卡
    disk:                硬盘
    memory:              内存
    main_board:          主板
    monitor:             显示器  # todo
    remark:              备注

    del_flag:            删除标记
    """
    eid = IntegerField()
    ip_address = CharField(max_length=64, null=True)
    cpu = CharField(max_length=32, null=True)
    gpu = CharField(max_length=32, null=True)
    disk = CharField(max_length=32, null=True)
    memory = CharField(max_length=32, null=True)
    main_board = CharField(max_length=32, null=True)
    monitor = CharField(max_length=32, null=True)
    remark = CharField(max_length=128, null=True)

    del_flag = BooleanField(constraints=[SQL('DEFAULT 0')])

    gmt_modified = DateTimeField(formats='%Y-%m-%d %H:%M:%S',
                                 constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])

    class Meta:
        indexes = (
            (('eid',), True),
        )
        table_name = 'computer_detail'


class WorkOrder(ModelBase):
    """
    order_id:               特殊的工单ID yyyymmdd + 3位index
    status:                 工单状态：R 上报/待处理，D 已派工/待去现场，H 已到现场/处理中，E 处理完成/待评价，F 工单结束，C 取消
    pid:                    当前处理人的ID
    name:                   人员名称
    eid:                    设备ID
    equipment:              设备名称
    department:             设备所属部门
    content:                最近一次的处理记录
    reason:                 原因
    rank:                   评分

    del_flag:               删除标记
    """
    order_id = CharField(max_length=12)
    status = CharField(max_length=1, constraints=[SQL("DEFAULT 'R'")])
    pid = IntegerField(null=True)
    name = CharField(max_length=16, null=True)
    eid = IntegerField()
    equipment = CharField(max_length=32)
    department = CharField(max_length=32)
    content = CharField()
    reason = CharField(max_length=32)
    rank = TinyInt(null=True)

    del_flag = BooleanField(constraints=[SQL('DEFAULT 0')])
    gmt_modified = DateTimeField(formats='%Y-%m-%d %H:%M:%S',
                                 constraints=[SQL('DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')])

    class Meta:
        table_name = 'order'
        indexes = (
            (('order_id',), True),
            (('pid',), False),
        )


class OrderHistory(ModelBase):
    """
    工单的节点信息
    oid:               对应的工单id
    status:            当前工单状态：R 上报/待处理，D 已派工/待去现场，H 已到现场/处理中，E 处理完成/待评价，F 工单结束，C 取消
    name:              当前操作人
    phone:             当前操作人联系方式
    remark:            备注
    content:           当前处理内容，可以记录派工/退回之类的内容
    """
    oid = IntegerField()
    status = CharField(max_length=1)
    name = CharField(max_length=16)
    phone = CharField(max_length=16, null=True)
    remark = CharField(null=True)
    content = CharField()

    gmt_modified = DateTimeField(formats='%Y-%m-%d %H:%M:%S', constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])

    class Meta:
        table_name = 'order_history'


class ItConfig(ModelBase):
    """
    简单保存kv
    send_sms: 0 or 1
    send_email: 0 or 1
    """
    key = CharField(max_length=32, unique=True)
    value = CharField(max_length=32)

    gmt_modified = DateTimeField(formats='%Y-%m-%d %H:%M:%S',
                                 constraints=[SQL('DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')])

    class Meta:
        table_name = 'it_config'


class CaptchaMeta(ModelBase):
    """
    记录 验证码 和 order/patrol 的关系
    case_id:    是order/patrol的长id
    """
    case_id = CharField(max_length=16)
    captcha = CharField(max_length=12)
    gmt_modified = DateTimeField(formats='%Y-%m-%d %H:%M:%S',
                                 constraints=[SQL('DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')])

    class Meta:
        table_name = 'captcha_meta'
        indexes = (
            (('case_id',), True),
        )


class EmailHistory(ModelBase):
    """
    记录email的发送记录
    case_id:    是order/patrol的长id
    email:      发送的目标邮箱
    captcha:    当前邮件包含的验证码
    content:    邮件正文
    """
    case_id = CharField(max_length=16)
    email = CharField(max_length=128)
    captcha = CharField(max_length=12)
    content = CharField(max_length=256)
    gmt_modified = DateTimeField(formats='%Y-%m-%d %H:%M:%S', constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])

    class Meta:
        table_name = 'email_history'
        indexes = (
            (('case_id',), True),
        )


class PatrolMeta(ModelBase):
    """
    巡检的meta资料
    patrol_id:              特殊的工单ID yyyymm + 3位index
    pid:                    当前处理人的ID
    total:                  计划内的设备总数
    status:                 0 进行中，1 已完成，2已取消
    unfinished:             未完成的数量，每次check都会更新这个数
    start_time:             计划开始时间
    end_time:               计划结束时间
    """
    patrol_id = CharField(max_length=12)
    pid = IntegerField()
    total = IntegerField()
    unfinished = IntegerField()
    status = TinyInt(constraints=[SQL('DEFAULT 0')])
    start_time = CharField()
    end_time = CharField()

    del_flag = BooleanField(constraints=[SQL('DEFAULT 0')])
    gmt_modified = DateTimeField(formats='%Y-%m-%d %H:%M:%S',
                                 constraints=[SQL('DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')])

    class Meta:
        table_name = 'patrol_meta'
        indexes = (
            (('patrol_id',), True),
        )


class PatrolDetail(ModelBase):
    """
    巡检的meta资料
    pid:               对应的巡检id
    eid:               设备对应的id
    check:             0 进行中，1 已完成
    """
    pid = CharField(max_length=16)
    eid = CharField(max_length=32)
    check = TinyInt(constraints=[SQL('DEFAULT 0')])

    del_flag = BooleanField(constraints=[SQL('DEFAULT 0')])
    gmt_modified = DateTimeField(formats='%Y-%m-%d %H:%M:%S',
                                 constraints=[SQL('DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')])

    class Meta:
        table_name = 'patrol_detail'
        indexes = (
            (('pid',), False),
        )


class DepartmentContact(ModelBase):
    """
    部门的联系人
    did:               department meta对应的id
    pid:               profile对应的id
    """
    did = CharField(max_length=16)
    pid = CharField(max_length=16, null=True)

    class Meta:
        table_name = 'department_contact'
        indexes = (
            (('did',), True),
        )


ALL_TABLES = [Profile, Equipment, EditHistory, ComputerDetail, WorkOrder, OrderHistory, ItConfig, CaptchaMeta,
              EmailHistory, PatrolMeta, PatrolDetail, DepartmentContact]

if __name__ == '__main__':
    # MySQL_DB.drop_tables([WorkOrder, OrderHistory])
    # MySQL_DB.create_tables([WorkOrder, OrderHistory])
    # MySQL_DB.drop_tables([ItConfig])
    # MySQL_DB.create_tables([ItConfig])
    # ItConfig.insert({ItConfig.key: "sendSms", ItConfig.value: "0"}).execute()
    # ItConfig.insert({ItConfig.key: "sendEmail", ItConfig.value: "0"}).execute()
    # MySQL_DB.drop_tables([OrderHistory, WorkOrder, CaptchaMeta, EmailHistory, PatrolMeta, PatrolDetail])
    # MySQL_DB.create_tables([OrderHistory, WorkOrder, CaptchaMeta, EmailHistory, PatrolMeta, PatrolDetail])
    # MySQL_DB.drop_tables([PatrolMeta, PatrolDetail, EmailHistory, CaptchaMeta])
    # MySQL_DB.create_tables([PatrolMeta, PatrolDetail, EmailHistory, CaptchaMeta])
    # MySQL_DB.drop_tables([ComputerDetail])
    # MySQL_DB.create_tables([ComputerDetail])
    _tables = [
        # DepartmentContact,
        PatrolMeta,
        PatrolDetail
    ]
    MySQL_DB.drop_tables(_tables)
    MySQL_DB.create_tables(_tables)
    pass
