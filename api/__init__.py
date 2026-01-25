# API模块初始化
from .router import APIRouter
from .v1 import APIv1
from .v2 import APIv2

__all__ = ['APIRouter', 'APIv1', 'APIv2']
