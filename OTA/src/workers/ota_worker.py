#!/usr/bin/python3
# -*- coding: utf-8 -*-

# import json

import re
from urllib.parse import urlparse
from request import *
from subworker import SubWorker


class RegisterSIM(SubWorker):
    __route__ = r'/ota/v1/probe'
    __cfg__ = 'ota_worker'
    header = {
        # 'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:70.0) Gecko/20100101 Firefox/70.0',
        # 'DNT': 1,
        # 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        # 'Accept-Language': 'en-US,en;q=0.5',
        # 'Accept-Encoding': 'gzip, deflate',
        # 'Content-Type': 'application/x-www-form-urlencoded',
        # 'Content-Length': 51,
        # 'Origin': 'http://10.77.66.9:8080',
        # 'Connection': 'keep-alive',
        # 'Referer': 'http://10.77.66.9:8080/ota/login?buildversion=1.0.10+build+2467',
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cookie = None

    def TEST(self, env, response):
        ota = Request(source=REST(**self.cfg.ota_rest))
        self.login(ota)

        result = 'done'
        # self.log.debug('TEST: %s %s', repr(result), repr(header))
        status, reason, header, result = ota.post('campaigns/list', headers=self.header,
                                                  body={"order": "asc", "pageNumber": 1, "pageSize": 5000,
                                                        "isFinished": False}, verbose=True)
        self.log.debug('CAMPAINGS: %s %s %s %s %s', status, repr(reason), repr(header), repr(result), type(result))

        response("200 OK", [('Content-Type', 'application/json; utf-8')])
        return json.dumps({'status': 1, 'response': result})

    def POST(self, env, response):
        result = ''

        response("200 OK", [('Content-Type', 'application/json; utf-8')])
        return json.dumps({'status': 1, 'response': result})

    def login(self, ota):
        status, reason, header, result = ota.get('/ota/', headers=self.header, verbose=True, no_json=True)
        # self.log.debug('TEST: %s %s %s %s', status, repr(reason), repr(header), repr(result))
        if status == 200:
            form = re.findall(r'\<(form|input) +(.*?) */?\>', result.decode('utf-8'))
            form = [(i[0], dict(re.findall(r' ?(\w+)="([^"]*?)"', i[1]))) for i in form]
            # self.log.debug('FORM: %s', repr(form))
            body = []
            for _, p in form[1:]:
                if p['type'] == 'hidden':
                    body.append(p['name'] + '=' + p['value'])
                elif p['type'] == 'text':
                    body.append(p['name'] + '=' + self.cfg.ota_rest.username)
                elif p['type'] == 'password':
                    body.append(p['name'] + '=' + self.cfg.ota_rest.password)
            else:
                body = '&'.join(body)
            # self.log.debug('BODY: %s', body)
            status, reason, header, result = ota(
                form[0][1]['method'],
                form[0][1]['action'],
                headers={**self.header, 'content-type': 'application/x-www-form-urlencoded'},
                verbose=True,
                no_json=True,
                body=body)
            # self.log.debug('LOGIN_OK: %s %s %s %s', status, repr(reason), repr(header), repr(result))


class ApiListCampaign(SubWorker):
    __route__ = r'/v1/listCampagins'
    __cfg__ = 'ota_worker'
    request_num = 0

    def GET(self, environ, start_response):
        self.request_num += 1
        request_num = self.request_num

        self.log.setLevel(self.cfg['debug_level'])

        req = json.load(environ['wsgi.input'])
        self.log.debug('%d %s %s', request_num, 'request:', repr(req))

        start_response("200 OK", [('Content-Type', 'application/json; utf-8')])

        # self.log.debug('ota_soap %s', repr(self.cfg.test))
        ota = Request(source=SOAP(**self.cfg.ota_api))

        try:
            res = ota.listCampaigns(onlyActive=False)

        except Fault as f:
            res = {'message': f.message}
        except Error as e:
            # res = {'message': e.message, 'content': e.content}
            res = {'message': e.message}

        self.log.debug('%d %s %s', request_num, 'response:', len(json.dumps(res)))
        return json.dumps({'status': 1, 'response': res})
