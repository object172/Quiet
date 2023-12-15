import argparse
import asyncio
import datetime
import json
import signal
import aiohttp
import redis
import logging.config
import requests
import yaml

import checkers
import errors
from typing import AnyStr, Union
from checkers import checker_aiosession
from itemStore import ItemStore

# Events poster
messages = ItemStore()


def validate_config(config: dict):
    services = config.get('servers', [])
    devices = config.get('devices', [])
    if not services and not devices:
        log.error(errors.CONFIG_NO_DEVICES_OR_SERVERS)
        return
    datasources = config.get('datasources')
    if devices and not datasources:
        log.error(errors.CONFIG_NO_DATASOURCES)
        return
    for service in services:
        if 'name' not in services[service]:
            log.error(f'Config file "{CONFIG_FILE}" not valid: {service} - {errors.CONFIG_NO_NAME}')
            return
    for device in devices:
        if device != 'interval' and 'name' not in devices[device]:
            log.error(f'Config file "{CONFIG_FILE}" not valid: {device} - {errors.CONFIG_NO_NAME}')
            return
    if not config.get('notifications'):
        log.error(f'Config file "{CONFIG_FILE}" not valid:{errors.CONFIG_NO_NOTIFICATIONS}')
        return


async def async_get_from_sb(session: aiohttp.ClientSession, config: dict) -> list or None:
    params = {'access_token': SB_LOGIN_TOKEN} if SB_LOGIN_TOKEN else {}

    try:
        async with session.get(
                cfg['datasources']['sb'] + config['url'],
                timeout=float(config['timeout']),
                params=params,
        ) as resp:
            r = await resp.json()

    except aiohttp.ClientConnectionError or aiohttp.ServerTimeoutError:
        return None
    else:
        return r


async def async_post_to_sb(session: aiohttp.ClientSession, url: str, data: dict) -> None:
    params = {'access_token': SB_LOGIN_TOKEN} if SB_LOGIN_TOKEN else {}
    try:
        async with session.post(
                cfg['datasources']['sb'] + url,
                timeout=float(cfg['notifications']['events']['timeout']),
                params=params,
                json=data
        ) as resp:
            await resp.json()
    except Exception as e:
        log.error(f'SB post error {repr(e)}')


def sb_login() -> Union[AnyStr, None]:
    response = requests.post(
        cfg['datasources']['sb'] + cfg['datasources']['sb_opts']['login_url'],
        json={
            'email': cfg['datasources']['sb_opts']['username'],
            'password': cfg['datasources']['sb_opts']['password']
        }
    )

    if response.status_code != 200:
        return None

    resp = response.json()
    if 'id' not in resp:
        return None

    return resp['id']


async def check(config: dict) -> (bool, str):
    msg = ''
    chs = config.get('checks', [])
    for ch in chs:
        try:
            checker_func = checkers.CHECKERS[ch]
        except KeyError:
            log.error(f'{config} - check error: No such check functions')
            return False, ''
        res, msg = await checker_func(config)
        return res, msg
    return True, msg


async def notify(msg: str, layer: str = None, coords: object = None, header: str = ''):
    try:
        notifications = cfg.get('notifications')
        if 'sb' in notifications:
            log.debug(f'Start creating notification {msg}')

            notification_type_id = notifications['sb'].get('notifications_type_id', -1002)
            notification_type_ids_by_layer = notifications['sb'].get('notification_type_id_by_layer')
            if notification_type_ids_by_layer is not None:
                notification_type_id = notification_type_ids_by_layer.get(layer, notification_type_id)
            if not header:
                header = {'trMessage': '{{datetime}} - Monitoring',
                          'trParams': {'datetime': datetime.datetime.now().strftime("%d-%m-%Y %H:%M")}
                          }

            data = {
                'name': header,
                'description': msg,
                'notificationTypeId': notification_type_id,
                'layer': layer,
                'location': coords,
                'status': 'active'
            }

            await async_post_to_sb(
                api_aiosession,
                notifications['sb'].get('notifications_url', '/api/notifications'),
                data
            )
            log.debug(f'Notification created: {msg}')
    except Exception as e:
        log.error('Unknown error in notifications ' + repr(e))


async def monitoring(config: dict):
    fails = 0
    max_fails = config.get('failed_counter', 5)
    interval = config.get('interval', 120)
    timeout_interval = config.get('timeout_interval', 10)
    try:
        device_id = int(config['id'])
    except ValueError:
        device_id = None

    log.info(f'Monitoring for {config["name"]} started. MF: {max_fails} INT: {interval} TO_INT: {timeout_interval}')
    while True:
        try:
            cfg_name = config['name']
            cfg_type = config['type']
            cfg_id = config['id']
            cfg_object_name = config['object_name'] if 'object_name' in config else None
            res, msg = await check(config)
            if res:
                if cfg_type == 'controllers':
                    data = {
                        "controller": (await checkers.snmp_get(config.get('host'), config.get('port') )),
                        "spot": (await checkers.http_get(f"http://{config.get('spot_ip')}:{config.get('spot_port')}/stats?count=1")) if config.get('has_spot') else False
                    }
                    redis.hset(f'monitoring:{cfg_type}', cfg_id, json.dumps(data))
                else:
                    redis.hset(f'monitoring:{cfg_type}', cfg_id, 1)
                if fails:
                    log.info(f'{cfg_name} - restored')

                    message_text = {
                        'trMessage': '{{tr_config_name}} performance restored',
                        'trParams': {'tr_config_name': cfg_name}
                    }

                    header_text = {
                        'trMessage': 'Monitoring -- {{tr_config_name}} -- {{config_id}} ' +
                                     ('-- {{config_obj_name}} \u2705' if cfg_object_name is not None and cfg_object_name != '' else '\u2705'),
                        'trParams': {
                            'tr_config_name': cfg_name,
                            'config_id': cfg_id,
                            'config_obj_name': cfg_object_name
                        }
                    }

                    name = json.dumps(message_text)
                    header = json.dumps(header_text)
                    await notify(name,
                                 layer=config.get('layer'),
                                 coords=config.get('location'),
                                 header=header
                                 )
                    ts = datetime.datetime.now()
                    messages.add({
                        'timestamp': ts.isoformat(),
                        'event': f"[UP] -- {cfg_name} -- {cfg_id}  -- работоспособность восстановлена",
                        'sourceType': cfg_type,
                        'sourceId': device_id
                    })
                fails = 0
                await asyncio.sleep(interval)
            elif msg:
                if cfg_type == "controllers":
                    data = {
                        "controller": False,
                        "spot": False
                    }
                    redis.hset(f'monitoring:{cfg_type}', cfg_id, json.dumps(data))
                else:
                    redis.hset(f'monitoring:{cfg_type}', cfg_id, 0)
                fails += 1
                log.debug(f'{cfg_name} - {msg}')

                if fails == max_fails:
                    log.info(f'{cfg_name} - maximum fail limit reached')
                    message_text = {
                        'trMessage': '{{tr_config_name}} -- ' + f'{msg}',
                        'trParams': {'tr_config_name': cfg_name}
                    }

                    header_text = {
                        'trMessage': 'Monitoring -- {{tr_config_name}} -- {{config_id}} ' +
                                     ('-- {{config_obj_name}} \u274c' if cfg_object_name is not None and cfg_object_name != '' else ' \u274c'),
                        'trParams': {
                            'tr_config_name': cfg_name,
                            'config_id': cfg_id,
                            'config_obj_name': cfg_object_name
                        }
                    }

                    name = json.dumps(message_text)
                    header = json.dumps(header_text)

                    await notify(
                        name,
                        layer=config.get('layer'),
                        coords=config.get('location'),
                        header=header
                    )
                    ts = datetime.datetime.now()
                    messages.add({
                        'timestamp': ts.isoformat(),
                        'event': f"[DOWN] -- {cfg_name} -- {cfg_id} -- {msg}",
                        'sourceType': cfg_type,
                        'sourceId': device_id
                    })
                await asyncio.sleep(timeout_interval)
            else:
                log.error('Monitoring check error')
        except asyncio.CancelledError as e:
            log.info("Monitoring sb canceled")
            return True
        except Exception as e:
            log.error('Monitoring error {}'.format(repr(e)))
            await asyncio.sleep(timeout_interval)


async def post_messages():
    buffer = []
    while True:
        log.debug("Post messages")
        data = messages.get_all()
        buffer += data
        if buffer:

            try:
                async with api_aiosession.post(cfg['datasources']['sb'] + cfg['notifications']['events']['url'],
                                               json=buffer,
                                               timeout=float(cfg['notifications']['events']['timeout'])) as resp:
                    status_code = resp.status
                    log.debug(f"aiosession post_code {status_code}")
            except aiohttp.ServerTimeoutError:
                log.error('Server timeout. Can\'t post events.')
            except Exception as e:
                log.error('Posting error {}'.format(repr(e)))
            else:
                log.debug(f'Posted events ({len(data)} items) to server')
                buffer = []

        await asyncio.sleep(cfg['notifications']['events']['interval'])  # sleep 60 seconds


async def prepare_data_for_updater(orig_device: dict, d_type: str, d: dict):
    c = orig_device.copy()
    c['name'] = f"{c['name']}"
    c['object_name'] = d['name'] if d_type != 'detectors' else d['address']
    c['id'] = d['id']
    if d_type == 'controllers':
        c['host'] = d['ip']
        c['url'] = f"http://{d['ip']}/"
        c['location'] = d['location']
        c['has_spot'] = d['has_spot']
        c['spot_ip'] = d['spot_ip']
        c['port'] = d['port']
        c['spot_port'] = d['spot_port']
    else:
        ip = d.get('ip', None)
        c['host'] = ip if ip else d.get('controllerIp')

        web_url = d.get('webUrl',
                        f"https://{d['ip']}:{d.get('port')}/" if ip else f"https://{d['controllerIp']}:{d['controllerPort']}/")
        c['url'] = web_url
        c['location'] = d.get('location', None)
    return c


async def device_updater(device: dict):
    d_type = device.get("type")
    if not d_type:
        log.error('No type for device ' + str(device))
        return
    if d_type and d_type not in monitors['devices']:
        monitors['devices'][d_type] = {}

    log.debug(f'{d_type}: Device updater started')
    while True:
        try:
            data = await async_get_from_sb(get_from_sb_session, device)
            inactive_monitors = list(monitors['devices'][d_type].keys())
            for d in data:
                c = await prepare_data_for_updater(device, d_type, d)
                if d['id'] not in monitors['devices'][d_type]:
                    m = asyncio.ensure_future(monitoring(c))
                    monitors['devices'][d_type][d['id']] = dict(info=c, task=m)

                elif monitors['devices'][d_type][d['id']]['info'] != c:
                    log.info(f'Device {d_type} id {d["id"]} changed, restarting monitoring')
                    monitors['devices'][d_type][d['id']]['task'].cancel()
                    m = asyncio.ensure_future(monitoring(c))
                    monitors['devices'][d_type][d['id']] = dict(info=c, task=m)
                    inactive_monitors.remove(d['id'])

                if d['id'] in inactive_monitors:
                    inactive_monitors.remove(d['id'])

            for m_id in inactive_monitors:
                monitors['devices'][d_type][m_id]['task'].cancel()
                monitors['devices'][d_type].pop(m_id, None)
                log.info(f'Monitoring for {d_type} id {m_id} stopped')

        except Exception as e:
            log.error('Unknown error in device updater')
            log.exception(e)

        await asyncio.sleep(cfg["devices"].get('interval', 60))


async def heartbeat():
    while True:
        redis.set('monitoring:heartbeat', 1, 20)
        log.debug("Heartbeat")
        await asyncio.sleep(10)


async def shutdown(_sig, loop):
    await checker_aiosession.close()
    await get_from_sb_session.close()
    await api_aiosession.close()
    tasks = [t for t in asyncio.Task.all_tasks() if t is not
             asyncio.Task.current_task()]
    [task.cancel() for task in tasks]
    await asyncio.gather(*tasks, return_exceptions=True)

    loop.stop()


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser(
        prog='monitoring',
        description='''
                    Usage:
                    \t-c <config file path>: use specified config file,
                    \t-h --help: prints this message
                    '''
    )
    arg_parser.add_argument('-c', '--config_name', nargs='?', default='config.yaml')
    args = arg_parser.parse_args()

    CONFIG_FILE = args.config_name

    # Get config from file
    try:
        with open(CONFIG_FILE, 'r', encoding='utf8') as conf_file:
            cfg = yaml.load(conf_file, Loader=yaml.FullLoader)
    except IOError or FileNotFoundError:
        print(f'Config file "{CONFIG_FILE}" not found')
        raise SystemExit(1)
    logging.config.dictConfig(cfg['logging'])
    log = logging.getLogger()

    validate_config(cfg)

    alerts_users = cfg.get('notifications', {}).get('failsafe_users', [])
    redis_conf = cfg.get('redis', {'host': '127.0.0.1', 'port': 6379})

    redis = redis.Redis(host=redis_conf.get('host', '127.0.0.1'), port=redis_conf.get('port', 6379), db=0)
    get_from_sb_session = aiohttp.ClientSession()
    api_aiosession = aiohttp.ClientSession()
    event_loop = asyncio.get_event_loop()
    monitors = {
        'servers': {},
        'devices': {},
    }

    log.info('monitoring started')

    signals = (signal.SIGINT, signal.SIGTERM)
    for s in signals:
        event_loop.add_signal_handler(s, lambda s=s: asyncio.ensure_future(shutdown(s, event_loop)))

    try:
        SB_LOGIN_TOKEN = ''
        if cfg['datasources']['sb_opts'].get('login', False):
            token = sb_login()
            if token:
                SB_LOGIN_TOKEN = token
            else:
                log.critical('Loopback login error')
                raise SystemExit(1)

        devices = cfg.get('devices', [])
        for key in devices:
            if key != "interval":
                event_loop.create_task(device_updater(devices[key]))

        servers = cfg.get('servers', {})
        for k, s in servers.items():
            s['type'] = 'servers'
            s['id'] = k
            event_loop.create_task(monitoring(s))
        event_loop.create_task(heartbeat())
        event_loop.create_task(post_messages())
        event_loop.run_forever()
    finally:
        log.info("Shutdown")
        event_loop.close()
