import logging
import re
import sys
from types import ModuleType

from config import Config


class SubWorker:
    __data__ = {}  # threadsafe хранилище

    def __init__(self, **kwargs):
        if self.__class__ is not SubWorker:
            config = self.__cfg__ if hasattr(self, '__cfg__') else '__default_subworker__'
            self.cfg = Config(config, **kwargs)

            self.log = logging.getLogger(self.__class__.__name__)
            self.log.addHandler(logging.StreamHandler(stream=sys.stderr))
            self.log.setLevel(self.cfg['debug_level'] or 'WARNING')

            if not hasattr(self, '__route__'):
                __route__ = '/' + '/'.join(self.__module__.split('.')[1:-1] + [self.__class__.__name__])
            else:
                __route__ = getattr(self, '__route__')

            self.__data__[__route__] = self

    @staticmethod
    def register(root, **kwargs):
        for name, obj in root.__dict__.items():
            if obj is root: continue
            if type(obj) is ModuleType and obj.__name__.startswith(root.__name__):
                SubWorker.register(obj, **kwargs)
            elif hasattr(obj, 'mro') and SubWorker in obj.mro()[1:]:
                obj(**kwargs)

    @staticmethod
    def dispatch(method, path):
        for regex, obj in SubWorker().__data__.items():
            match = re.match(f'^{regex}$', path)
            if match:
                func = getattr(obj, method.upper(), None)
                if func: return func
                raise DispatchError('405 Method Not Allowed',
                                    message=f"Can't call method '{method}'")  # не найден метод в субворкере
        else:
            raise DispatchError('404 Not Found',
                                message=f"Path '{path}' is not exists")  # не найден подходящий субворкер


class DispatchError(Exception):
    def __init__(self, status, message=None):
        self.status = status
        self.message = message
