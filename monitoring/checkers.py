import os
import errors
import aiohttp
import asyncio
import aiosnmp
import logging

LOCAL = [
    'localhost',
    '127.0.0.1',
]

checker_aiosession = aiohttp.ClientSession()

async def ping(host: str, timeout: int = 1):
    if not host:
        return False
    results = []
    for _ in range(5):
        with open(os.devnull, 'w') as devnull:
            pr = await asyncio.create_subprocess_shell(
                f'ping -c 1 -W {str(timeout)} {host}',
                stdout=devnull,
                stderr=devnull,
            )
        code = await pr.wait()
        results.append(True if code == 0 else False)
    return any(results)


async def ping_checker(config: dict) -> (bool, str):
    if config.get('model', None) == 'SmartVisionMock':
        return True, ''
    host = config.get('host', None)
    spot_host = None
    if config.get('has_spot'):
        spot_host = config.get('spot_ip')
    if not host and not spot_host:
        return False, errors.NO_CONFIG
    if host in LOCAL or spot_host in LOCAL:
        return True, ''
    timeout = config.get('timeout', 1)
    host_ping = await ping(host, timeout)
    spot_ping = await ping(spot_host, timeout)
    result = host_ping or spot_ping
    return (True, '') if result else (False, errors.NOT_AVAILABLE)


async def http_checker(config: dict) -> (bool, str):
    if config.get('model', None) == 'SmartVisionMock':
        return True, ''
    url = config.get('url', None)
    if not url:
        return False, errors.NO_CONFIG
    timeout = config.get('timeout', 2)
    try:
        async with checker_aiosession.get(url, timeout=timeout, ssl=False) as resp:
            status = resp.status
    except Exception as e:
        return False, errors.NO_HTTP
    else:
        if status not in range(200, 300):
            return False, errors.NO_HTTP
    return True, ''

async def service_checker(config: dict) -> (bool, str):
    host = config.get('host', None)
    if not host:
        return False, errors.NO_CONFIG

    timeout = config.get('timeout', 2)

    service_name = config.get('service_name', None)
    if not service_name:
        return False, errors.NO_CONFIG

    command = f'systemctl is-active {service_name}'
    if host not in LOCAL:
        ssh_user = config.get('ssh_user', None)
        if not ssh_user:
            return False, errors.NO_CONFIG
        command = f'ssh -oStrictHostKeyChecking=no -o ConnectTimeout={timeout} {ssh_user}@{host} ' + command

    with open(os.devnull, 'w') as devnull:
        pr = await asyncio.create_subprocess_shell(
            command,
            stdout=devnull,
            stderr=devnull,
        )
    code = await pr.wait()
    return (True, '') if code == 0 else (False, errors.NO_SERVICE)


async def snmp_checker(config: dict) -> (bool, str):
    host = config.get('host', None)
    port = config.get('port', '161')
    spot_host = None
    if config.get('has_spot'):
        spot_host = config.get('spot_ip')
    if not host and not spot_host:
        return False, errors.NO_CONFIG
    if host in LOCAL:
        return True, ''
    snmp_ping = await snmp_get(host, port)
    spot_ping = await ping(spot_host)
    result = spot_ping or snmp_ping
    return (True, '') if result else (False, errors.NO_SNMP)


async def snmp_get(host: str, port: str):
    logging.debug(f"Get SNMP {host}:{port}")
    if not host:
        return False
    try:
        async with aiosnmp.Snmp(host=host, port=port, community="UTMC") as snmp:
            r = await snmp.get('1.3.6.1.2.1.1.5.0')
            return True
    except Exception as e:
        logging.debug(f'Controller {host}:{port} unawail')
        return False

async def http_get(url: str, timeout: int = 2) -> bool:
    logging.debug(f"Get http {url}")
    try:
        async with checker_aiosession.get(url, timeout=timeout, ssl=False) as resp:
            status = resp.status
    except Exception as e:
        return False
    else:
        if status not in range(200, 300):
            return False
    return True


CHECKERS = {
    'ping': ping_checker,
    'service': service_checker,
    'http': http_checker,
    'snmp': snmp_checker,
    'snmp_get': snmp_get,
    'http_get': http_get
}
