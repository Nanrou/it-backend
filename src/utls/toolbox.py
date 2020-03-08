from hashlib import md5
from json import dumps

from aiohttp.web import RouteTableDef, json_response, Request
from aiohttp.web_exceptions import HTTPForbidden
from aiomysql.pool import Pool
from hashids import Hashids

from src.settings import config


class LocalHashids(Hashids):
    def decode(self, hashid):
        res = super().decode(hashid)
        if res:
            return res[0]
        else:
            raise KeyError


# todo 应该是每个模块用不同的salt
ItHashids = LocalHashids(salt=config.get('jwt-secret'), min_length=8)


class PrefixRouteTableDef(RouteTableDef):
    def __init__(self, prefix):
        self.prefix = prefix
        super().__init__()

    def route(self, method, path, **kwargs):  # 注意这个是装饰器
        return super().route(method, self.prefix + path, **kwargs)

    # 其他具体方法都是调用route来实现的，所以在route改就行了


class Tree:
    def __init__(self, pool: Pool):
        self.pool = pool

    async def add_node(self, name: str, meta_id: int = None):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute('INSERT INTO department_meta (name) VALUES (%s)', (name,))
                lastrowid = cur.lastrowid

                # 自己构造插入语句，来保证连续自增id
                relations = [(lastrowid, lastrowid, 0)]
                await cur.execute(
                    'SELECT ancestor, {lastrowid}, depth+1 FROM department_relation WHERE descendant=%s'.format(
                        lastrowid=lastrowid), (meta_id,))
                for row in await cur.fetchall():
                    relations.append(row)
                await cur.executemany(
                    "INSERT INTO department_relation (ancestor, descendant, depth) VALUES (%s, %s, %s)",
                    relations)
                await conn.commit()

        return lastrowid  # 返回新生成的节点id

    async def delete_node(self, meta_id):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute('''\
SELECT a.id, a.descendant 
FROM department_relation a JOIN department_relation b 
    ON a.descendant = b.descendant 
WHERE b.ancestor=%s''', (meta_id,))
                relation_ids = set()
                department_ids = set()
                for row in await cur.fetchall():
                    relation_ids.add(row[0])
                    department_ids.add(row[1])
                if len(department_ids):
                    await cur.execute(
                        'DELETE FROM department_meta WHERE id in ({})'.format(
                            ','.join([str(i) for i in department_ids])))
                if len(relation_ids):
                    await cur.execute(
                        'DELETE FROM department_relation WHERE id in ({})'.format(
                            ','.join([str(i) for i in relation_ids])))
                await conn.commit()

    async def update_node(self, meta_id, new_name):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute('UPDATE department_meta SET name=%s WHERE id=%s', (new_name, meta_id))
                await conn.commit()

    async def get_children_node(self, meta_id: int, json_format=True):
        """
        查寻该节点的所有子节点(包含本节点), 并转换为树状结构

        :param meta_id: 节点id
        :param json_format: 输出是否为json化
        :return:
        """
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute('''\
SELECT c.id, c.name, c.is_global, d.ancestor, d.depth
FROM department_meta c JOIN
(
SELECT b.ancestor, a.depth, a.descendant
FROM department_relation a
LEFT JOIN (SELECT * FROM department_relation WHERE depth = 1) b
ON a.descendant = b.descendant
WHERE a.ancestor = %s
) d
ON c.id = d.descendant\
''', (meta_id,))
                res = []
                for row in await cur.fetchall():
                    res.append(row)
                await conn.commit()
        # res [(meta_id, meta_name, meta_global, relation_ancestor, relation_depth), ...]

        layer_dict = {}
        for item in res:
            layer_dict.setdefault(item[-1], []).append({
                'value': ItHashids.encode(item[0]),
                'label': item[1],
                'isGlobal': item[2],
                'ancestor': ItHashids.encode(item[3] or 0),
                'children': []
            })

        # 去掉叶节点的children
        for item in layer_dict[len(layer_dict.keys()) - 1]:
            item.pop('children')

        for layer in range(len(layer_dict.keys()) - 1, 0, -1):
            for item in layer_dict[layer]:
                for ancestor in layer_dict[layer - 1]:
                    if item['ancestor'] == ancestor['value']:
                        ancestor['children'].append(item)
                        break

        return dumps(layer_dict[0], ensure_ascii=False) if json_format else layer_dict[0]

    async def add_nodes(self, nodes: dict, ancestor: str = None):
        """
        批量添加节点，利用递归
        :param nodes:
        :param ancestor:
        :return:
        """
        for key, value in nodes.items():
            rid = await self.add_node(key, ancestor)
            if isinstance(value, dict):
                await self.add_nodes(value, ancestor=rid)
            else:
                for _v in value:
                    await self.add_node(_v, rid)


class SimpleHash:
    def __init__(self, cap, seed):
        self.cap = cap
        self.seed = seed

    def hash(self, value):
        ret = 0
        for i in range(len(value)):
            ret += self.seed * ret + ord(value[i])
        return (self.cap - 1) & ret


class BloomFilter:
    """
    布隆过滤器
    简单原理为：先生成一个长度为固定，且全为0的集合，然后开始逐一对要比较的元素进行多次哈希，然后在集合中将多次结果
    的值对应的位置为1，如此类推，若发现某一元素所有要插入的位置都已经为1了，则说明这个元素重复了。
    关键参数：n个元素，集合大小为m，k次哈希
    具体误判率可以查表：http://pages.cs.wisc.edu/~cao/papers/summary-cache/node8.html
    """

    def __init__(self, bit_map, bf_name="bf", bit_size=1 << 20, seeds=None):
        """
        默认参数下，处理10万条数据的时候，误判率为0.00819
        :param bit_size: m值
        :param seeds: k值
        """
        self._bf_name = bf_name
        self._bit_size = bit_size
        if seeds is None:
            seeds = [3, 5, 7, 11, 13, 31, 67]
        self._seeds = seeds
        # if bit_map is None:  # 初始化
        #     map = array('b', [0 for _ in range(self._bit_size)])  # 选择了用数组来存放记录
        #     可以改用其他的结构，例如redis的bitmap
        #     这里就是要传入redis的对象
        #     raise RuntimeError('Must choose map')
        self._map = bit_map
        self._hash_functions = []
        for seed in self._seeds:
            self._hash_functions.append(SimpleHash(self._bit_size, seed))

    async def is_contain(self, ele):  # 判断是否存在
        m5 = md5()
        m5.update(bytes(ele, encoding='utf-8'))
        _ele = m5.hexdigest()
        return all([await self._map.getbit(self._bf_name, f.hash(_ele)) for f in self._hash_functions])

    async def insert(self, ele):  # 参入新值
        m5 = md5()
        m5.update(bytes(ele, encoding='utf-8'))
        _ele = m5.hexdigest()
        for f in self._hash_functions:
            index = f.hash(_ele)
            await self._map.setbit(self._bf_name, index, 1)


def code_response(response_type, data=None):
    if data is None:
        return json_response(response_type.json_without_data())
    else:
        return json_response(response_type(data).json())


def get_query_params(request: Request, key: str, decode=True):
    try:
        if decode:
            return ItHashids.decode(request.query[key])
        else:
            return request.query[key]
    except KeyError:
        raise HTTPForbidden(text=f'Miss {key}')


if __name__ == '__main__':
    print(ItHashids.decode('aaaa'))
