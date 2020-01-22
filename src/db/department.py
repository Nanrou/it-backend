import asyncio
import json

from aiomysql import create_pool as create_mysql_pool
from peewee import CharField, BooleanField, IntegerField, SQL

from src.db.orm import ModelBase, MySQL_DB
from src.utls.toolbox import Tree
from src.settings import config


class DepartmentMeta(ModelBase):
    """
    部门元数据

    name:          部门名称
    is_global:     辅助判定，是可以看整个公司级别的，还是看自己下属单位的
    """
    name = CharField(max_length=64)
    is_global = BooleanField(constraints=[SQL('DEFAULT 0')])

    class Meta:
        table_name = 'department_meta'


class DepartmentRelation(ModelBase):
    """
    注意，每个节点都有一条指向自己的路径
    ancestor:         父节点
    descendant:       子节点
    depth:            深度
    """
    ancestor = IntegerField(null=True)  # 根节点父代指向空
    descendant = IntegerField()
    depth = IntegerField()

    class Meta:
        table_name = 'department_relation'


def init_department():
    async def inner_func(loop):
        if config["mysql"]["host"] == 'localhost':
            pass
        else:
            raise RuntimeError("init prod ?")
        pool = await create_mysql_pool(
            host=config["mysql"]["host"],
            port=config["mysql"]["port"],
            user=config["mysql"]["user"],
            password=config["mysql"]["password"],
            db=config["mysql"]["database"],
            loop=loop)
        MySQL_DB.drop_tables([DepartmentMeta, DepartmentRelation])
        MySQL_DB.create_tables([DepartmentMeta, DepartmentRelation])

        tree = Tree(pool)
        with open('../meta/departments.json', 'r') as rf:
            _departments = json.load(rf)
        await tree.add_nodes(_departments)

        pool.close()
        await pool.wait_closed()

    _loop = asyncio.get_event_loop()
    _loop.run_until_complete(inner_func(_loop))


if __name__ == '__main__':
    init_department()
