#!/usr/bin/env python3
# encoding=utf8

import argparse
import functools
import hashlib
import importlib.util
import sqlite3
import sys
from collections import defaultdict
from functools import wraps
from inspect import signature
from queue import Queue
from threading import Thread
from time import sleep
from typing import Dict, Iterable, Generator, Tuple, Iterator, Any

import inflection

from .log import get_logger
from .math import int_is_power_of_2
from .tricks_ import *
from .type import Decorator, QueueType


class VoidDuck:
    """a void, versatile, useless and quiet duck, called in any way, return nothing, raise nothing"""

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, item):
        return self

    def __call__(self, *args, **kwargs):
        return self

    def __bool__(self):
        return False


def range_from_expr(expr: str) -> Generator:
    sections = [[int(n.strip() or 1) for n in e.split('-')] for e in expr.split(',')]
    for s in sections:
        yield from range(s[0], s[-1] + 1)


def deco_factory_args_choices(choices: Dict[int or str, Iterable] or None, *args, **kwargs) -> Decorator:
    """decorator factory: force arguments of a func limited inside the given choices

    :param choices: a dict which describes the choices of arguments
        the key of the dict must be either the index of args or the key(str) of kwargs
        the value of the dict must be an iterable
        choices could be supplemented by *args and **kwargs
        choices could be empty or None"""
    choices = choices or {}
    for i in range(len(args)):
        choices[i] = args[i]
    choices.update(kwargs)
    err_fmt = "argument {}={} is not valid, choose from {})"

    def deco(target):
        @wraps(target)
        def tgt(*args, **kwargs):
            for arg_index in range(len(args)):
                param_name = target.__code__.co_varnames[arg_index]
                value = args[arg_index]
                if arg_index in choices and value not in choices[arg_index]:
                    raise ValueError(err_fmt.format(param_name, choices[arg_index]))
                elif param_name in choices and value not in choices[param_name]:
                    raise ValueError(err_fmt.format(param_name, value, choices[param_name]))
            for param_name in kwargs:
                value = kwargs[param_name]
                if param_name in choices and value not in choices[param_name]:
                    raise ValueError(err_fmt.format(param_name, value, choices[param_name]))

            return target(*args, **kwargs)

        return tgt

    return deco


def deco_factory_retry(retry_exceptions=None, max_retries: int = 3,
                       enable_default=False, default=None,
                       exception_predicate: Callable[[Exception], bool] = None,
                       exception_queue: QueueType = None) -> Decorator:
    """decorator factory: force a func re-running for several times on exception(s)"""
    retry_exceptions = retry_exceptions or ()
    predicate = exception_predicate or (lambda e: True)
    max_retries = int(max_retries)
    initial_counter = max_retries if max_retries < 0 else max_retries + 1

    def decorator(func):
        @wraps(func)
        def decorated_func(*args, **kwargs):
            cnt = initial_counter
            err = None
            while cnt:
                try:
                    return func(*args, **kwargs)
                except retry_exceptions as e:
                    if predicate(e):
                        if exception_queue:
                            exception_queue.put(e)
                        err = e
                        cnt -= 1
                        continue
                    else:
                        if enable_default:
                            return default
                        raise
            else:
                if enable_default:
                    return default
                raise err

        return decorated_func

    return decorator


def modify_and_import(module_path: str, code_modifier: str or Callable, package_path: str = None,
                      output: bool = False, output_file: str = 'tmp.py'):
    # How to modify imported source code on-the-fly?
    #     https://stackoverflow.com/a/41863728/7966259  (answered by Martin Valgur)
    # Modules and Packages: Live and Let Die!  (by David Beazley)
    #     http://www.dabeaz.com/modulepackage/ModulePackage.pdf
    #     https://www.youtube.com/watch?v=0oTh1CXRaQ0
    spec = importlib.util.find_spec(module_path, package_path)
    if isinstance(code_modifier, str):
        source = code_modifier
    else:
        source = code_modifier(spec.loader.get_source(module_path))
    if output:
        with open(output_file, 'w') as f:
            f.write(source)
    module = importlib.util.module_from_spec(spec)
    code_obj = compile(source, module.__spec__.origin, 'exec')
    exec(code_obj, module.__dict__)
    sys.modules[module_path] = module
    return module


def singleton(cls):
    _instances = {}

    def get_instance(*args, **kwargs):
        if cls not in _instances:
            _instances[cls] = cls(*args, **kwargs)
        return _instances[cls]

    return get_instance


def str_ishex(s):
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


def arg_type_pow2(x):
    i = int(x)
    if int_is_power_of_2(i):
        return i
    else:
        raise argparse.ArgumentTypeError("'{}' is not power of 2".format(x))


def arg_type_range_factory(x_type, x_range_condition: str):
    def arg_type_range(x):
        xx = x_type(x)
        if eval(x_range_condition):
            return xx
        else:
            raise argparse.ArgumentTypeError("'{}' not in range {}".format(x, x_range_condition))

    return arg_type_range


class ArgParseCompactHelpFormatter(argparse.HelpFormatter):
    def _format_action_invocation(self, action):
        if not action.option_strings or action.nargs == 0:
            # noinspection PyProtectedMember
            return super()._format_action_invocation(action)
        default = self._get_default_metavar_for_optional(action)
        args_string = self._format_args(action, default)
        return ', '.join(action.option_strings) + '  ' + args_string


def new_argument_parser(formatter_class=ArgParseCompactHelpFormatter):
    return argparse.ArgumentParser(formatter_class=formatter_class)


def deco_with_self_context(target):
    """decorator: wrap a class method inside a `with self: ...` context"""

    def tgt(self, *args, **kwargs):
        with self:
            return target(self, *args, **kwargs)

    return tgt


def deco_factory_with_context(context_obj) -> Decorator:
    def deco(target):
        def tgt(*args, **kwargs):
            with context_obj:
                return target(*args, **kwargs)

        return tgt

    return deco


def getitem_default(x, index_or_key, default=None):
    try:
        return x[index_or_key]
    except (IndexError, KeyError):
        return default


def remove_from_list(source: Iterable, rmv_set: Iterable) -> list:
    """return a list, which contains elements in source but not in rmv_set"""
    return [x for x in source if x not in rmv_set]


def dedup_list(source: Iterable) -> list:
    r = []
    [r.append(e) for e in source if e not in r]
    return r


def get_kwargs(**kwargs):
    return kwargs


def default_dict_tree():
    return defaultdict(default_dict_tree)


class Attreebute:
    """Attribute Tree"""
    __exclude__ = ['__data__', '__index__']

    def __init__(self, tree_data: dict = None, json_filepath: str = None, **kwargs):
        self.__data__ = {}
        if tree_data:
            self.__from_dict__(tree_data)
        if json_filepath:
            self.__from_json__(json_filepath)
        if kwargs:
            self.__from_dict__(kwargs)

    def __from_dict__(self, tree_data: dict):
        for k, v in tree_data.items():
            if isinstance(v, dict):
                self.__dict__[k] = Attreebute(tree_data=v)
            else:
                self.__dict__[k] = v
            self.__update_data__(k, self[k])

    def __from_json__(self, json_filepath: str):
        from .fs_util import read_json_file
        self.__from_dict__(read_json_file(json_filepath))

    def __to_dict__(self):
        return self.__data__

    def __to_json__(self, json_filepath: str):
        from .fs_util import write_json_file
        write_json_file(json_filepath, self.__data__, indent=4)

    def __query__(self, *args, **kwargs):
        if not args and not kwargs:
            return self.__table__

    __call__ = __query__

    def __update_data__(self, key, value):
        if isinstance(value, Attreebute):
            self.__data__[key] = value.__data__
        elif isinstance(value, list):
            self.__data__[key] = [e.__data__ if isinstance(e, Attreebute) else e for e in value]
        elif key not in self.__exclude__:
            self.__data__[key] = value

    @property
    def __map__(self):
        tmp = {}
        for k in self.__dict__:
            v = self[k]
            if isinstance(v, Attreebute):
                for vk in v.__map__:
                    tmp['{}.{}'.format(k, vk)] = v.__map__[vk]
            elif k not in self.__exclude__:
                tmp[k] = v
        return tmp

    @property
    def __table__(self):
        return sorted(self.__map__.items())

    @staticmethod
    def __valid_path__(path):
        if '.' in str(path):
            key, sub_path = path.split('.', maxsplit=1)
        else:
            key, sub_path = path, None
        return key, sub_path

    def __getitem__(self, item):
        key, sub_path = self.__valid_path__(item)
        try:
            target = self.__dict__[key]
        except KeyError:
            target = self.__dict__[key] = Attreebute()
            self.__update_data__(key, target)
        if sub_path:
            return target[sub_path]
        else:
            return target

    __getattr__ = __getitem__

    def __setitem__(self, key, value):
        self_key, sub_path = self.__valid_path__(key)
        if sub_path:
            if self_key in self:
                self[self_key][sub_path] = value
            else:
                target = self.__dict__[self_key] = Attreebute()
                self.__update_data__(self_key, target)
                target[sub_path] = value
        else:
            self.__dict__[self_key] = value
            self.__update_data__(self_key, value)

    __setattr__ = __setitem__

    def __delitem__(self, key):
        self_key, sub_path = self.__valid_path__(key)
        if sub_path:
            del self.__dict__[self_key][sub_path]
        else:
            del self.__dict__[self_key]
            del self.__data__[self_key]

    def __delattr__(self, item):
        try:
            self.__delitem__(item)
        except KeyError as e:
            raise AttributeError(*e.args)

    def __iter__(self):
        yield from self.__dict__

    def __contains__(self, item):
        return item in self.__dict__

    def __bool__(self):
        return bool(self.__data__)

    def __len__(self):
        return len(self.__dict__)

    def __repr__(self):
        table = self.__table__
        half = len(table) // 2
        head_end, mid_begin, mid_end, tail_begin = 6, half - 3, half + 3, -6
        max_ = 3 * (6 + 1)
        lines = [super(Attreebute, self).__repr__()]
        if len(table) >= max_:
            lines.extend(['{}={}'.format(k, v) for k, v in table[:head_end]])
            lines.append('...')
            lines.extend(['{}={}'.format(k, v) for k, v in table[mid_begin:mid_end]])
            lines.append('...')
            lines.extend(['{}={}'.format(k, v) for k, v in table[tail_begin:]])
        else:
            lines.extend(['{}={}'.format(k, v) for k, v in table])
        return '\n'.join(lines)

    def __str__(self):
        return '\n'.join(['{}={}'.format(k, v) for k, v in self.__table__])


def until_return_try(schedule: Iterable[dict], unified_exception=Exception):
    """try through `schedule`, bypass specified exception, until sth returned, then return it.
    format of every task inside `schedule`:
        {'callable':..., 'args':(...), 'kwargs':{...}, 'exception':...}
    if a task in `schedule` has `exception` specified for its own, the `unified_exception` will be ignored
    if a task has wrong format, it will be ignored"""
    for task in schedule:
        if 'exception' in task:
            exception = task['exception']
        else:
            exception = unified_exception
        if 'args' in task:
            args = task['args']
        else:
            args = ()
        if 'kwargs' in task:
            kwargs = task['kwargs']
        else:
            kwargs = {}
        try:
            return task['callable'](*args, **kwargs)
        except exception:
            pass


def hex_hash(data: bytes, algorithm: str = 'md5') -> str:
    return getattr(hashlib, algorithm.replace('-', '_'))(data).hexdigest()


def get_args_kwargs(*args, **kwargs) -> Tuple[list, dict]:
    return list(args), kwargs


class WrappedList(list):
    pass


def seconds_from_colon_time(t: str) -> float:
    def greater_0(x):
        return x >= 0

    def less_60(x):
        return x < 60

    def less_24(x):
        return x < 24

    t_value_error = ValueError(t)
    parts = t.split(':')
    last = parts[-1]
    before_last = parts[:-1]
    after_1st = parts[1:]
    after_2nd = parts[2:]
    n = len(parts)

    if 4 < n < 1:
        raise t_value_error
    try:
        float(last)
        [int(p) for p in before_last]
    except ValueError:
        raise t_value_error
    if not all([greater_0(float(x)) for x in after_1st]):
        raise t_value_error
    sign = -1 if t.startswith('-') else 1

    if n == 1:
        total = float(t)
    elif n == 4:
        if not all([less_60(float(x)) for x in after_2nd]):
            raise t_value_error
        d, h, m = [abs(int(x)) for x in before_last]
        if not less_24(h):
            raise t_value_error
        s = float(last)
        total = (d * 24 + h) * 3600 + m * 60 + s
    else:
        if not all([less_60(float(x)) for x in after_1st]):
            raise t_value_error
        total = 0
        for x in parts:
            total = total * 60 + abs(float(x))

    return total if total == 0 else total * sign


class EverythingFineNoError(Exception):
    pass


class AttributeInflection:
    def __getattribute__(self, item):
        if item == '__dict__':
            return object.__getattribute__(self, item)
        item_camel = inflection.camelize(item, False)
        underscore = inflection.underscore
        if item in self.__dict__:
            return self.__dict__[item]
        elif item_camel in self.__dict__ or item in [underscore(k) for k in self.__dict__]:
            return self.__dict__[item_camel]
        else:
            return object.__getattribute__(self, item)


def percentage(quotient, digits: int = 1) -> str:
    fmt = '{:.' + str(digits) + '%}'
    return fmt.format(quotient)


def width_of_int(x: int):
    return len(str(x))


def meta_retry_iter(max_retries=0,
                    throw_exceptions=(),
                    swallow_exceptions=(Exception,),
                    ):
    throw_exceptions = throw_exceptions or ()
    swallow_exceptions = swallow_exceptions or Exception
    if max_retries is None:
        max_retries = -1
    max_retries = int(max_retries)
    if max_retries >= 0:
        max_try = max_retries + 1
    else:
        max_try = max_retries

    def retry_gen(callee: Callable, *args, **kwargs) -> Generator[Tuple[int, Exception or Any], None, None]:
        cnt = max_try
        while cnt:
            try:
                yield cnt, callee(*args, **kwargs)
            except throw_exceptions:
                raise
            except swallow_exceptions as e:
                cnt -= 1
                yield cnt, e

    return retry_gen


class CLIArgumentList(list):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.add(*args, **kwargs)

    def add_arg(self, arg):
        if isinstance(arg, str):
            self.append(arg)
        elif isinstance(arg, (Iterable, Iterator)):
            for a in arg:
                self.add_arg(a)
        else:
            self.append(str(arg))
        return self

    def add_kwarg(self, key: str, value):
        if isinstance(key, str):
            if isinstance(value, str):
                self.append(key)
                self.append(value)
            elif isinstance(value, (Iterable, Iterator)):
                for v in value:
                    self.add_kwarg(key, v)
            elif value is True:
                self.append(key)
            elif value is None or value is False:
                pass
            else:
                self.append(key)
                self.append(str(value))
        return self

    def add(self, *args, **kwargs):
        for a in args:
            self.add_arg(a)
        for k, v in kwargs.items():
            self.add_kwarg(*self.kwarg_to_long_option(k, v))
        return self

    @staticmethod
    def kwarg_to_long_option(key: str, value):
        if '_' in key:
            k = '--' + '-'.join(key.split('_'))
        else:
            k = '-' + key
        return k, value


def make_kwargs_dict(**kwargs):
    return kwargs


def eval_or_str(x: str):
    from ast import literal_eval
    try:
        return literal_eval(x)
    except (ValueError, SyntaxError):
        return x


def make_ternary_call(callee: callable, *args, **kwargs):
    return callee, args, kwargs


def meta_wrap_in_process(callee, before=None, after=None):
    def wrap(*args, **kwargs):
        if before:
            for _callee, _args, _kwargs in before:
                _callee(*_args, **_kwargs)
        r = callee(*args, **kwargs)
        if after:
            for _callee, _args, _kwargs in before:
                _callee(*_args, **_kwargs)
        return r

    return wrap


class ExceptionWithKwargs(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.kwargs = kwargs

    def __str__(self):
        args_str = ', '.join([str(a) for a in self.args])
        kwargs_str = ', '.join([f'{k}={v}' for k, v in self.kwargs.items()])
        return f"({', '.join((args_str, kwargs_str))})"

    def __repr__(self):
        return f'{self.__class__.__name__}{self}'


def thread_factory(group: None = None, name: str = None, daemon: bool = False):
    thread_kwargs = {'group': group, 'name': name, 'daemon': daemon}

    def new_thread(callee: Callable, *args, **kwargs):
        return Thread(target=callee, args=args, kwargs=kwargs, **thread_kwargs)

    return new_thread


class NonBlockingCaller:
    class StillRunning(ExceptionWithKwargs):
        pass

    class Stopped(Exception):
        pass

    def __init__(self, target: Callable, *args, **kwargs):
        self.triple = target, args, kwargs
        self._running = False
        self.run()

    @property
    def running(self):
        return self._running

    def thread(self):
        try:
            callee, args, kwargs = self.triple
            self._result_queue.put(callee(*args, **kwargs), block=False)
        except Exception as e:
            self._exception_queue.put(e, block=False)
        finally:
            self._running = False

    def run(self):
        if self._running:
            return False
        self._running = True
        self._result_queue = Queue(maxsize=1)
        self._exception_queue = Queue(maxsize=1)
        self._thread = thread_factory(daemon=True)(self.thread)
        self._thread.start()
        return True

    def get(self, wait):
        """return target result, or raise target exception, or raise NonBlockingCaller.StillRunning"""
        rq = self._result_queue
        eq = self._exception_queue
        if rq.qsize():
            return rq.get(block=False)
        elif eq.qsize():
            raise rq.get(block=False)
        else:
            sleep(wait)
            target, args, kwargs = self.triple
            raise self.StillRunning(target, *args, **kwargs)


def deco_factory_copy_signature(signature_source: Callable):
    # https://stackoverflow.com/a/58989918/7966259
    def deco(target: Callable):
        @functools.wraps(target)
        def tgt(*args, **kwargs):
            signature(signature_source).bind(*args, **kwargs)
            return target(*args, **kwargs)

        tgt.__signature__ = signature(signature_source)
        return tgt

    return deco


class SimpleSQLiteTable:
    def __init__(self, db_path: str, table_name: str, table_columns: list or tuple, *,
                 converters: dict = None, adapters: dict = None):
        logger = get_logger(f'{__name__}.{self.__class__.__name__}')
        db_path = db_path or ':memory:'
        if converters:
            self.connection = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        else:
            self.connection = sqlite3.connect(db_path)
        self.cursor = self.connection.cursor()
        for k, v in (converters or {}).items():
            sqlite3.register_converter(k, v)
        for k, v in (adapters or {}).items():
            sqlite3.register_adapter(k, v)
        self.table_name = table_name
        self.sql_values_qmark = f'values ({", ".join("?" * len(table_columns))})'
        self.cursor.execute(f'create table if not exists {self.table_name} ({", ".join(table_columns)})')

    def insert(self, values, replace=True):
        if replace:
            sql = f'insert or replace into {self.table_name}'
        else:
            sql = f'insert into {self.table_name}'
        try:
            col_keys = f'({", ".join(values.keys())})'
            col_values = f'({", ".join([f":v" for v in values.values()])})'
            self.cursor.execute(f'{sql} {col_keys} values {col_values}', values)
        except AttributeError:
            self.cursor.execute(f'{sql} {self.sql_values_qmark}', values)
        return self

    def update(self, where: str = None, **data):
        keys_qmark = [f'{k}=?' for k in data.keys()]
        sql = f'update {self.table_name} set {", ".join(keys_qmark)}'
        if where:
            sql = f'{sql} where {where}'
        self.cursor.execute(sql, tuple(data.values()))
        return self

    def select(self, where: str = None, *columns):
        sql = f'select {", ".join(columns or "*")} from {self.table_name}'
        if where:
            sql = f'{sql} where {where}'
        self.cursor.execute(sql)
        return self.cursor.fetchall()

    get = select

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self.cursor.close()
        self.connection.close()


def module_sqlitedict_with_dill():
    import dill
    import sqlitedict
    sqlitedict.dumps = dill.dumps
    sqlitedict.loads = dill.loads
    sqlitedict.PICKLE_PROTOCOL = dill.HIGHEST_PROTOCOL
    return sqlitedict


def deco_factory_keyboard_interrupt(exit_code,
                                    called_in_except_block: Any = VoidDuck,
                                    called_in_finally_block: Any = VoidDuck):
    def deco(target):
        @deco_factory_copy_signature(target)
        def tgt(*args, **kwargs):
            try:
                return target(*args, **kwargs)
            except KeyboardInterrupt:
                called_in_except_block()
                sys.exit(exit_code)
            finally:
                called_in_finally_block()

        return tgt

    return deco


def ensure_import_package(name: str, package: str = None, *, notify=True, prompt=True):
    try:
        return importlib.import_module(name, package)
    except ModuleNotFoundError:
        ...
