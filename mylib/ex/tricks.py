#!/usr/bin/env python3
# encoding=utf8
import ast
import codecs
import collections
import functools
import hashlib
import inspect
import locale
import queue
import sqlite3
import subprocess
import sys
import time
from time import sleep

from mylib.easy import io, T, logging, VoidDuck, deco_factory_copy_signature, ExceptionWithKwargs, thread_factory


class AttributeInflection:
    def __getattribute__(self, item):
        import inflection
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


def module_sqlitedict_with_dill(*, dill_detect_trace=False):
    import dill
    import sqlitedict
    dill.detect.trace(dill_detect_trace)
    sqlitedict.dumps = dill.dumps
    sqlitedict.loads = dill.loads
    sqlitedict.PICKLE_PROTOCOL = dill.HIGHEST_PROTOCOL
    return sqlitedict


def is_picklable_with_dill_trace(obj, exact=False, safe=False, **kwds):
    import dill
    args = (obj,)
    kwargs = dict(exact=exact, safe=safe, **kwds)
    if dill.pickles(*args, **kwargs):
        return True
    else:
        dill.detect.trace(True)
        r = dill.pickles(*args, **kwargs)
        dill.detect.trace(False)
        return r


def monitor_sub_process_tty_frozen(p: subprocess.Popen, timeout=30, wait=1,
                                   encoding=None, ignore_decode_error=True,
                                   ):
    import psutil

    def decode(inc_decoder: codecs.IncrementalDecoder, new_bytes: bytes) -> str or None:
        chars = inc_decoder.decode(new_bytes)
        if chars:
            inc_decoder.reset()
            return chars

    if not encoding:
        encoding = locale.getdefaultlocale()[1]
    _out = io.BytesIO()
    _err = io.BytesIO()
    monitoring = []
    monitor_stdout = bool(p.stdout)
    monitor_stderr = bool(p.stderr)
    nb_caller = NonBlockingCaller
    if monitor_stdout:
        monitoring.append(
            (nb_caller(p.stdout.read, 1), codecs.getincrementaldecoder(encoding)(), sys.stdout, _out))
    if monitor_stderr:
        monitoring.append(
            (nb_caller(p.stderr.read, 1), codecs.getincrementaldecoder(encoding)(), sys.stderr, _err))
    t0 = time.perf_counter()
    while 1:
        if time.perf_counter() - t0 > timeout:
            for p in psutil.Process(p.pid).children(recursive=True):
                p.kill()
            p.kill()
            _out.seek(0)
            _err.seek(0)
            raise ProcessTTYFrozen(p, _out, _err)
        for nb_reader, decoder, output, bytes_io in monitoring:
            decoder: codecs.IncrementalDecoder
            try:
                b = nb_reader.get(wait)
                if b:
                    t0 = time.perf_counter()
                    bytes_io.write(b)
                    nb_reader.run()
                    if output:
                        try:
                            s = decode(decoder, b)
                            if s:
                                decoder.reset()
                                output.write(s)
                        except UnicodeDecodeError:
                            if ignore_decode_error:
                                decoder.reset()
                                continue
                            else:
                                raise
                else:
                    r = p.poll()
                    if r is not None:
                        _out.seek(0)
                        _err.seek(0)
                        return p, _out, _err
                    sleep(wait)
            except nb_reader.StillRunning:
                pass
            except Exception as e:
                raise e


def deep_getattr(obj, *path, enable_default=False, default=None):
    try:
        current = obj
        for name in path:
            current = getattr(current, name)
        return current
    except AttributeError:
        if enable_default:
            return default
        else:
            raise


def deep_setattr(obj, value, *path):
    o = deep_getattr(obj, *path[:-1])
    # print(path[:-1], path[-1])  # DEBUG ONLY
    setattr(o, path[-1], value)


def walk_obj_iter(obj, path: list = None, skip: set = None, *,
                  ignore_method=True, ignore_magic=True, keepout_types=()):
    path = [] if path is None else path
    skip = set() if skip is None else skip

    def _iter(_obj, _path):
        for name, value in inspect.getmembers(_obj):
            if name == '__dict__':
                continue
            if ignore_method and inspect.ismethod(value):
                continue
            if ignore_magic and name.startswith('__') and name.endswith('__'):
                continue
            _path_ = [*_path, name]
            yield _path_, value
            if isinstance(value, keepout_types):
                continue
            if id(value) in skip:
                continue
            skip.add(id(value))
            yield from _iter(value, _path_)

    root = deep_getattr(obj, *path)
    skip.add(id(root))
    if path:
        yield path, root
    yield from _iter(root, path)


def constrained(x, x_type: T.Callable, x_condition: str or T.Callable = None, *,
                enable_default=False, default=None):
    x = x_type(x)
    if x_condition:
        if isinstance(x_condition, str) and eval(x_condition):
            return x
        elif isinstance(x_condition, T.Callable) and x_condition(x):
            return x
        elif enable_default:
            return default
        else:
            raise ValueError("'{}' conflicts with '{}'".format(x, x_condition))
    else:
        return x


def str2range(expr: str) -> T.Generator:
    sections = [[int(n.strip() or 1) for n in e.split('-')] for e in expr.split(',')]
    for s in sections:
        yield from range(s[0], s[-1] + 1)


def deco_factory_retry(retry_exceptions=None, max_retries: int = 3,
                       enable_default=False, default=None,
                       exception_predicate: T.Callable[[Exception], bool] = None,
                       exception_queue: T.QueueType = None) -> T.Decorator:
    """decorator factory: force a func re-running for several times on exception(s)"""
    retry_exceptions = retry_exceptions or ()
    predicate = exception_predicate or (lambda e: True)
    max_retries = int(max_retries)
    initial_counter = max_retries if max_retries < 0 else max_retries + 1

    def decorator(func):
        @functools.wraps(func)
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


def singleton(cls):
    _instances = {}

    def get_instance(*args, **kwargs):
        if cls not in _instances:
            _instances[cls] = cls(*args, **kwargs)
        return _instances[cls]

    return get_instance


def is_hex(s: str):
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


def deco_with_self_context(target):
    """decorator: wrap a class method inside a `with self: ...` context"""

    def tgt(self, *args, **kwargs):
        with self:
            return target(self, *args, **kwargs)

    return tgt


def deco_factory_with_context(context_obj) -> T.Decorator:
    def deco(target):
        def tgt(*args, **kwargs):
            with context_obj:
                return target(*args, **kwargs)

        return tgt

    return deco


def remove_from_list(source: T.Iterable, rmv_set: T.Iterable) -> list:
    """return a list, which contains elements in source but not in rmv_set"""
    return [x for x in source if x not in rmv_set]


def default_dict_tree():
    return collections.defaultdict(default_dict_tree)


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
        from .fstk import read_json_file
        self.__from_dict__(read_json_file(json_filepath))

    def __to_dict__(self):
        return self.__data__

    def __to_json__(self, json_filepath: str):
        from .fstk import write_json_file
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


def eval_or_str(x: str):
    try:
        return ast.literal_eval(x)
    except (ValueError, SyntaxError):
        return x


class SimpleSQLiteTable:
    def __init__(self, db_path: str, table_name: str, table_columns: list or tuple, *,
                 converters: dict = None, adapters: dict = None):
        logger = logging.ez_get_logger(f'{__name__}.{self.__class__.__name__}')
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


def deco_factory_exit_on_keyboard_interrupt(exit_code,
                                            called_in_except_block: T.Any = VoidDuck,
                                            called_in_finally_block: T.Any = VoidDuck):
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


def hex_hash(data: bytes, algorithm: str = 'md5') -> str:
    return getattr(hashlib, algorithm.replace('-', '_'))(data).hexdigest()


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


def percentage(quotient, decimal_digits: int = 1) -> str:
    fmt = '{:.' + str(decimal_digits) + '%}'
    return fmt.format(quotient)


def width_of_int(x: int):
    return len(str(x))


def iter_factory_retry(max_retries=0,
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

    def iter_retry(callee: T.Callable, *args, **kwargs) -> T.Generator[
        T.Tuple[int, Exception or T.Any], None, None]:
        cnt = max_try
        while cnt:
            try:
                yield cnt, callee(*args, **kwargs)
            except throw_exceptions:
                raise
            except swallow_exceptions as e:
                cnt -= 1
                yield cnt, e

    return iter_retry


def seq_call_return(tasks: T.Iterable[dict], common_exception=Exception):
    """try through a sequence of calling, until sth returned, then stop and return that value.

    Args:
        tasks: a sequence of task, which is a dict
            consisting of a callable ``target`` (required)
            with optional ``args``, ``kwargs``, ``exceptions``:
            {'target': ``target``, 'args': ``args``, 'kwargs': ``kwargs``, 'exceptions': ``exceptions``}
            every task is called like `target(*args, **kwargs)`
        common_exception: Exception(s) for all tasks, could be overrode per tasks.

    during the calling sequence, if the target raises any error, it will be handled in two ways:
        - if the error fit the given exception, it will be ignored
        - else, it will be raised, which will stop the whole sequence
    however, if the whole sequence failed (no return), the last exception will be raised
    """
    e = None
    ok = False
    for task in tasks:
        exception = task.get('exception', common_exception)
        args = task.get('args', ())
        kwargs = task.get('kwargs', {})
        try:
            r = task['target'](*args, **kwargs)
            ok = True
            return r
        except exception as e:
            pass
    if not ok and e:
        raise e


class NonBlockingCaller:
    class StillRunning(ExceptionWithKwargs):
        pass

    class Stopped(Exception):
        pass

    def __init__(self, target: T.Callable, *args, **kwargs):
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
        self._result_queue = queue.Queue(maxsize=1)
        self._exception_queue = queue.Queue(maxsize=1)
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


class ProcessTTYFrozen(TimeoutError):
    pass
