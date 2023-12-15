#!/usr/bin/python3
# -*- coding: utf-8 -*-

import http.client
import json
import logging
from functools import partial

from urllib.parse import urlparse
from requests import Session
from requests.auth import HTTPBasicAuth
from zeep import Client
from zeep.exceptions import *
from zeep.transports import Transport

from cache import InMemoryCache
import sys

logger = logging.getLogger(__name__)


# @traced()
class Request:
    def __init__(self, *args, source=None, cache=None, **kwargs):
        self.source = source
        self.cache = cache
        # self.source.post_init()

    def __getattr__(self, item):
        return self.source.__getattr__(item)

    def __call__(self, *args, **kwargs):
        return self.source._request(*args, **kwargs)

    def request(self, *args, **kwargs):
        return self.source._request(*args, **kwargs)

    def _request(self, *args, **kwargs):
        raise NotImplemented


class SOAP:
    def __init__(self, wsdl=None, auth=None, username='', password='', **kwargs):
        self.wsdl = wsdl
        self.username = username
        self.password = password
        self.auth = auth.lower()

        session = Session()
        if self.auth == 'basic':
            session.auth = HTTPBasicAuth(self.username, self.password)
        self.client = Client(self.wsdl, transport=Transport(cache=InMemoryCache(), session=session))

    def __getattr__(self, item):
        return partial(self._request, self.client.service[item])

    def _request(self, *args, **kwargs):
        req, *args = args
        try:
            res = req(*args, **kwargs)
        except Error as e:
            raise e
        return self._rec_copy(res)

    def _rec_copy(self, obj):
        '''
        Декодирование zeep-объектов в иерархию list/dict
        :param obj:
        :return: list/dict
        '''
        if type(obj) is list:
            return [self._rec_copy(i) for i in obj]
        elif type(obj) is str:
            return obj.rstrip('\r\n')
        elif hasattr(obj, '__json__'):
            return {k: self._rec_copy(v) for k, v in obj.__json__().items()}
        else:
            return obj


class REST:
    def __init__(self, host=None, cache=None, username=None, password=None):
        self.rest = host
        self.username = username
        self.password = password
        self.cache = cache
        self._cookie = []
        self.cookie = None
        self.path = '/'

    def __getattr__(self, item):
        return partial(self._request, item)

    def _request(self, method, url, no_json=False, verbose=False, headers={}, body=None, redirect=True, timeout=30):
        method = method.upper()
        rc = http.client.HTTPConnection(self.rest, timeout=timeout)

        if isinstance(body, (dict,)) and not no_json:
            try:
                body = json.dumps(body)
                headers.update({'content-type': 'application/json', 'accept': 'application/json'})
            except:
                pass
        if self.cookie: headers.update({'Cookie': self.cookie})

        path = self.path if not url.startswith('/') else ''

        rc.request(method, path + url, body=body, headers=headers)
        res = rc.getresponse()
        response = res.read()
        header = {k.lower(): v for k, v in res.getheaders()}

        if 'set-cookie' in header:
            self._cookie = [i.strip(' \r\n') for i in header['set-cookie'].split(';')]
            self.cookie = self._cookie[0]
            for i in self._cookie:
                if i.upper().startswith('PATH='):
                    self.path = i[5:]
                    if not self.path.endswith('/'): self.path += '/'

        if redirect and res.status == 302:
            path = urlparse(header['location']).path
            return self._request('GET', path, no_json=no_json, verbose=verbose, headers=headers, body=body,
                                 redirect=redirect, timeout=timeout)

        if not no_json:
            try:
                response = json.loads(response.decode('utf-8'))
            except:
                pass
        rc.close()
        if verbose:
            return res.status, res.reason, header, response
        return response
