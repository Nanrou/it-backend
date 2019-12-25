import os

from aiohttp import web

from src.db.connection import open_connection, close_connection, init_bf, clear_bf
from src.settings import config
from src.routes import setup_routes
from src.middlewares import verify_jwt_token


def app_factory():
    app = web.Application(middlewares=[verify_jwt_token])
    setup_routes(app)
    app['config'] = config
    app.on_startup.append(open_connection)
    app.on_startup.append(init_bf)
    # app.on_cleanup.append(clear_bf)
    app.on_cleanup.append(close_connection)
    return app


if __name__ == '__main__':
    os.environ['PYTHONASYNCIODEBUG'] = '1'
    web.run_app(app_factory(), host='localhost', port=8081)
