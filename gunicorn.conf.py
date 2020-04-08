import os
import platform

PRO_PATH = os.path.dirname(os.path.abspath(__file__))
if not os.path.exists(os.path.join(PRO_PATH, 'src/log')):
    os.mkdir(os.path.join(PRO_PATH, 'src/log'))

preload_app = True

if platform.system() == 'Darwin':
    bind = '127.0.0.1:8081'
    workers = 1
else:
    bind = '0.0.0.0:8080'
    workers = 4

timeout = 5
worker_class = 'aiohttp.GunicornWebWorker'
max_requests = 1000

loglevel = 'debug'
errorlog = os.path.join(PRO_PATH, 'src/log/gunicorn.error.log')
accesslog = os.path.join(PRO_PATH, 'src/log/gunicorn.access.log')
