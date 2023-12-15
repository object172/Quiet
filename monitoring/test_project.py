import pytest
import checkers
import errors

TIMEOUT_TIME = 400


@pytest.mark.timeout(TIMEOUT_TIME)
@pytest.mark.asyncio
async def test_ping_checker_no_config():
    assert await checkers.ping_checker({}) == (False, errors.NO_CONFIG)


@pytest.mark.timeout(TIMEOUT_TIME)
@pytest.mark.asyncio
async def test_ping_checker_localhost():
    assert await checkers.ping_checker({'host': 'localhost'}) == (True, '')


@pytest.mark.timeout(TIMEOUT_TIME)
@pytest.mark.asyncio
async def test_ping_checker_yandex():
    assert await checkers.ping_checker({'host': 'ya.ru'}) == (True, '')


@pytest.mark.timeout(TIMEOUT_TIME)
@pytest.mark.asyncio
async def test_ping_checker_unavailable_address():
    assert await checkers.ping_checker({'host': '172.16.19.253'}) == (False, errors.NOT_AVAILABLE)


@pytest.mark.timeout(TIMEOUT_TIME)
@pytest.mark.asyncio
async def test_ping_checker():
    assert await checkers.ping_checker({'host': '8.8.8.8'}) == (True, '')


@pytest.mark.timeout(TIMEOUT_TIME)
@pytest.mark.asyncio
async def test_http_checker_no_config():
    assert await checkers.http_checker({}) == (False, errors.NO_CONFIG)


@pytest.mark.timeout(TIMEOUT_TIME)
@pytest.mark.asyncio
async def test_http_checker_unavailable():
    assert await checkers.http_checker({'url': 'thishostdoesnotexistatall.ru'}) == (False, errors.NO_HTTP)


@pytest.mark.timeout(TIMEOUT_TIME)
@pytest.mark.asyncio
async def test_service_checker_no_config():
    assert await checkers.service_checker({}) == (False, errors.NO_CONFIG)


@pytest.mark.timeout(TIMEOUT_TIME)
@pytest.mark.asyncio
async def test_service_checker_eights_wrong_cfg_1():
    assert await checkers.service_checker({'host': '8.8.8.8'}) == (False, errors.NO_CONFIG)


@pytest.mark.timeout(TIMEOUT_TIME)
@pytest.mark.asyncio
async def test_service_checker_eights_wrong_cfg_2():
    assert await checkers.service_checker(
        {'host': '8.8.8.8', 'service_name': 'nginx'}) == (False, errors.NO_CONFIG)


@pytest.mark.timeout(TIMEOUT_TIME)
@pytest.mark.asyncio
async def test_service_checker_eights_wrong_cfg_3():
    assert await checkers.service_checker(
        {'host': '8.8.8.8', 'service_name': 'nginx', 'ssh_user': 'none'}) == (False, errors.NO_SERVICE)


@pytest.mark.timeout(TIMEOUT_TIME)
@pytest.mark.asyncio
async def test_service_checker_no_service():
    assert await checkers.service_checker(
        {'host': 'localhost', 'service_name': 'nosuchservice'}) == (False, errors.NO_SERVICE)
