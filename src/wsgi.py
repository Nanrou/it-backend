import argparse

from aiohttp import web
from src.main import app_factory

app = app_factory()


if __name__ == '__main__':
    parse = argparse.ArgumentParser()
    parse.add_argument('port')
    args = parse.parse_args()
    web.run_app(app_factory(), host='0.0.0.0', port=args.port)
