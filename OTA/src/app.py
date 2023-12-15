#!/usr/bin/python3
# -*- coding: utf-8 -*-
import eventlet
from gunicorn.app.base import BaseApplication
from gunicorn.workers.geventlet import EventletWorker

from subworker import SubWorker, DispatchError
from config import Config, YamlConfig
import workers

# import multiprocessing

if not workers.ALL_LOAD: raise Exception('Not all workers is loaded correctly')

eventlet.monkey_patch()
CONFIG = Config(source=YamlConfig('/etc/ota_app/config.yml', 'etc/config.yml', 'config.yml')).load()


class Worker(EventletWorker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.wsgi = None

    def init_process(self):
        SubWorker.register(workers, glob=True)
        super().init_process()


def wsgi(env, response):
    try:
        result = SubWorker.dispatch(env['REQUEST_METHOD'], env['PATH_INFO'])(env, response)
    except DispatchError as e:
        response(e.status, [('Content-Type', 'application/json; utf-8')])
        result = e.message
    # except Exception as e:
    #     response("500 Internal Server Error", [('Content-Type', 'application/json; utf-8')])
    #     result = e.args[0] or ''

    return [result.encode('utf-8')]


class Application(BaseApplication):

    def __init__(self):
        self.application = wsgi
        super().__init__()

    def init(self, parser, opts, args):
        pass

    def load_config(self):
        for key, val in CONFIG.gunicorn.items():
            if key in self.cfg.settings and val is not None:
                self.cfg.set(key.lower(), val)
        self.cfg.set('worker_class'.lower(), 'app.Worker')

    def load(self):
        return self.application


if __name__ == '__main__':
    Application().run()
