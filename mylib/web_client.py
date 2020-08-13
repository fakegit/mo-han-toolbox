#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Library for website operation"""

import http.cookiejar
import json
import os
import re
from concurrent.futures.thread import ThreadPoolExecutor
from io import StringIO
from typing import List

import lxml.html
import requests.utils

from mylib.tricks import JSONType

MAGIC_TXT_NETSCAPE_HTTP_COOKIE_FILE = '# Netscape HTTP Cookie File'
USER_AGENT_FIREFOX_WIN10 = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:64.0) Gecko/20100101 Firefox/64.0'

HTMLElementTree = lxml.html.HtmlElement


class WebRequestFailure(Exception):
    code = None
    desc = None
    data = None

    def __init__(self, code: int, reason: str = None, data=None):
        self.code = int(code)
        self.desc = str(reason)
        self.data = data


def decode_html_char_ref(x: str) -> str:
    return re.sub(r'&amp;', '&', x, flags=re.I)


def get_html_element_tree(url, **kwargs) -> HTMLElementTree:
    r = requests.get(url, **kwargs)
    if r.ok:
        return lxml.html.document_fromstring(r.text)
    else:
        raise ConnectionError(r.status_code, r.reason)


def convert_cookies_json_to_netscape(json_data_or_filepath: JSONType or str, disable_filepath: bool = False) -> str:
    from .os_util import read_json_file
    if not disable_filepath and os.path.isfile(json_data_or_filepath):
        json_data = read_json_file(json_data_or_filepath)
    else:
        json_data = json_data_or_filepath
    cookies = ensure_json_cookies(json_data)
    tab = '\t'
    false_ = 'FALSE' + tab
    true_ = 'TRUE' + tab
    lines = [MAGIC_TXT_NETSCAPE_HTTP_COOKIE_FILE]
    for c in cookies:
        http_only_prefix = '#HttpOnly_' if c['httpOnly'] else ''
        line = http_only_prefix + c['domain'] + tab
        if c['hostOnly']:
            line += false_
        else:
            line += true_
        line += c['path'] + tab
        if c['secure']:
            line += true_
        else:
            line += false_
        line += '{}\t{}\t{}'.format(c['expirationDate'], c['name'], c['value'])
        lines.append(line)
    return '\n'.join(lines)


def convert_cookies_file_json_to_netscape(src, dst=None) -> str:
    from .os_util import fs_rename, ensure_open_file
    if not os.path.isfile(src):
        raise FileNotFoundError(src)
    dst = dst or src + '.txt'
    with ensure_open_file(dst, 'w') as f:
        f.write(convert_cookies_json_to_netscape(src))
        return dst


def ensure_json_cookies(json_data) -> list:
    if isinstance(json_data, list):
        cookies = json_data
    elif isinstance(json_data, dict):
        if 'cookies' in json_data:
            if isinstance(json_data['cookies'], list):
                cookies = json_data['cookies']
            else:
                raise TypeError("{}['cookies'] is not list".format(json_data))
        else:
            raise TypeError("dict '{}' has no 'cookies'".format(json_data))
    else:
        raise TypeError("'{}' is not list or dict".format(json_data))
    return cookies


def cookies_dict_from_json(json_data_or_filepath: JSONType or str, disable_filepath: bool = False) -> dict:
    from .os_util import read_json_file
    if not disable_filepath and os.path.isfile(json_data_or_filepath):
        json_data = read_json_file(json_data_or_filepath)
    else:
        json_data = json_data_or_filepath
    d = {}
    cookies = ensure_json_cookies(json_data)
    for c in cookies:
        d[c['name']] = c['value']
    return d


class CurlCookieJar(http.cookiejar.MozillaCookieJar):
    """fix MozillaCookieJar ignoring '#HttpOnly_'"""

    def load(self, filename=None, ignore_discard=False, ignore_expires=False):
        http_only_prefix = '#HttpOnly_'
        http_only_prefix_len = len(http_only_prefix)
        if filename is None:
            if self.filename is not None:
                filename = self.filename
            else:
                # noinspection PyUnresolvedReferences
                raise ValueError(http.cookiejar.MISSING_FILENAME_TEXT)

        with open(filename) as f:
            lines = [e[http_only_prefix_len:] if e.startswith(http_only_prefix) else e for e in f.readlines()]

        with StringIO() as f:
            f.writelines(lines)
            f.seek(0)
            # noinspection PyUnresolvedReferences
            self._really_load(f, filename, ignore_discard, ignore_expires)


def cookies_dict_from_netscape_file(filepath: str) -> dict:
    from .os_util import read_json_file
    cj = CurlCookieJar(filepath)
    cj.load()
    return requests.utils.dict_from_cookiejar(cj)


def cookies_dict_from_file(filepath: str) -> dict:
    if not os.path.isfile(filepath):
        raise FileNotFoundError(filepath)
    if filepath.endswith('.json'):
        d = cookies_dict_from_json(filepath)
    else:
        d = cookies_dict_from_netscape_file(filepath)
    return d


def cookie_str_from_dict(cookies: dict) -> str:
    cookies_l = ['{}={}'.format(k, v) for k, v in cookies.items()]
    cookie = '; '.join(cookies_l)
    return cookie


def get_headers_of_user_agent(user_agent: str = None, headers: dict = None) -> dict:
    h = headers or {}
    h['User-Agent'] = user_agent or USER_AGENT_FIREFOX_WIN10
    return h


def get_headers_of_cookie(cookies_data: dict or str, headers: dict = None) -> dict:
    h = headers or get_headers_of_user_agent()
    if isinstance(cookies_data, dict):
        cookie = cookie_str_from_dict(cookies_data)
    elif isinstance(cookies_data, str):
        cookie = cookies_data
    else:
        raise TypeError('cookies_data', (dict, str))
    h['Cookie'] = cookie
    return h


def get_phantomjs_splinter(proxy=None, show_image=False, window_size=(1024, 1024)):
    import splinter
    from .os_util import TEMPDIR

    extra_argv = ['--webdriver-loglevel=WARN']
    if proxy:
        extra_argv.append('--proxy={}'.format(proxy))
    if not show_image:
        extra_argv.append('--load-images=no')

    b = splinter.Browser(
        'phantomjs',
        service_log_path=os.path.join(TEMPDIR, 'ghostdriver.log'),
        user_agent=USER_AGENT_FIREFOX_WIN10,
        service_args=extra_argv,
    )
    b.driver.set_window_size(*window_size)
    return b


def get_firefox_splinter(headless=True, proxy: str = None, **kwargs):
    import splinter
    from .os_util import TEMPDIR
    config = {'service_log_path': os.path.join(TEMPDIR, 'geckodriver.log'),
              'headless': headless}
    config.update(kwargs)
    profile_dict = {}
    if proxy:
        from urllib.parse import urlparse
        prefix = 'network.proxy.'
        profile_dict[prefix + 'type'] = 1
        proxy_parse = urlparse(proxy)
        scheme = proxy_parse.scheme
        netloc = proxy_parse.netloc
        try:
            host, port = netloc.split(':')
            port = int(port)
        except ValueError:
            raise ValueError(proxy)
        if scheme in ('http', 'https', ''):
            profile_dict[prefix + 'http'] = host
            profile_dict[prefix + 'http_port'] = port
            profile_dict[prefix + 'https'] = host
            profile_dict[prefix + 'https_port'] = port
        elif scheme.startswith('socks'):
            profile_dict[prefix + 'socks'] = host
            profile_dict[prefix + 'socks_port'] = port
        else:
            raise ValueError(proxy)
    browser = splinter.Browser(driver_name='firefox', profile_preferences=profile_dict, **config)
    return browser


def get_zope_splinter(**kwargs):
    import splinter
    return splinter.Browser(driver_name='zope.testbrowser', **kwargs)


get_browser = {
    'splinter.phantomjs': get_phantomjs_splinter,
}


class WebDownloadExecutor(ThreadPoolExecutor):
    pass