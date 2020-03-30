import os

from aiohttp import web

from src.db.connection import open_connection, close_connection, init_bf, clear_bf
from src.settings import CONFIG, DOWNLOAD_DIR
from src.routes import setup_routes
from src.middlewares import verify_jwt_token


def app_factory():
    app = web.Application(middlewares=[verify_jwt_token])
    app['config'] = CONFIG
    setup_routes(app)
    app.add_routes([
        web.static('/api/download', DOWNLOAD_DIR, show_index=False, follow_symlinks=True, append_version=False)
    ])
    app.on_startup.append(open_connection)
    app.on_startup.append(init_bf)
    # app.on_cleanup.append(clear_bf)
    app.on_cleanup.append(close_connection)
    return app


if __name__ == '__main__':
    os.environ['PYTHONASYNCIODEBUG'] = '1'
    web.run_app(app_factory(), host='localhost', port=8081)
