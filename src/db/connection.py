from aiomysql import create_pool as create_mysql_pool
from aioredis import create_redis_pool

from src.utls.toolbox import BloomFilter


async def open_connection(app):
    conf_mysql = app['config']['mysql']
    conf_redis = app['config']['redis']

    app['redis'] = await create_redis_pool(
        address="redis://" + conf_redis['host'] + ":" + str(conf_redis['port']) + "?encoding=utf-8",
        timeout=1.5,
        minsize=3,
        maxsize=100,
        password=conf_redis['password']
    )
    app['mysql'] = await create_mysql_pool(
        host=conf_mysql['host'],
        user=conf_mysql['user'],
        password=conf_mysql['password'],
        port=conf_mysql['port'],
        db=conf_mysql['database'],
        loop=app.loop,
        minsize=3,
        maxsize=10,
    )


async def close_connection(app):
    app["mysql"].close()
    await app["mysql"].wait_closed()
    await app['redis'].delete(BLACK_BF_NAME)
    app["redis"].close()
    await app["redis"].wait_closed()


BLACK_BF_NAME = "it:black:bf"


async def init_bf(app):
    app['black_bf'] = BloomFilter(bf_name=BLACK_BF_NAME, bit_map=app['redis'])


async def clear_bf(app):
    await app['redis'].delete(BLACK_BF_NAME)

if __name__ == '__main__':
    pass
