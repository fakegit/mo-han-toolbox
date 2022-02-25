#!/usr/bin/env python3
import codecs
import collections
import unicodedata

from mylib.easy import *

CR = '\r'
LF = '\n'
CRLF = '\r\n'


def visual_len(s: str):
    eaw = unicodedata.east_asian_width
    n = len(s)
    n += sum([1 for c in s if eaw(c) == 'W'])
    return n


def decode_fallback_locale(b: bytes, encoding='u8'):
    try:
        return b.decode(encoding=encoding)
    except UnicodeDecodeError:
        return b.decode(encoding=locale.getdefaultlocale()[1])


def encode_default_locale(s: str, encoding: str = locale.getdefaultlocale()[1], **kwargs) -> (str, bytes):
    """str -> (encoding: str, encoded_bytes)"""
    c = codecs.lookup(encoding)
    cn = c.name
    return cn, s.encode(cn, **kwargs)


def split_by_new_line_with_max_length(x: str, length: int):
    parts = []
    while x:
        if len(x) > length:
            part = x[:length]
            stop = part.rfind('\n') + 1
            if stop:
                parts.append(x[:stop])
                x = x[stop:]
            else:
                parts.append(part)
                x = x[length:]
        else:
            parts.append(x)
            break
    return parts


def dedup_periodical_str(s):
    # https://stackoverflow.com/a/29489919/7966259
    i = (s + s)[1:-1].find(s)
    if i == -1:
        return s
    else:
        return s[:i + 1]


@deco_factory_param_value_choices({'logic': ('and', '&', 'AND', 'or', '|', 'OR')})
def simple_partial_query(pattern_list: T.Iterable[str], source_pool: T.Iterable[str],
                         logic: str = 'and',
                         ignore_case: bool = True, enable_regex: bool = False):
    if not enable_regex:
        pattern_list = [re.escape(p) for p in pattern_list]
    if ignore_case:
        flag_val = re.IGNORECASE
    else:
        flag_val = 0
    pl = [re.compile(p, flags=flag_val) for p in pattern_list]
    if logic in ('and', '&', 'AND'):
        r = [s for s in source_pool if not [p for p in pl if not p.search(s)]]
    elif logic in ('or', '|', 'OR'):
        r = [s for s in source_pool if [p for p in pl if p.search(s)]]
    else:
        raise ValueError('logic', logic)
    return dedup_list(r)


def regex_find(pattern, source, dedup: bool = False):
    findall = re.findall(pattern, source)
    r = []
    for e in findall:
        if dedup and e in r:
            continue
        else:
            r.append(e)
    return r


def ellipt_middle(s: str, limit: int, *, the_ellipsis: str = '...', encoding: str = None):
    half_limit = (limit - len(the_ellipsis.encode(encoding=encoding) if encoding else the_ellipsis)) // 2
    common_params = dict(encoding=encoding, the_ellipsis='', limit=half_limit)
    half_s_len = len(s) // 2 + 1
    left = ellipt_end(s[:half_s_len], left_side=False, **common_params)
    right = ellipt_end(s[half_s_len:], left_side=True, **common_params)
    lr = f'{left}{right}'
    if the_ellipsis:
        if len(lr) == len(s):
            return s
        else:
            return f'{left}{the_ellipsis}{right}'
    else:
        return f'{left}{right}'


def ellipt_end(s: str, limit: int, *, the_ellipsis: str = '...', encoding: str = None, left_side=False):
    if encoding:
        def length(x: str):
            return len(x.encode(encoding=encoding))
    else:
        def length(x: str):
            return len(x)
    ellipsis_len = length(the_ellipsis)
    if left_side:
        def strip(x: str):
            return x[1:]
    else:
        def strip(x: str):
            return x[:-1]
    shrunk = False
    limit = limit - ellipsis_len
    if limit <= 0:
        raise ValueError('limit too small', limit)
    while length(s) > limit:
        s = strip(s)
        shrunk = True
    if shrunk:
        if left_side:
            return f'{the_ellipsis}{s}'
        else:
            return f'{s}{the_ellipsis}'
    else:
        return s


def slice_word(x: str):
    x_len = len(x)
    r = collections.defaultdict(list)
    if x_len == 0:
        return r
    r[1] = [*x]
    if x_len == 1:
        return r
    for slice_len in range(2, x_len):
        for i in range(x_len - slice_len + 1):
            r[slice_len].append(x[i:i + slice_len])
    return r
