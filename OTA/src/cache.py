#!/usr/bin/python3
# -*- coding: utf-8 -*-

import datetime
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=128)
class InMemoryCache:
    """Simple in-memory caching using dict lookup with(out) support for timeouts"""

    _cache = {}  # global cache, thread-safe by default

    def __init__(self, timeout=3600):
        self._timeout = timeout

    def add(self, url, content):
        if url in self._cache: return
        logger.debug("Caching contents of %s", url)
        if not isinstance(content, (str, bytes)):
            raise TypeError("a bytes-like object is required, not {}".format(type(content).__name__))
        self._cache[url] = (datetime.datetime.utcnow(), content)

    def get(self, url):
        try:
            created, content = self._cache[url]
        except KeyError:
            pass
        else:
            logger.debug("Cache HIT for %s", url)
            return content
        logger.debug("Cache MISS for %s", url)
        return None
