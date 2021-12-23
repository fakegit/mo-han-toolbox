#!/usr/bin/env python3
from ezpykit.stdlib import typing as T


def deco_factory_add_method_to_class(cls):
    def deco(func):
        setattr(cls, func.__name__, func)
        return func

    return deco


class SingletonMetaClass(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


def deco_ctx_with_self(target):
    def tgt(self, *args, **kwargs):
        with self:
            return target(self, *args, **kwargs)

    return tgt


def deco_factory_ctx(context_obj) -> T.Decorator:
    def deco(target):
        def tgt(*args, **kwargs):
            with context_obj:
                return target(*args, **kwargs)

        return tgt

    return deco


class AttrName(metaclass=SingletonMetaClass):
    def __setattr__(self, key, value):
        pass

    def __getattr__(self, item: str) -> str:
        self.__dict__[item] = item
        return item