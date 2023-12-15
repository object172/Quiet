#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import yaml

__all__ = ['Config', 'YamlConfig']


class Config:
    __data__ = {}  # threadsafe хранилище

    def __init__(self, *args, source=None, glob=None, **kwargs):
        self._source = source
        self._root = list(args)
        self._glob = glob

    @staticmethod
    def merge(d, u):  # recursive merge two dicts
        for (k, v) in u.items():
            if type(v) is dict:
                d[k] = Config.merge(d.get(k, {}), v)
            elif type(d) is dict:
                d[k] = u[k]
            else:
                d = {k: u[k]}
        return d

    def load(self):
        Config.__data__ = self._source.load()
        return self

    def __root(self):
        data = Config.__data__
        for k in self._root:
            if k not in data:   data[k] = {}
            data = data[k]
        return data

    def __getitem__(self, item):
        return self.__getattr__(item)

    def __setitem__(self, key, value):
        data = self.__root()
        if type(key) is list:
            for k in key[-1]:   data = data[k]
        else:
            data[key] = value

    def __call__(self, *args, **kwargs):
        return self.__root()

    def __getattr__(self, item):
        data = self.__root()
        if item in data:
            if type(data[item]) is dict:
                return Config(*self._root, item)
            else:
                return data[item]
        else:
            try:
                if self._glob:  return Config(*self._root[:-1]).__getattr__(item)
                return data[item]
            except KeyError:
                return None

    def __str__(self):
        return str(dict(self))

    def __len__(self):
        return len(Config.__data__)

    def keys(self):
        return self.__root().keys()

    def items(self):
        return self.__root().items()


class YamlConfig:
    def __init__(self, *args, **kwargs):
        self.files = []
        for i in args:
            if type(i) is str:
                self.files += [i]
            elif type(i) is list:
                self.files += i
            else:
                raise TypeError

    def load(self):
        res = {}
        for f in self.files:
            try:
                Config.merge(res, yaml.full_load(open(os.path.expanduser(f)).read()))
            except Exception as e:
                print(e)
        return res
