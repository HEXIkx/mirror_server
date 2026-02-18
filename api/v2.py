#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""API v2 版本处理模块 - 增强版本"""

import os
import json
import re
import time
from datetime import datetime

from .v1 import APIv1
from .admin import AdminAPI
from core.utils import format_file_size
from core.api_auth import require_auth, check_endpoint_auth


class APIv2(APIv1):
    """API v2 - 增强版本，继承v1并添加新功能"""

    def __init__(self, config):
        super().__init__(config)
        self.api_version = "v2"
        # 管理员API处理器（始终创建，auth_type检查在装饰器中处理）
        self.admin_api = AdminAPI(config)

    def handle_request(self, handler, method, path, query_params):
        """处理API v2请求"""
        import sys

        # 调试输出 (debug-v2)
        if handler._is_debug_enabled('v2'):
            msg = f"\n=== DEBUG APIv2.handle_request ===\n  path: '{path}'\n  method: '{method}'"
            handler._debug_log('v2', msg, '\033[36m')

        # v2 端点列表（这些是 v2 专有端点，不应该交给 APIv1 处理）
        v2_endpoints = [
            'admin/',
            'search/enhanced',
            'search/by-tag',
            'search/by-date',
            'stats/detailed',
            'stats/trending',
            'stats/download-trend',
            'stats/download-by-period',
            'stats/rank',
            'cache/popular',
            'file/',
            'metadata/',
            'monitor/',
            'health/',
            'health/',
            'alerts',
            'alerts/',
            'webhooks',
            'sync/',
            'cache/',
            'mirrors',
            'pypi',
            'config',
            'server/',
            'health',
            'downloads/',
            'metrics',
            'activity',
            'user/',
        ]

        # 检查是否是 v2 专有端点
        is_v2_endpoint = False
        for ep in v2_endpoints:
            if path == ep or path.startswith(ep):
                is_v2_endpoint = True
                break

        # 如果是 v2 端点，调用 auth_manager 时要跳过 v1 路径
        auth_manager = getattr(handler, 'auth_manager', None)

        # ========== 首先处理 v2 专有端点 ==========
        if is_v2_endpoint:
            # 公开端点列表（无需认证）
            public_endpoints = [
                'admin/auth/verify',
                'user/login',
                'user/password',
                'search/enhanced',
                'search/by-tag',
                'search/by-date'
            ]

            # 检查是否公开端点
            is_public = path in public_endpoints or any(path.startswith(ep + '/') for ep in public_endpoints)

            # 如果auth_type为none，跳过所有认证检查
            auth_type = self.config.get('auth_type', 'none')
            skip_auth = auth_type == 'none'

            # 如果需要认证（不是公开端点且auth_type不是none）
            if auth_manager and not is_public and not skip_auth:
                auth_check = check_endpoint_auth(method, path, auth_manager)
                if auth_check['required']:
                    auth_result = auth_manager.validate_request(handler, 'admin')
                    if not auth_result.get('authenticated'):
                        handler.send_response(401)
                        handler.send_header('WWW-Authenticate', 'Bearer')
                        handler.send_header('Access-Control-Allow-Origin', '*')
                        handler.send_json_response({
                            "error": "认证Required",
                            "code": "UNAUTHORIZED",
                            "required_permission": auth_check['permission']
                        })
                        return

                    if auth_check['permission']:
                        if not auth_manager.check_permission(auth_result, auth_check['permission']):
                            handler.send_header('Access-Control-Allow-Origin', '*')
                            handler.send_json_response({
                                "error": "权限不足",
                                "code": "FORBIDDEN",
                                "required_permission": auth_check['permission']
                            }, 403)
                            return

                    handler.auth_result = auth_result

            # ========== v2 端点处理 ==========
            # 认证验证 API
            if path == 'admin/auth/verify':
                if method == 'POST':
                    self.api_verify_auth(handler)
                else:
                    handler.send_error(405)
                return

            # 管理员统计 API
            if path == 'admin/stats':
                self.admin_api.handle_request(handler, method, 'stats', query_params)
                return

            # v2新增的增强功能
            # 增强搜索API（无需认证）
            if path == 'search/enhanced':
                if method == 'GET':
                    self.api_search_files_enhanced(handler, query_params)
                else:
                    handler.send_error(405)
                return
            elif path == 'search/by-tag':
                if method == 'GET':
                    self.api_search_by_tag(handler, query_params)
                else:
                    handler.send_error(405)
                return
            elif path == 'search/by-date':
                if method == 'GET':
                    self.api_search_by_date(handler, query_params)
                else:
                    handler.send_error(405)
                return

            # 增强统计API
            elif path == 'stats/detailed':
                if method == 'GET':
                    self.api_get_stats_detailed(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'stats/trending':
                if method == 'GET':
                    self.api_get_trending_files(handler, query_params)
                else:
                    handler.send_error(405)
                return

            # 增强文件操作API
            elif path.startswith('file/') and path.endswith('/metadata'):
                filename = path[5:-9]  # 移除 'file/' 和 '/metadata'
                if method == 'GET':
                    self.api_get_file_metadata(handler, filename)
                elif method == 'PUT':
                    self.api_update_file_metadata(handler, filename)
                else:
                    handler.send_error(405)
                return

            # 批量元数据操作
            elif path == 'metadata/batch':
                if method == 'GET':
                    self.api_get_batch_metadata(handler, query_params)
                elif method == 'PUT':
                    self.api_update_batch_metadata(handler)
                else:
                    handler.send_error(405)
                return

            # 文件版本控制
            elif path.startswith('file/') and '/versions' in path:
                parts = path.split('/')
                if len(parts) >= 3 and parts[-1] == 'versions':
                    filename = '/'.join(parts[1:-1])
                    if method == 'GET':
                        self.api_get_file_versions(handler, filename)
                    elif method == 'POST':
                        self.api_create_file_version(handler, filename)
                    else:
                        handler.send_error(405)
                    return

            # 缩略图API
            elif path.startswith('file/') and path.endswith('/thumbnail'):
                filename = path[5:-10]  # 移除 'file/' 和 '/thumbnail'
                if method == 'GET':
                    self.api_get_file_thumbnail(handler, filename, query_params)
                else:
                    handler.send_error(405)
                return

            # 服务器监控（实时数据）
            elif path == 'monitor/realtime':
                if method == 'GET':
                    self.api_get_realtime_stats(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'monitor/history':
                if method == 'GET':
                    self.api_get_monitor_history(handler, query_params)
                else:
                    handler.send_error(405)
                return
            elif path == 'monitor/detailed':
                if method == 'GET':
                    self.api_get_monitor_detailed(handler)
                else:
                    handler.send_error(405)
                return

            # ========== 镜像源健康检查 ==========
            elif path == 'health/sources':
                if method == 'GET':
                    self.api_get_source_health(handler, query_params)
                else:
                    handler.send_error(405)
                return
            elif path.startswith('health/check/'):
                source_name = path[13:]  # 移除 'health/check/'
                if method == 'GET':
                    self.api_check_source(handler, source_name)
                else:
                    handler.send_error(405)
                return
            elif path == 'health/failover':
                if method == 'GET':
                    self.api_get_failover_status(handler)
                else:
                    handler.send_error(405)
                return
            elif path.startswith('health/failover/') and method == 'POST':
                mirror_type = path[18:]  # 移除 'health/failover/'
                self.api_trigger_failover(handler, mirror_type)
                return
            elif path == 'health/stats':
                if method == 'GET':
                    from core.health_check import HealthChecker
                    checker = HealthChecker(self.config.get('health_check', {}))
                    handler.send_json_response(checker.get_stats())
                else:
                    handler.send_error(405)
                return

            # Webhook支持
            elif path == 'webhooks':
                if method == 'GET':
                    self.api_list_webhooks(handler)
                elif method == 'POST':
                    self.api_create_webhook(handler)
                else:
                    handler.send_error(405)
                return
            elif path.startswith('webhooks/'):
                webhook_id = path[9:]

                # 交付历史: webhooks/{id}/deliveries
                if webhook_id.endswith('/deliveries'):
                    actual_id = webhook_id[:-11]
                    if method == 'GET':
                        self.api_get_webhook_deliveries(handler, actual_id)
                    else:
                        handler.send_error(405)
                    return

                # 统计: webhooks/{id}/stats
                if webhook_id.endswith('/stats'):
                    actual_id = webhook_id[:-6]
                    if method == 'GET':
                        self.api_get_webhook_stats(handler, actual_id)
                    else:
                        handler.send_error(405)
                    return

                # 单个 webhook 操作
                if method == 'GET':
                    self.api_get_webhook(handler, webhook_id)
                elif method == 'DELETE':
                    self.api_delete_webhook(handler, webhook_id)
                elif method == 'POST':
                    # 检查是否是测试请求
                    if '/test' in webhook_id:
                        actual_id = webhook_id.split('/')[0]
                        self.api_test_webhook(handler, actual_id)
                    else:
                        self.api_test_webhook(handler, webhook_id)
                elif method == 'PUT':
                    self.api_update_webhook(handler, webhook_id)
                else:
                    handler.send_error(405)
                return

            # ========== 以下端点需要认证 ==========

            # 同步管理API
            elif path == 'sync/sources':
                if method == 'GET':
                    self.api_get_sync_sources(handler)
                elif method == 'POST':
                    self.api_add_sync_source(handler)
                else:
                    handler.send_error(405)
                return
            elif path.startswith('sync/') and path.endswith('/start'):
                source_name = path[5:-6]
                if method == 'POST':
                    self.api_start_sync(handler, source_name)
                else:
                    handler.send_error(405)
                return
            elif path.startswith('sync/') and path.endswith('/stop'):
                source_name = path[5:-5]
                if method == 'POST':
                    self.api_stop_sync(handler, source_name)
                else:
                    handler.send_error(405)
                return
            elif path.startswith('sync/') and path.endswith('/status'):
                source_name = path[5:-7]
                if method == 'GET':
                    self.api_get_sync_status(handler, source_name)
                else:
                    handler.send_error(405)
                return
            elif path == 'sync/history':
                if method == 'GET':
                    self.api_get_sync_history(handler, query_params)
                else:
                    handler.send_error(405)
                return
            elif path == 'sync/packages':
                if method == 'POST':
                    self.api_sync_packages(handler)
                else:
                    handler.send_error(405)
                return
            elif path.startswith('sync/packages/') and path.endswith('/status'):
                source_name = path[14:-8]
                if method == 'GET':
                    self.api_get_temp_sync_status(handler, source_name)
                else:
                    handler.send_error(405)
                return

            # 缓存管理API
            elif path == 'cache/stats':
                if method == 'GET':
                    self.api_get_cache_stats(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'cache/clean' and method == 'POST':
                self.api_clean_cache(handler)
                return
            elif path == 'cache/usage':
                if method == 'GET':
                    self.api_get_cache_usage(handler)
                else:
                    handler.send_error(405)
                return

            # 镜像加速源API
            elif path == 'mirrors':
                if method == 'GET':
                    self.api_list_mirrors(handler)
                else:
                    handler.send_error(405)
                return

            # 镜像管理 API - 必须放在特殊镜像处理之前
            # mirrors/xxx/enable, mirrors/xxx/refresh, mirrors/xxx (PUT/DELETE)
            elif path.endswith('/enable'):
                # 格式: mirrors/xxx/enable
                parts = path.split('/')
                if len(parts) >= 3:
                    mirror_name = parts[1]
                    if method == 'PUT':
                        self.api_enable_mirror(handler, mirror_name, query_params)
                    else:
                        handler.send_error(405)
                    return
            elif path.endswith('/refresh'):
                # 格式: mirrors/xxx/refresh
                parts = path.split('/')
                if len(parts) >= 3:
                    mirror_name = parts[1]
                    if method == 'POST':
                        self.api_refresh_mirror(handler, mirror_name)
                    else:
                        handler.send_error(405)
                    return

            # 加速源访问 API - mirrors/pypi/*, mirrors/npm/*, mirrors/go/* 等
            # 注意：排除 mirrors/pypi/enable, mirrors/pypi/refresh 等管理路径
            elif (path.startswith('mirrors/pypi/') and not '/enable' in path and not '/refresh' in path) or path == 'mirrors/pypi':
                # PyPI 加速源 - 优先本地，没有再从上游拉取
                from mirrors import get_mirror_handler
                mirror_path = path.replace('mirrors/pypi/', '', 1)
                if path == 'mirrors/pypi':
                    mirror_path = 'pypi'
                handler_class = get_mirror_handler('pypi')
                if handler_class:
                    # 创建实例
                    mirror_config = self.config.get('mirrors', {}).get('pypi', {})
                    base_dir = self.config.get('base_dir', './downloads')
                    storage_subdir = mirror_config.get('storage_dir', 'pypi')
                    # 配置: base_dir=downloads目录, storage_dir=pypi子目录
                    mirror_handler = handler_class({
                        'base_dir': base_dir,
                        'storage_dir': storage_subdir,
                        'upstream_url': mirror_config.get('url', 'https://pypi.org')
                    })
                    mirror_handler.handle_request(handler, mirror_path)
                else:
                    handler.send_error(404, "PyPI mirror not configured")
                return
            elif path.startswith('mirrors/npm/') or path == 'mirrors/npm':
                # NPM 加速源 - 优先本地，没有再从上游拉取
                from mirrors import get_mirror_handler
                mirror_path = path.replace('mirrors/npm/', '', 1)
                if path == 'mirrors/npm':
                    mirror_path = 'npm'
                handler_class = get_mirror_handler('npm')
                if handler_class:
                    mirror_config = self.config.get('mirrors', {}).get('npm', {})
                    base_dir = self.config.get('base_dir', './downloads')
                    storage_subdir = mirror_config.get('storage_dir', 'npm')
                    mirror_handler = handler_class({
                        'base_dir': base_dir,
                        'storage_dir': storage_subdir,
                        'upstream_url': mirror_config.get('url', 'https://registry.npmjs.org')
                    })
                    mirror_handler.handle_request(handler, mirror_path)
                else:
                    handler.send_error(404, "NPM mirror not configured")
                return
            elif path.startswith('mirrors/go/') or path == 'mirrors/go':
                # Go 加速源 - 优先本地，没有再从上游拉取
                from mirrors import get_mirror_handler
                mirror_path = path.replace('mirrors/go/', '', 1)
                if path == 'mirrors/go':
                    mirror_path = 'go'
                handler_class = get_mirror_handler('go')
                if handler_class:
                    mirror_config = self.config.get('mirrors', {}).get('go', {})
                    base_dir = self.config.get('base_dir', './downloads')
                    storage_subdir = mirror_config.get('storage_dir', 'go')
                    mirror_handler = handler_class({
                        'base_dir': base_dir,
                        'storage_dir': storage_subdir,
                        'upstream_url': mirror_config.get('url', 'https://goproxy.cn')
                    })
                    mirror_handler.handle_request(handler, mirror_path)
                else:
                    handler.send_error(404, "Go mirror not configured")
                return
            elif path.startswith('mirrors/docker/') or path == 'mirrors/docker':
                # Docker 加速源 - 优先本地，没有再从上游拉取
                from mirrors import get_mirror_handler
                mirror_path = path.replace('mirrors/docker/', '', 1)
                if path == 'mirrors/docker':
                    mirror_path = 'docker'
                handler_class = get_mirror_handler('docker')
                if handler_class:
                    mirror_config = self.config.get('mirrors', {}).get('docker', {})
                    base_dir = self.config.get('base_dir', './downloads')
                    storage_subdir = mirror_config.get('storage_dir', 'docker')
                    mirror_handler = handler_class({
                        'base_dir': base_dir,
                        'storage_dir': storage_subdir,
                        'upstream_url': mirror_config.get('url', 'https://registry.hub.docker.com')
                    })
                    mirror_handler.handle_request(handler, mirror_path)
                else:
                    handler.send_error(404, "Docker mirror not configured")
                return

            # PyPI包路径处理 - 处理 /pypi/packages/... 和 /pypi/web/... 路径
            # 这些路径来自镜像返回的HTML中的绝对链接
            elif path.startswith('pypi/packages/') or path.startswith('pypi/web/') or path.startswith('pypi/simple/'):
                import re
                import sys
                from mirrors import PyPIMirror
                # 从Referer中提取镜像名称
                referer = handler.headers.get('Referer', '')
                mirror_name = None
                if 'mirrors/' in referer:
                    match = re.search(r'mirrors/([^/]+)', referer)
                    if match:
                        mirror_name = match.group(1)

                # 优先使用Referer中指定的镜像，否则查找任意可用的pypi类型镜像
                mirrors_config = self.config.get('mirrors', {})
                if mirror_name and mirror_name in mirrors_config:
                    pypi_config = mirrors_config[mirror_name]
                else:
                    # 尝试查找任意pypi类型的镜像（按优先级：pypi-cn, pypi）
                    pypi_config = None
                    for pref_name in ['pypi-cn', 'pypi']:
                        if pref_name in mirrors_config and mirrors_config[pref_name].get('type') == 'pypi':
                            pypi_config = mirrors_config[pref_name]
                            break
                    if not pypi_config:
                        # 尝试查找任意pypi类型的镜像
                        for name, cfg in mirrors_config.items():
                            if cfg.get('type') == 'pypi':
                                pypi_config = cfg
                                break
                base_dir = self.config.get('base_dir', './downloads')
                storage_subdir = pypi_config.get('storage_dir', 'pypi') if pypi_config else 'pypi'
                pypi_handler = PyPIMirror({
                    'base_dir': base_dir,
                    'storage_dir': storage_subdir,
                    'upstream_url': pypi_config.get('url', 'https://pypi.org') if pypi_config else 'https://pypi.org'
                })
                pypi_handler.handle_request(handler, path)
                return

            # 通用镜像处理 - 支持自定义镜像名称如 pypi-cn, npm-cn 等
            elif path.startswith('mirrors/') and method == 'PUT':
                # 更新自定义加速源
                mirror_name = path[8:]
                self.api_update_mirror(handler, mirror_name)
                return
            elif path.startswith('mirrors/') and method == 'DELETE':
                # 删除自定义加速源
                mirror_name = path[8:]
                self.api_delete_mirror(handler, mirror_name)
                return
            elif path == 'mirrors' and method == 'POST':
                # 添加自定义加速源
                self.api_add_mirror(handler)
                return

            # 通用镜像处理 - 支持自定义镜像名称如 pypi-cn, npm-cn 等
            elif path.startswith('mirrors/'):

                from mirrors import HttpMirror, get_mirror_handler, get_default_upstream
                # 解析镜像名称和路径
                # 格式: mirrors/{mirror_name}/... 或 mirrors/{mirror_name}
                # 例如: mirrors/pypi-cn/simple/setuptools -> mirror_name=pypi-cn, mirror_path=simple/setuptools
                parts = path[8:].split('/', 1)
                mirror_name = parts[0]
                # 去掉 mirror_name 前缀，只保留后面的路径
                if len(parts) > 1:
                    full_path = parts[1]
                    # 去掉路径开头的 mirror_name（如 pypi-cn/）
                    if full_path.startswith(mirror_name + '/'):
                        mirror_path = full_path[len(mirror_name)+1:]
                    else:
                        mirror_path = full_path
                else:
                    mirror_path = mirror_name

                # 获取镜像配置
                mirror_config = self.config.get('mirrors', {}).get(mirror_name, {})

                if not mirror_config:
                    handler.send_error(404, f"Mirror '{mirror_name}' not configured")
                    return

                # 获取镜像类型
                mirror_type = mirror_config.get('type', 'http')

                # 调试
                debug_file = '/tmp/pypi_debug.log'
                with open(debug_file, 'a') as f:
                    f.write(f"[V2] mirror_type={mirror_type}, handler_class={get_mirror_handler(mirror_type)}\n")

                # 获取处理器类
                handler_class = get_mirror_handler(mirror_type)
                if not handler_class:
                    handler_class = HttpMirror

                # 创建处理器实例
                base_dir = self.config.get('base_dir', './downloads')
                storage_subdir = mirror_config.get('storage_dir', mirror_name)
                # 拼接完整存储路径
                storage_dir = os.path.join(base_dir, storage_subdir)

                # 根据镜像类型确定上游URL
                default_upstream = 'https://pypi.org/simple'
                if mirror_type in ('pypi', 'pip', 'pipenv', 'poetry'):
                    default_upstream = 'https://pypi.org/simple'
                elif mirror_type == 'npm':
                    default_upstream = 'https://registry.npmjs.org'
                elif mirror_type == 'go':
                    default_upstream = 'https://goproxy.cn'
                elif mirror_type == 'docker':
                    default_upstream = 'https://registry.hub.docker.com'
                else:
                    default_upstream = get_default_upstream(mirror_type)

                mirror_handler = handler_class({
                    'base_dir': base_dir,
                    'storage_dir': storage_dir,
                    'upstream_url': mirror_config.get('url', default_upstream),
                    'type': mirror_type,
                    'cache_enabled': mirror_config.get('cache_enabled', True),
                    'cache_ttl': mirror_config.get('cache_ttl', 3600)
                })
                mirror_handler.handle_request(handler, mirror_path)
                return

            # 用户管理
            elif path == 'user/login':
                if method == 'POST':
                    self.api_login(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'user/password':
                if method == 'POST':
                    self.api_change_password(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'user/login-logs':
                if method == 'GET':
                    self.api_get_login_logs(handler, query_params)
                else:
                    handler.send_error(405)
                return

            # 配置文件管理
            elif path == 'config':
                if method == 'GET':
                    self.api_get_config(handler)
                elif method == 'PUT':
                    self.api_save_config(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'config/reload':
                if method == 'POST':
                    self.api_reload_config(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'config/changes':
                if method == 'GET':
                    self.api_get_config_changes(handler)
                else:
                    handler.send_error(405)
                return

            # 告警管理
            elif path == 'alerts':
                if method == 'GET':
                    self.api_get_alerts(handler, query_params)
                else:
                    handler.send_error(405)
                return
            elif path.startswith('alerts/') and '/acknowledge' in path:
                alert_id = path[7:].split('/')[0]
                if method == 'POST':
                    self.api_acknowledge_alert(handler, alert_id)
                else:
                    handler.send_error(405)
                return
            elif path == 'alerts/clear':
                if method == 'POST':
                    self.api_clear_alerts(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'alerts/test':
                if method == 'POST':
                    self.api_test_alert(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'alerts/config':
                if method == 'GET':
                    self.api_get_alert_config(handler)
                elif method == 'PUT':
                    self.api_save_alert_config(handler)
                else:
                    handler.send_error(405)
                return

            # Prometheus 指标
            elif path == 'metrics':
                if method == 'GET':
                    self.api_get_metrics(handler)
                else:
                    handler.send_error(405)
                return

            # 下载趋势
            elif path == 'stats/download-trend':
                if method == 'GET':
                    self.api_get_download_trend(handler, query_params)
                else:
                    handler.send_error(405)
                return

            # 按周期下载统计
            elif path == 'stats/download-by-period':
                if method == 'GET':
                    self.api_get_download_by_period(handler, query_params)
                else:
                    handler.send_error(405)
                return

            # 下载排行
            elif path == 'stats/rank':
                if method == 'GET':
                    self.api_get_download_rank(handler, query_params)
                else:
                    handler.send_error(405)
                return

            # 热门缓存
            elif path == 'cache/popular':
                if method == 'GET':
                    self.api_get_hot_cache(handler, query_params)
                else:
                    handler.send_error(405)
                return

            # 最近活动
            elif path == 'activity':
                if method == 'GET':
                    self.api_get_recent_activity(handler, query_params)
                else:
                    handler.send_error(405)
                return

            # 服务器重启管理
            elif path == 'server/restart':
                if method == 'GET':
                    self.api_get_restart_status(handler)
                elif method == 'POST':
                    self.api_graceful_restart(handler, query_params)
                else:
                    handler.send_error(405)
                return
            elif path == 'server/restart/confirm':
                if method == 'POST':
                    self.api_confirm_restart(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'server/restart/immediate':
                if method == 'POST':
                    self.api_immediate_restart(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'server/restart/pending':
                if method == 'GET':
                    self.api_get_pending_requests(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'server/restart/history':
                if method == 'GET':
                    self.api_get_restart_history(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'server/restart/config':
                if method == 'GET':
                    self.api_get_restart_config(handler)
                elif method == 'PUT':
                    self.api_update_restart_config(handler)
                else:
                    handler.send_error(405)
                return

            # 缓存预热管理
            elif path == 'cache/prewarm':
                if method == 'GET':
                    self.api_get_prewarm_status(handler)
                elif method == 'POST':
                    self.api_run_prewarm(handler, query_params)
                else:
                    handler.send_error(405)
                return
            elif path == 'cache/prewarm/stats':
                if method == 'GET':
                    self.api_get_prewarm_stats(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'cache/prewarm/items':
                if method == 'GET':
                    self.api_get_prewarm_items(handler, query_params)
                elif method == 'POST':
                    self.api_add_prewarm_items(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'cache/prewarm/history':
                if method == 'GET':
                    self.api_get_prewarm_history(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'cache/prewarm/clear':
                if method == 'POST':
                    self.api_clear_prewarm_queue(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'cache/prewarm/popular':
                if method == 'GET':
                    self.api_get_popular_items(handler, query_params)
                elif method == 'POST':
                    self.api_add_popular_items(handler, query_params)
                else:
                    handler.send_error(405)
                return
            elif path == 'cache/prewarm/config':
                if method == 'GET':
                    self.api_get_prewarm_config(handler)
                elif method == 'PUT':
                    self.api_save_prewarm_config(handler)
                else:
                    handler.send_error(405)
                return

            # API 文档
            elif path == 'api-docs.json':
                if method == 'GET':
                    self.api_get_api_docs(handler)
                else:
                    handler.send_error(405)
                return
            elif path == 'api-docs.yaml':
                if method == 'GET':
                    self.api_get_api_docs(handler, format='yaml')
                else:
                    handler.send_error(405)
                return
            elif path == 'api-docs/generate':
                if method == 'POST':
                    self.api_generate_api_docs(handler)
                else:
                    handler.send_error(405)
                return

            # 服务器信息
            elif path == 'server/info':
                if method == 'GET':
                    self.api_get_server_info(handler)
                else:
                    handler.send_error(405)
                return

        # v2 端点都没匹配到，尝试调用 APIv1
        try:
            return super().handle_request(handler, method, path, query_params)
        except:
            pass

        # 404 - 未找到端点
        handler.send_error(404)
    
    # ==================== 认证 API ====================

    def api_verify_auth(self, handler):
        """验证认证状态"""
        # 调试模式输出 (debug-v2)
        if handler._is_debug_enabled('v2'):
            auth_header = handler.headers.get('Authorization', '')
            api_key = handler.headers.get('X-API-Key', '')
            auth_header_display = auth_header[:30] + '...' if len(auth_header) > 30 else auth_header
            api_key_display = api_key[:20] + '...' if len(api_key) > 20 else api_key
            msg = f"\n=== DEBUG api_verify_auth ===\n  auth_header: '{auth_header_display}'\n  api_key: '{api_key_display}'\n  auth_type: {self.config.get('auth_type', 'none')}"
            handler._debug_log('v2', msg, '\033[32m')

        auth_manager = getattr(handler, 'auth_manager', None)

        # 从请求头获取认证信息
        auth_header = handler.headers.get('Authorization', '')
        api_key = handler.headers.get('X-API-Key', '')
        cookie = handler.headers.get('Cookie', '')

        # 验证 Basic Auth (用户名:密码)
        if auth_header.startswith('Basic '):
            try:
                import base64
                encoded = auth_header[6:]
                decoded = base64.b64decode(encoded).decode('utf-8')
                if ':' in decoded:
                    username, password = decoded.split(':', 1)
                    auth_user = self.config.get('auth_user', '')
                    auth_pass = self.config.get('auth_pass', '')
                    if username == auth_user and password == auth_pass:
                        handler.send_json_response({
                            "valid": True,
                            "level": "admin",
                            "user_id": username,
                            "permissions": ["admin:*", "files:*", "sync:*", "keys:*"],
                            "expires_at": None
                        })
                        return
            except Exception:
                pass

        # 验证 Bearer Token 或 API Key
        token = auth_header[7:] if auth_header.startswith('Bearer ') else api_key

        if token:
            # 尝试从密钥文件验证
            keys_file = 'api_keys.json'
            if os.path.exists(keys_file):
                try:
                    with open(keys_file, 'r') as f:
                        keys_data = json.load(f)
                        for key_id, key_info in keys_data.items():
                            if key_info.get('key', '').startswith(token) and key_info.get('enabled', True):
                                handler.send_json_response({
                                    "valid": True,
                                    "level": key_info.get('level', 'user'),
                                    "user_id": key_id,
                                    "permissions": key_info.get('permissions', []),
                                    "expires_at": key_info.get('expires_at')
                                })
                                return
                except Exception:
                    pass

        # 验证配置文件中的 token
        config_token = self.config.get('auth_token', '')
        if token and token == config_token:
            handler.send_json_response({
                "valid": True,
                "level": "admin",
                "user_id": "config",
                "permissions": ["admin:*", "files:*", "sync:*", "keys:*"],
                "expires_at": None
            })
            return

        # 如果 auth_type 为 none，则允许访问
        if self.config.get('auth_type', 'none') == 'none':
            handler.send_json_response({
                "valid": True,
                "level": "admin",
                "user_id": "anonymous",
                "permissions": ["admin:*", "files:*", "sync:*", "keys:*"],
                "expires_at": None,
                "message": "Auth disabled - full access"
            })
            return

        # 无效认证
        handler.send_json_response({
            "valid": False,
            "error": "Invalid or expired credentials"
        }, 401)

    # ==================== 增强搜索API ====================

    def api_search_files_enhanced(self, handler, query_params):
        """增强的文件搜索 - 支持更多选项"""
        search_term = query_params.get('q', [''])[0].lower()
        search_type = query_params.get('type', ['all'])[0]
        search_mode = query_params.get('mode', ['fuzzy'])[0]  # fuzzy, exact, regex
        max_results = int(query_params.get('limit', ['100'])[0])
        offset = int(query_params.get('offset', ['0'])[0])
        include_content = query_params.get('include_content', ['false'])[0].lower() == 'true'
        
        if not search_term:
            handler.send_json_response({"error": "No search term provided"}, 400)
            return
        
        results = []
        search_time = 0
        import time as time_module
        start_time = time_module.time()
        
        for root, dirs, files in os.walk(self.config['base_dir']):
            if search_type in ['all', 'dir']:
                for dir_name in dirs:
                    match = False
                    if search_mode == 'exact':
                        match = search_term == dir_name.lower()
                    elif search_mode == 'regex':
                        try:
                            match = re.search(search_term, dir_name.lower()) is not None
                        except re.error:
                            match = False
                    else:  # fuzzy
                        match = search_term in dir_name.lower()
                    
                    if match:
                        full_path = os.path.join(root, dir_name)
                        rel_path = os.path.relpath(full_path, self.config['base_dir']).replace("\\", "/")
                        try:
                            mtime = os.path.getmtime(full_path)
                            result = {
                                "name": dir_name,
                                "path": rel_path + "/",
                                "type": "directory",
                                "size": 0,
                                "modified": datetime.fromtimestamp(mtime).isoformat(),
                                "match_score": self._calculate_match_score(dir_name, search_term, search_mode)
                            }
                            if include_content:
                                result['item_count'] = len(os.listdir(full_path))
                            results.append(result)
                        except OSError:
                            continue
            
            if search_type in ['all', 'file']:
                for file_name in files:
                    match = False
                    if search_mode == 'exact':
                        match = search_term == file_name.lower()
                    elif search_mode == 'regex':
                        try:
                            match = re.search(search_term, file_name.lower()) is not None
                        except re.error:
                            match = False
                    else:  # fuzzy
                        match = search_term in file_name.lower()
                    
                    if match:
                        full_path = os.path.join(root, file_name)
                        rel_path = os.path.relpath(full_path, self.config['base_dir']).replace("\\", "/")
                        try:
                            size = os.path.getsize(full_path)
                            mtime = os.path.getmtime(full_path)
                            mime_type, _ = os.path.splitext(file_name)
                            mime_type = mime_type[1:].lower() if mime_type else 'unknown'
                            
                            result = {
                                "name": file_name,
                                "path": rel_path,
                                "type": mime_type,
                                "size": size,
                                "size_formatted": self.format_file_size(size),
                                "modified": datetime.fromtimestamp(mtime).isoformat(),
                                "match_score": self._calculate_match_score(file_name, search_term, search_mode)
                            }
                            
                            if include_content:
                                if mime_type in ['txt', 'log', 'md', 'json', 'xml', 'html']:
                                    try:
                                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                                            content = f.read(5000)
                                            result['content_preview'] = content
                                    except:
                                        pass
                            
                            results.append(result)
                        except OSError:
                            continue
            
            if len(results) >= max_results + offset:
                break
        
        search_time = time_module.time() - start_time
        
        # 按匹配分数排序
        results.sort(key=lambda x: x.get('match_score', 0), reverse=True)
        
        paginated_results = results[offset:offset + max_results]
        
        handler.send_json_response({
            "query": search_term,
            "search_type": search_type,
            "search_mode": search_mode,
            "total_count": len(results),
            "returned_count": len(paginated_results),
            "offset": offset,
            "limit": max_results,
            "search_time": round(search_time, 3),
            "results": paginated_results
        })
    
    def api_search_by_tag(self, handler, query_params):
        """按标签搜索文件"""
        tag = query_params.get('tag', [''])[0]
        if not tag:
            handler.send_json_response({"error": "No tag specified"}, 400)
            return
        
        # 这里假设有一个标签存储系统
        # 实际实现需要维护文件标签数据库
        results = []
        handler.send_json_response({
            "tag": tag,
            "total_count": 0,
            "results": results
        })
    
    def api_search_by_date(self, handler, query_params):
        """按日期范围搜索文件"""
        start_date = query_params.get('start', [''])[0]
        end_date = query_params.get('end', [''])[0]
        search_type = query_params.get('type', ['all'])[0]
        
        if not start_date:
            handler.send_json_response({"error": "Start date required"}, 400)
            return
        
        try:
            start_dt = datetime.fromisoformat(start_date)
            end_dt = datetime.fromisoformat(end_date) if end_date else datetime.now()
        except ValueError:
            handler.send_json_response({"error": "Invalid date format"}, 400)
            return
        
        results = []
        
        for root, dirs, files in os.walk(self.config['base_dir']):
            if search_type in ['all', 'dir']:
                for dir_name in dirs:
                    full_path = os.path.join(root, dir_name)
                    try:
                        mtime = datetime.fromtimestamp(os.path.getmtime(full_path))
                        if start_dt <= mtime <= end_dt:
                            rel_path = os.path.relpath(full_path, self.config['base_dir']).replace("\\", "/")
                            results.append({
                                "name": dir_name,
                                "path": rel_path + "/",
                                "type": "directory",
                                "modified": mtime.isoformat()
                            })
                    except OSError:
                        continue
            
            if search_type in ['all', 'file']:
                for file_name in files:
                    full_path = os.path.join(root, file_name)
                    try:
                        mtime = datetime.fromtimestamp(os.path.getmtime(full_path))
                        if start_dt <= mtime <= end_dt:
                            rel_path = os.path.relpath(full_path, self.config['base_dir']).replace("\\", "/")
                            results.append({
                                "name": file_name,
                                "path": rel_path,
                                "type": "file",
                                "modified": mtime.isoformat()
                            })
                    except OSError:
                        continue
            
            if len(results) > 1000:
                break
        
        handler.send_json_response({
            "start_date": start_date,
            "end_date": end_date.isoformat(),
            "total_count": len(results),
            "results": results
        })
    
    def _calculate_match_score(self, text, search_term, mode):
        """计算匹配分数"""
        if mode == 'exact':
            return 100 if text.lower() == search_term else 0
        elif mode == 'regex':
            try:
                return 80 if re.search(search_term, text.lower()) else 0
            except:
                return 0
        else:  # fuzzy
            text_lower = text.lower()
            if search_term == text_lower:
                return 100
            elif text_lower.startswith(search_term):
                return 90
            elif text_lower.endswith(search_term):
                return 80
            elif search_term in text_lower:
                return 70
            return 0
    
    # ==================== 增强统计API ====================
    
    def api_get_stats_detailed(self, handler):
        """获取详细统计信息"""
        import mimetypes
        
        total_files = 0
        total_dirs = 0
        total_size = 0
        file_types = {}
        size_distribution = {
            "small": 0,      # < 1MB
            "medium": 0,     # 1MB - 100MB
            "large": 0,      # 100MB - 1GB
            "xlarge": 0      # > 1GB
        }
        oldest_file = None
        newest_file = None
        largest_file = None
        
        for root, dirs, files in os.walk(self.config['base_dir']):
            total_dirs += len(dirs)
            total_files += len(files)
            for filename in files:
                try:
                    file_path = os.path.join(root, filename)
                    size = os.path.getsize(file_path)
                    mtime = os.path.getmtime(file_path)
                    total_size += size
                    
                    mime_type, _ = mimetypes.guess_type(file_path)
                    if mime_type is None:
                        mime_type = "application/octet-stream"
                    file_types[mime_type] = file_types.get(mime_type, 0) + 1
                    
                    # 大小分布
                    if size < 1024 * 1024:
                        size_distribution["small"] += 1
                    elif size < 100 * 1024 * 1024:
                        size_distribution["medium"] += 1
                    elif size < 1024 * 1024 * 1024:
                        size_distribution["large"] += 1
                    else:
                        size_distribution["xlarge"] += 1
                    
                    # 最旧/最新文件
                    if oldest_file is None or mtime < oldest_file[1]:
                        oldest_file = (filename, mtime)
                    if newest_file is None or mtime > newest_file[1]:
                        newest_file = (filename, mtime)
                    
                    # 最大文件
                    if largest_file is None or size > largest_file[1]:
                        largest_file = (filename, size)
                        
                except OSError:
                    continue
        
        handler.send_json_response({
            "summary": {
                "total_files": total_files,
                "total_dirs": total_dirs,
                "total_size": total_size,
                "total_size_formatted": self.format_file_size(total_size)
            },
            "file_types": dict(sorted(file_types.items(), key=lambda x: x[1], reverse=True)),
            "size_distribution": size_distribution,
            "extremes": {
                "oldest_file": {
                    "name": oldest_file[0] if oldest_file else None,
                    "modified": datetime.fromtimestamp(oldest_file[1]).isoformat() if oldest_file else None
                },
                "newest_file": {
                    "name": newest_file[0] if newest_file else None,
                    "modified": datetime.fromtimestamp(newest_file[1]).isoformat() if newest_file else None
                },
                "largest_file": {
                    "name": largest_file[0] if largest_file else None,
                    "size": largest_file[1] if largest_file else None,
                    "size_formatted": self.format_file_size(largest_file[1]) if largest_file else None
                }
            },
            "updated": datetime.now().isoformat()
        })
    
    def api_get_trending_files(self, handler, query_params):
        """获取热门文件（按下载次数）"""
        limit = int(query_params.get('limit', ['20'])[0])
        time_range = query_params.get('range', ['24h'])[0]  # 24h, 7d, 30d
        
        # 获取下载统计
        stats = handler.load_stats()
        
        # 转换为列表并排序
        trending = []
        for filepath, count in stats.items():
            full_path = os.path.join(self.config['base_dir'], filepath)
            if os.path.exists(full_path) and os.path.isfile(full_path):
                try:
                    info = os.stat(full_path)
                    trending.append({
                        "path": filepath,
                        "name": os.path.basename(filepath),
                        "size": info.st_size,
                        "size_formatted": self.format_file_size(info.st_size),
                        "modified": datetime.fromtimestamp(info.st_mtime).isoformat(),
                        "downloads": count
                    })
                except OSError:
                    continue
        
        # 按下载次数排序
        trending.sort(key=lambda x: x['downloads'], reverse=True)
        trending = trending[:limit]
        
        handler.send_json_response({
            "time_range": time_range,
            "limit": limit,
            "trending": trending
        })

    def api_get_download_trend(self, handler, query_params):
        """获取下载趋势（按天统计）"""
        days = int(query_params.get('days', [7])[0])
        days = min(max(days, 1), 90)  # 限制 1-90 天

        trend = []

        # 从数据库获取下载记录进行统计
        db = self.get_db()
        if db:
            try:
                from datetime import timedelta
                from core.database import DownloadRecord

                now = datetime.now()
                start_time = (now - timedelta(days=days)).timestamp()

                with db.session() as session:
                    records = session.query(DownloadRecord).filter(
                        DownloadRecord.download_time >= start_time,
                        DownloadRecord.success == True
                    ).all()

                    # 按日期聚合
                    daily_stats = {}
                    for r in records:
                        if r.download_time:
                            date = datetime.fromtimestamp(r.download_time).strftime('%Y-%m-%d')
                            daily_stats[date] = daily_stats.get(date, 0) + 1

                    # 填充所有日期
                    for i in range(days):
                        date = (now - timedelta(days=days - 1 - i)).strftime('%Y-%m-%d')
                        trend.append({
                            "date": date,
                            "downloads": daily_stats.get(date, 0)
                        })
            except Exception as e:
                print(f"Error getting download trend from database: {e}")

        # 如果没有数据库数据，返回模拟数据
        if not trend:
            now = datetime.now()
            for i in range(days):
                date = (now - timedelta(days=days - 1 - i)).strftime('%m-%d')
                trend.append({
                    "date": date,
                    "downloads": 0
                })

        handler.send_json_response({
            "days": days,
            "trend": trend
        })

    def api_get_download_by_period(self, handler, query_params):
        """按周期获取下载统计（年/月/日）"""
        from datetime import datetime, timedelta
        from sqlalchemy import func

        period = query_params.get('period', ['day'])[0]
        year = int(query_params.get('year', [datetime.now().year])[0])
        month = int(query_params.get('month', [datetime.now().month])[0])

        # 限制 period 值
        if period not in ['year', 'month', 'day']:
            period = 'day'

        result = {
            "period": period,
            "year": year,
            "month": month,
            "data": []
        }

        db = self.get_db()
        if db:
            try:
                from core.database import DownloadRecord
                now = datetime.now()

                with db.session() as session:
                    if period == 'year':
                        # 按月统计全年数据
                        start_time = datetime(year, 1, 1).timestamp()
                        end_time = datetime(year + 1, 1, 1).timestamp()

                        records = session.query(DownloadRecord).filter(
                            DownloadRecord.download_time >= start_time,
                            DownloadRecord.download_time < end_time,
                            DownloadRecord.success == True
                        ).all()

                        monthly_stats = {m: 0 for m in range(1, 13)}
                        total = 0
                        for r in records:
                            if r.download_time:
                                dt = datetime.fromtimestamp(r.download_time)
                                monthly_stats[dt.month] += 1
                                total += 1

                        result["data"] = [
                            {"label": f"{m}月", "value": monthly_stats[m], "month": m}
                            for m in range(1, 13)
                        ]
                        result["total"] = total

                    elif period == 'month':
                        # 按日统计当月数据
                        start_time = datetime(year, month, 1).timestamp()
                        if month == 12:
                            end_time = datetime(year + 1, 1, 1).timestamp()
                        else:
                            end_time = datetime(year, month + 1, 1).timestamp()

                        records = session.query(DownloadRecord).filter(
                            DownloadRecord.download_time >= start_time,
                            DownloadRecord.download_time < end_time,
                            DownloadRecord.success == True
                        ).all()

                        days_in_month = (datetime(year, month + 1, 1) - timedelta(days=1)).day if month < 12 else 31
                        daily_stats = {d: 0 for d in range(1, days_in_month + 1)}
                        total = 0
                        for r in records:
                            if r.download_time:
                                dt = datetime.fromtimestamp(r.download_time)
                                daily_stats[dt.day] += 1
                                total += 1

                        result["data"] = [
                            {"label": f"{d}日", "value": daily_stats[d], "day": d}
                            for d in range(1, days_in_month + 1)
                        ]
                        result["total"] = total

                    else:  # day - 按日统计当月数据
                        # 获取当月第一天和最后一天
                        if month == 12:
                            start_date = datetime(year, month, 1)
                            end_date = datetime(year + 1, 1, 1)
                        else:
                            start_date = datetime(year, month, 1)
                            end_date = datetime(year, month + 1, 1)

                        start_time = start_date.timestamp()
                        end_time = end_date.timestamp()

                        records = session.query(DownloadRecord).filter(
                            DownloadRecord.download_time >= start_time,
                            DownloadRecord.download_time < end_time,
                            DownloadRecord.success == True
                        ).all()

                        # 按天统计
                        days_in_month = (end_date - timedelta(days=1)).day
                        daily_stats = {d: 0 for d in range(1, days_in_month + 1)}
                        total = 0
                        for r in records:
                            if r.download_time:
                                dt = datetime.fromtimestamp(r.download_time)
                                daily_stats[dt.day] += 1
                                total += 1

                        result["data"] = [
                            {"label": f"{d}日", "value": daily_stats[d], "day": d}
                            for d in range(1, days_in_month + 1)
                        ]
                        result["total"] = total

                # 获取历史年份列表
                if period == 'year':
                    with db.session() as session:
                        # SQLite 不支持 from_unixtime，使用 Python 处理
                        records = session.query(DownloadRecord.download_time).filter(
                            DownloadRecord.success == True
                        ).distinct().all()
                        years_set = set()
                        for (ts,) in records:
                            if ts:
                                dt = datetime.fromtimestamp(ts)
                                years_set.add(dt.year)
                        result["available_years"] = sorted(list(years_set), reverse=True)[:10]

            except Exception as e:
                print(f"Error getting download by period: {e}")
                result["error"] = str(e)

        # 如果没有数据，返回空数据结构
        if not result.get("data"):
            if period == 'year':
                result["data"] = [{"label": f"{m}月", "value": 0, "month": m} for m in range(1, 13)]
            elif period == 'month':
                result["data"] = [{"label": f"{d}日", "value": 0, "day": d} for d in range(1, 32)]
            else:
                result["data"] = [{"label": f"{h}:00", "value": 0, "hour": h} for h in range(24)]

        handler.send_json_response(result)

    def api_get_download_rank(self, handler, query_params):
        """获取下载排行 TOP 20"""
        import traceback
        import os
        limit = int(query_params.get('limit', [20])[0])
        limit = min(max(limit, 1), 100)

        rank_data = []
        errors = []

        # 从数据库获取下载记录进行统计
        db = self.get_db()
        if db:
            try:
                from core.database import DownloadRecord

                with db.session() as session:
                    # 按文件路径分组统计下载次数
                    from sqlalchemy import func
                    results = session.query(
                        DownloadRecord.file_path,
                        func.count(DownloadRecord.id).label('download_count')
                    ).filter(
                        DownloadRecord.success == True
                    ).group_by(
                        DownloadRecord.file_path
                    ).order_by(
                        func.count(DownloadRecord.id).desc()
                    ).limit(limit).all()

                    total_downloads = sum(r[1] for r in results) if results else 0

                    # 获取 base_dir
                    base_dir = self.config.get('base_dir', './downloads')
                    base_dir = os.path.abspath(base_dir) if base_dir else './downloads'

                    for idx, (file_path, count) in enumerate(results, 1):
                        # 获取文件大小
                        file_size = 0
                        full_path = os.path.join(base_dir, file_path) if file_path else ''
                        if full_path and os.path.exists(full_path):
                            try:
                                file_size = os.path.getsize(full_path)
                            except OSError:
                                pass

                        # 计算占比
                        percentage = (count / total_downloads * 100) if total_downloads > 0 else 0

                        rank_data.append({
                            "rank": idx,
                            "file": file_path or 'Unknown',
                            "downloads": count,
                            "size": file_size,
                            "percentage": round(percentage, 1)
                        })
            except Exception as e:
                errors.append(str(e))
                traceback.print_exc()

        handler.send_json_response({
            "rank": rank_data,
            "count": len(rank_data),
            "total_records": len(rank_data),
            "_debug": {"errors": errors} if errors else {}
        })

    def api_get_hot_cache(self, handler, query_params):
        """获取热门缓存文件"""
        import traceback
        import os
        limit = int(query_params.get('limit', [20])[0])
        limit = min(max(limit, 1), 100)

        cache_data = []
        errors = []

        # 从数据库获取缓存访问记录
        db = self.get_db()
        if db:
            try:
                from core.database import DownloadRecord

                with db.session() as session:
                    from sqlalchemy import func
                    # 获取被访问过的缓存文件（按访问次数排序）
                    results = session.query(
                        DownloadRecord.file_path,
                        func.count(DownloadRecord.id).label('access_count'),
                        func.max(DownloadRecord.download_time).label('last_access')
                    ).filter(
                        DownloadRecord.success == True
                    ).group_by(
                        DownloadRecord.file_path
                    ).order_by(
                        func.count(DownloadRecord.id).desc()
                    ).limit(limit).all()

                    # 获取 base_dir
                    base_dir = self.config.get('base_dir', './downloads')
                    base_dir = os.path.abspath(base_dir) if base_dir else './downloads'

                    for idx, (file_path, access_count, last_access) in enumerate(results, 1):
                        # 获取文件信息
                        full_path = os.path.join(base_dir, file_path) if file_path else ''
                        file_size = 0
                        if full_path and os.path.exists(full_path):
                            try:
                                file_size = os.path.getsize(full_path)
                            except OSError:
                                pass

                        cache_data.append({
                            "rank": idx,
                            "file": file_path or 'Unknown',
                            "access_count": access_count,
                            "size": file_size,
                            "last_access": datetime.fromtimestamp(last_access).isoformat() if last_access else '-'
                        })
            except Exception as e:
                errors.append(str(e))
                traceback.print_exc()

        handler.send_json_response({
            "cache": cache_data,
            "count": len(cache_data),
            "_debug": {"errors": errors} if errors else {}
        })

    def get_db(self):
        """获取数据库实例"""
        from core.database import get_db
        try:
            return get_db()
        except Exception:
            return None

    # ==================== 文件元数据API ====================
    
    def api_get_file_metadata(self, handler, filename):
        """获取文件元数据"""
        full_path = os.path.join(self.config['base_dir'], filename)
        if not os.path.exists(full_path):
            handler.send_json_response({"error": "File not found"}, 404)
            return
        
        # 这里可以从单独的元数据文件中读取
        metadata_file = full_path + '.meta'
        metadata = {}
        
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except:
                pass
        
        # 添加基本文件信息
        import os
        stat = os.stat(full_path)
        metadata['_file_info'] = {
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat()
        }
        
        handler.send_json_response(metadata)
    
    def api_update_file_metadata(self, handler, filename):
        """更新文件元数据"""
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            handler.send_json_response({"error": "No metadata provided"}, 400)
            return
        
        try:
            metadata = json.loads(handler.rfile.read(content_length))
            full_path = os.path.join(self.config['base_dir'], filename)
            metadata_file = full_path + '.meta'
            
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            handler.send_json_response({"success": True})
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)
    
    def api_get_batch_metadata(self, handler, query_params):
        """批量获取文件元数据"""
        paths = query_params.get('paths', [])
        if not paths:
            handler.send_json_response({"error": "No file paths provided"}, 400)
            return
        
        results = {}
        for path in paths:
            full_path = os.path.join(self.config['base_dir'], path)
            if os.path.exists(full_path):
                metadata_file = full_path + '.meta'
                metadata = {}
                if os.path.exists(metadata_file):
                    try:
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                    except:
                        pass
                results[path] = metadata
        
        handler.send_json_response(results)
    
    def api_update_batch_metadata(self, handler):
        """批量更新文件元数据"""
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            handler.send_json_response({"error": "No data provided"}, 400)
            return
        
        try:
            data = json.loads(handler.rfile.read(content_length))
            results = {}
            
            for path, metadata in data.items():
                full_path = os.path.join(self.config['base_dir'], path)
                metadata_file = full_path + '.meta'
                try:
                    with open(metadata_file, 'w', encoding='utf-8') as f:
                        json.dump(metadata, f, ensure_ascii=False, indent=2)
                    results[path] = {"success": True}
                except Exception as e:
                    results[path] = {"success": False, "error": str(e)}
            
            handler.send_json_response(results)
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)
    
    # ==================== 文件版本控制API ====================
    
    def api_get_file_versions(self, handler, filename):
        """获取文件版本列表"""
        # 这里可以实现版本控制系统
        # 简化实现：检查备份文件
        full_path = os.path.join(self.config['base_dir'], filename)
        versions = []
        
        # 查找备份文件
        dir_path = os.path.dirname(full_path)
        base_name = os.path.basename(full_path)
        
        if os.path.exists(dir_path):
            for item in os.listdir(dir_path):
                if item.startswith(base_name) and item != base_name:
                    backup_path = os.path.join(dir_path, item)
                    try:
                        stat = os.stat(backup_path)
                        versions.append({
                            "name": item,
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                        })
                    except OSError:
                        continue
        
        handler.send_json_response({
            "filename": filename,
            "versions": versions
        })
    
    def api_create_file_version(self, handler, filename):
        """创建文件版本（备份）"""
        import time
        full_path = os.path.join(self.config['base_dir'], filename)
        if not os.path.exists(full_path):
            handler.send_json_response({"error": "File not found"}, 404)
            return
        
        # 创建备份
        timestamp = int(time.time())
        backup_path = f"{full_path}.v{timestamp}"
        
        try:
            import shutil
            shutil.copy2(full_path, backup_path)
            handler.send_json_response({
                "success": True,
                "version": backup_path
            })
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)
    
    # ==================== 缩略图API ====================
    
    def api_get_file_thumbnail(self, handler, filename, query_params):
        """获取文件缩略图"""
        import mimetypes
        
        full_path = os.path.join(self.config['base_dir'], filename)
        if not os.path.exists(full_path):
            handler.send_json_response({"error": "File not found"}, 404)
            return
        
        mime_type, _ = mimetypes.guess_type(full_path)
        if not mime_type or not mime_type.startswith('image/'):
            handler.send_json_response({"error": "Not an image file"}, 400)
            return
        
        width = int(query_params.get('width', ['200'])[0])
        height = int(query_params.get('height', ['200'])[0])
        
        try:
            from PIL import Image
            
            with Image.open(full_path) as img:
                img.thumbnail((width, height), Image.LANCZOS)
                
                import io
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=85)
                thumbnail_data = buffer.getvalue()
            
            handler.send_response(200)
            handler.send_header("Content-Type", "image/jpeg")
            handler.send_header("Content-Length", str(len(thumbnail_data)))
            handler.send_header("Cache-Control", "public, max-age=86400")
            handler.end_headers()
            handler.wfile.write(thumbnail_data)
            
        except ImportError:
            handler.send_json_response({"error": "PIL/Pillow not installed"}, 500)
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)
    
    # ==================== 服务器监控API ====================
    
    def api_get_realtime_stats(self, handler):
        """获取实时服务器统计"""
        try:
            import psutil
            result = {
                "timestamp": datetime.now().isoformat(),
                "cpu": {
                    "percent": psutil.cpu_percent(interval=0.1),
                    "count": psutil.cpu_count()
                },
                "memory": {
                    "total": psutil.virtual_memory().total,
                    "available": psutil.virtual_memory().available,
                    "percent": psutil.virtual_memory().percent,
                    "used": psutil.virtual_memory().used,
                    "free": psutil.virtual_memory().free
                },
                "disk": {
                    "total": psutil.disk_usage(self.config['base_dir']).total,
                    "used": psutil.disk_usage(self.config['base_dir']).used,
                    "free": psutil.disk_usage(self.config['base_dir']).free,
                    "percent": psutil.disk_usage(self.config['base_dir']).percent
                }
            }
            # 尝试获取网络数据，失败时忽略
            try:
                result["network"] = {
                    "connections": len(psutil.net_connections()),
                    "io": psutil.net_io_counters()._asdict() if psutil.net_io_counters() else None
                }
            except (PermissionError, OSError):
                result["network"] = {"connections": 0, "io": None, "note": "Permission denied"}

            # 尝试获取 CPU 频率，失败时忽略
            try:
                result["cpu"]["freq"] = psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
            except (PermissionError, OSError):
                result["cpu"]["freq"] = None

            handler.send_json_response(result)
        except ImportError:
            handler.send_json_response({"error": "psutil not installed"}, 500)
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)
    
    def api_get_monitor_history(self, handler, query_params):
        """获取历史监控数据"""
        hours = int(query_params.get('hours', ['24'])[0])

        # 尝试从数据库获取
        if self.db_enabled and self.db:
            try:
                records = self.db.get_monitor_history(hours)
                data = [r.to_dict() for r in records]
                handler.send_json_response({
                    "hours": hours,
                    "data": data,
                    "source": "database"
                })
                return
            except Exception as e:
                print(f"Error getting monitor history from database: {e}")

        # 回退到空数据
        handler.send_json_response({
            "hours": hours,
            "data": [],
            "source": "none"
        })
    
    # ==================== Webhook API ====================

    def api_list_webhooks(self, handler):
        """列出所有webhook"""
        # 从数据库获取
        if self.db_enabled and self.db:
            try:
                webhooks = self.db.get_webhooks()
                handler.send_json_response({
                    "webhooks": [w.to_dict() for w in webhooks],
                    "count": len(webhooks),
                    "source": "database"
                })
                return
            except Exception as e:
                print(f"Error getting webhooks from database: {e}")

        # 回退到空列表
        handler.send_json_response({
            "webhooks": [],
            "count": 0,
            "source": "none"
        })

    def api_create_webhook(self, handler):
        """创建webhook"""
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            handler.send_json_response({"error": "No webhook data provided"}, 400)
            return

        try:
            webhook_data = json.loads(handler.rfile.read(content_length))

            # 验证必要字段
            name = webhook_data.get('name', '').strip()
            url = webhook_data.get('url', '').strip()

            if not name:
                handler.send_json_response({"error": "Webhook name is required"}, 400)
                return
            if not url:
                handler.send_json_response({"error": "Webhook URL is required"}, 400)
                return

            # 保存到数据库
            if self.db_enabled and self.db:
                record = self.db.add_webhook(
                    name=name,
                    url=url,
                    events=webhook_data.get('events', []),
                    secret=webhook_data.get('secret'),
                    enabled=webhook_data.get('enabled', True)
                )
                handler.send_json_response({
                    "success": True,
                    "message": "Webhook created successfully",
                    "webhook": record.to_dict()
                })
            else:
                handler.send_json_response({
                    "success": False,
                    "error": "Database not available"
                }, 503)

        except json.JSONDecodeError:
            handler.send_json_response({"error": "Invalid JSON format"}, 400)
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)

    def api_get_webhook(self, handler, webhook_id):
        """获取webhook详情"""
        webhook_id = int(webhook_id)

        if self.db_enabled and self.db:
            try:
                webhook = self.db.get_webhook(webhook_id)
                if webhook:
                    handler.send_json_response({
                        "webhook": webhook.to_dict()
                    })
                else:
                    handler.send_json_response({
                        "error": "Webhook not found"
                    }, 404)
                return
            except Exception as e:
                handler.send_json_response({"error": str(e)}, 500)

        handler.send_json_response({
            "error": "Database not available"
        }, 503)

    def api_delete_webhook(self, handler, webhook_id):
        """删除webhook"""
        webhook_id = int(webhook_id)

        if self.db_enabled and self.db:
            try:
                success = self.db.delete_webhook(webhook_id)
                if success:
                    handler.send_json_response({
                        "success": True,
                        "message": "Webhook deleted successfully"
                    })
                else:
                    handler.send_json_response({
                        "error": "Webhook not found"
                    }, 404)
                return
            except Exception as e:
                handler.send_json_response({"error": str(e)}, 500)

        handler.send_json_response({
            "success": False,
            "error": "Database not available"
        }, 503)

    def api_test_webhook(self, handler, webhook_id):
        """测试webhook"""
        webhook_id = int(webhook_id)

        if self.db_enabled and self.db:
            try:
                webhook = self.db.get_webhook(webhook_id)
                if not webhook:
                    handler.send_json_response({
                        "error": "Webhook not found"
                    }, 404)
                    return

                # 发送测试请求
                import urllib.request
                import urllib.parse

                test_payload = {
                    "event": "test",
                    "timestamp": datetime.now().isoformat(),
                    "data": {
                        "message": "This is a test webhook from HYC下载站"
                    }
                }

                try:
                    data = json.dumps(test_payload).encode('utf-8')
                    req = urllib.request.Request(
                        webhook.url,
                        data=data,
                        headers={
                            'Content-Type': 'application/json',
                            'X-Webhook-Secret': webhook.secret or ''
                        },
                        method='POST'
                    )
                    with urllib.request.urlopen(req, timeout=10) as response:
                        handler.send_json_response({
                            "success": True,
                            "webhook_id": webhook_id,
                            "test_result": "Webhook test successful",
                            "status_code": response.status
                        })
                except urllib.error.HTTPError as e:
                    handler.send_json_response({
                        "success": False,
                        "webhook_id": webhook_id,
                        "error": f"HTTP Error: {e.code} {e.reason}"
                    }, 400)
                except Exception as e:
                    handler.send_json_response({
                        "success": False,
                        "webhook_id": webhook_id,
                        "error": str(e)
                    }, 400)

            except Exception as e:
                handler.send_json_response({"error": str(e)}, 500)
        else:
            handler.send_json_response({
                "success": False,
                "error": "Database not available"
            }, 503)

    def api_get_webhook_deliveries(self, handler, webhook_id):
        """获取 webhook 交付历史"""
        webhook_id = int(webhook_id)

        # 验证 webhook 存在
        if self.db_enabled and self.db:
            try:
                webhook = self.db.get_webhook(webhook_id)
                if not webhook:
                    handler.send_json_response({
                        "error": "Webhook not found"
                    }, 404)
                    return

                # 获取交付历史
                deliveries = self.db.get_webhook_deliveries(webhook_id=webhook_id, limit=50)

                handler.send_json_response({
                    "webhook_id": webhook_id,
                    "webhook_name": webhook.name,
                    "deliveries": [d.to_dict() for d in deliveries],
                    "count": len(deliveries)
                })

            except Exception as e:
                handler.send_json_response({"error": str(e)}, 500)
        else:
            handler.send_json_response({
                "error": "Database not available"
            }, 503)

    def api_get_webhook_stats(self, handler, webhook_id):
        """获取 webhook 交付统计"""
        webhook_id = int(webhook_id)

        if self.db_enabled and self.db:
            try:
                stats = self.db.get_webhook_stats(webhook_id)

                handler.send_json_response({
                    "webhook_id": webhook_id,
                    "stats": stats
                })

            except Exception as e:
                handler.send_json_response({"error": str(e)}, 500)
        else:
            handler.send_json_response({
                "error": "Database not available"
            }, 503)

    def api_update_webhook(self, handler, webhook_id):
        """更新 webhook 配置"""
        webhook_id = int(webhook_id)

        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            handler.send_json_response({"error": "No webhook data provided"}, 400)
            return

        try:
            webhook_data = json.loads(handler.rfile.read(content_length))

            if self.db_enabled and self.db:
                webhook = self.db.get_webhook(webhook_id)
                if not webhook:
                    handler.send_json_response({
                        "error": "Webhook not found"
                    }, 404)
                    return

                # 更新 webhook
                updated = self.db.update_webhook(
                    webhook_id,
                    name=webhook_data.get('name', webhook.name),
                    url=webhook_data.get('url', webhook.url),
                    events=webhook_data.get('events'),
                    secret=webhook_data.get('secret'),
                    enabled=webhook_data.get('enabled', webhook.enabled)
                )

                if updated:
                    handler.send_json_response({
                        "success": True,
                        "message": "Webhook updated successfully",
                        "webhook": updated.to_dict()
                    })
                else:
                    handler.send_json_response({
                        "success": False,
                        "error": "Failed to update webhook"
                    }, 500)
            else:
                handler.send_json_response({
                    "success": False,
                    "error": "Database not available"
                }, 503)

        except json.JSONDecodeError:
            handler.send_json_response({"error": "Invalid JSON format"}, 400)
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)

    # ==================== 同步管理 API (真实数据) ====================

    def api_get_sync_sources(self, handler):
        """获取所有同步源（真实数据）"""
        # 从 sync_manager 获取真实数据
        if hasattr(handler, 'sync_manager') and handler.sync_manager:
            sources = getattr(handler.sync_manager, 'sync_sources', {})
            # 转换为数组格式
            sources_list = []
            for name, config in sources.items():
                item = {"name": name}
                item.update(config)
                sources_list.append(item)
            handler.send_json_response({
                "sources": sources_list,
                "count": len(sources_list)
            })
        else:
            handler.send_json_response({
                "sources": [],
                "count": 0,
                "message": "Sync manager not available"
            })

    def api_add_sync_source(self, handler):
        """添加同步源"""
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            handler.send_json_response({"error": "No data provided"}, 400)
            return

        try:
            data = json.loads(handler.rfile.read(content_length))

            if hasattr(handler, 'sync_manager') and handler.sync_manager:
                name = data.get('name')
                config = data.get('config', {})

                if not name:
                    handler.send_json_response({"error": "Source name required"}, 400)
                    return

                success = handler.sync_manager.add_source(name, config)
                handler.send_json_response({
                    "success": success,
                    "name": name
                })
            else:
                handler.send_json_response({"error": "Sync manager not available"}, 500)

        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)

    def api_start_sync(self, handler, source_name):
        """启动同步"""
        if hasattr(handler, 'sync_manager') and handler.sync_manager:
            task_id = handler.sync_manager.start_sync(source_name)
            if task_id:
                handler.send_json_response({
                    "success": True,
                    "task_id": task_id,
                    "source_name": source_name
                })
            else:
                handler.send_json_response({
                    "success": False,
                    "error": "Failed to start sync",
                    "source_name": source_name
                }, 500)
        else:
            handler.send_json_response({"error": "Sync manager not available"}, 500)

    def api_stop_sync(self, handler, source_name):
        """停止同步"""
        if hasattr(handler, 'sync_manager') and handler.sync_manager:
            handler.sync_manager.stop_all_tasks_for_source(source_name)
            handler.send_json_response({
                "success": True,
                "source_name": source_name
            })
        else:
            handler.send_json_response({"error": "Sync manager not available"}, 500)

    def api_get_sync_status(self, handler, source_name):
        """获取同步状态（真实数据）"""
        # source_name 格式: source_name/status，需要提取
        if source_name.endswith('/status'):
            source_name = source_name[:-7]

        if hasattr(handler, 'sync_manager') and handler.sync_manager:
            status = handler.sync_manager.get_source_status(source_name)
            handler.send_json_response(status)
        else:
            handler.send_json_response({"error": "Sync manager not available"}, 500)

    def api_get_sync_history(self, handler, query_params):
        """获取同步历史"""
        limit = int(query_params.get('limit', ['100'])[0])

        if hasattr(handler, 'sync_manager') and handler.sync_manager:
            history = handler.sync_manager.get_sync_history(limit=limit)
            handler.send_json_response({
                "history": history,
                "count": len(history)
            })
        else:
            handler.send_json_response({
                "history": [],
                "count": 0
            })

    # ==================== 定时任务调度 API ====================

    def api_get_scheduled_tasks(self, handler):
        """获取所有定时任务状态"""
        if hasattr(handler, 'sync_manager') and handler.sync_manager:
            scheduler = getattr(handler.sync_manager, 'task_scheduler', None)
            if scheduler and hasattr(scheduler, 'get_all_tasks'):
                tasks = scheduler.get_all_tasks()
                handler.send_json_response({
                    "tasks": tasks,
                    "count": len(tasks)
                })
                return

        handler.send_json_response({
            "tasks": [],
            "count": 0,
            "message": "Scheduler not available"
        })

    def api_update_sync_schedule(self, handler, source_name):
        """更新同步源的定时配置"""
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            handler.send_json_response({"error": "No schedule data provided"}, 400)
            return

        try:
            data = json.loads(handler.rfile.read(content_length))

            if hasattr(handler, 'sync_manager') and handler.sync_manager:
                # 更新同步源的定时配置
                sync_manager = handler.sync_manager

                if hasattr(sync_manager, 'scheduled_syncs'):
                    schedule_config = data.get('schedule', {})
                    if source_name not in sync_manager.scheduled_syncs:
                        sync_manager.scheduled_syncs[source_name] = {}

                    sync_manager.scheduled_syncs[source_name] = {
                        'type': schedule_config.get('type', 'interval'),
                        'config': {
                            'cron': schedule_config.get('cron'),
                            'interval': schedule_config.get('interval', {}),
                            'enabled': schedule_config.get('enabled', True)
                        }
                    }

                    # 如果调度器已运行，更新任务
                    if sync_manager.task_scheduler:
                        task_name = f"sync_{source_name}"
                        existing_task = sync_manager.task_scheduler.get_task(task_name)
                        if existing_task:
                            sync_manager.task_scheduler.update_task_config(
                                task_name,
                                sync_manager.scheduled_syncs[source_name]['config']
                            )
                            if schedule_config.get('enabled'):
                                sync_manager.task_scheduler.enable_task(task_name, True)
                            else:
                                sync_manager.task_scheduler.enable_task(task_name, False)

                handler.send_json_response({
                    "success": True,
                    "source_name": source_name,
                    "schedule": sync_manager.scheduled_syncs.get(source_name, {})
                })
            else:
                handler.send_json_response({"error": "Sync manager not available"}, 500)

        except json.JSONDecodeError:
            handler.send_json_response({"error": "Invalid JSON format"}, 400)
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)

    def api_run_sync_now(self, handler, source_name):
        """立即触发同步（覆盖定时）"""
        if hasattr(handler, 'sync_manager') and handler.sync_manager:
            success = handler.sync_manager.start_sync(source_name)
            handler.send_json_response({
                "success": success,
                "source_name": source_name,
                "message": "Sync started" if success else "Failed to start sync"
            })
        else:
            handler.send_json_response({"error": "Sync manager not available"}, 500)

    def api_sync_packages(self, handler):
        """临时单次同步指定源的特定包"""
        try:
            # 读取请求体
            content_length = int(handler.headers.get('Content-Length', 0))
            if content_length == 0:
                handler.send_json_response({"error": "请求体不能为空"}, 400)
                return

            body = handler.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            # 获取参数
            source = data.get('source')
            packages = data.get('packages', [])

            if not source:
                handler.send_json_response({"error": "缺少 'source' 参数"}, 400)
                return

            if not packages or not isinstance(packages, list):
                handler.send_json_response({"error": "请提供有效的 'packages' 列表"}, 400)
                return

            # 调用 sync_manager
            if hasattr(handler, 'sync_manager') and handler.sync_manager:
                result = handler.sync_manager.sync_packages(source, packages)
                handler.send_json_response(result)
            else:
                handler.send_json_response({"error": "Sync manager not available"}, 500)

        except json.JSONDecodeError:
            handler.send_json_response({"error": "Invalid JSON format"}, 400)
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)

    def api_get_temp_sync_status(self, handler, source_name):
        """获取临时同步状态"""
        if hasattr(handler, 'sync_manager') and handler.sync_manager:
            sync_manager = handler.sync_manager
            # 查找匹配的临时同步任务
            temp_status = None
            if hasattr(sync_manager, 'sync_status'):
                for task_name, status in sync_manager.sync_status.items():
                    if status.get('source_name') == source_name and status.get('is_temp_sync'):
                        temp_status = status
                        break

            if temp_status:
                handler.send_json_response({
                    "success": True,
                    "source": source_name,
                    "status": temp_status.get('status'),
                    "packages": temp_status.get('packages', []),
                    "files_synced": temp_status.get('files_synced', 0),
                    "total_files": temp_status.get('total_files', 0),
                    "last_sync": temp_status.get('last_sync'),
                    "error": temp_status.get('error')
                })
            else:
                handler.send_json_response({
                    "success": False,
                    "error": f"没有找到 {source_name} 的临时同步任务"
                })
        else:
            handler.send_json_response({"error": "Sync manager not available"}, 500)

    # ==================== 系统监控 API (真实数据) ====================

    def api_get_monitor_detailed(self, handler):
        """获取详细监控数据"""
        if hasattr(handler, 'monitor') and handler.monitor:
            stats = handler.monitor.get_realtime_stats()
            handler.send_json_response(stats)
        else:
            handler.send_json_response({
                "error": "Monitor not available",
                "timestamp": datetime.now().isoformat()
            }, 500)

    def api_get_monitor_history_detailed(self, handler, query_params):
        """获取历史监控数据（详细版）"""
        hours = int(query_params.get('hours', ['24'])[0])

        # 尝试从数据库获取详细统计
        if self.db_enabled and self.db:
            try:
                stats = self.db.get_monitor_stats(hours)
                history = self.db.get_monitor_history(hours)
                handler.send_json_response({
                    "hours": hours,
                    "stats": stats,
                    "history": [r.to_dict() for r in history],
                    "source": "database"
                })
                return
            except Exception as e:
                print(f"Error getting monitor stats from database: {e}")

        # 回退到原有实现
        if hasattr(handler, 'monitor') and handler.monitor:
            history = handler.monitor.get_monitor_history(hours)
            handler.send_json_response({
                "hours": hours,
                "data": history,
                "source": "monitor"
            })
        else:
            handler.send_json_response({
                "hours": hours,
                "data": [],
                "source": "none"
            })

    def api_get_monitor_summary(self, handler):
        """获取监控摘要"""
        if hasattr(handler, 'monitor') and handler.monitor:
            summary = handler.monitor.get_stats_summary()
            handler.send_json_response(summary)
        else:
            handler.send_json_response({
                "status": "unavailable",
                "message": "Monitor not available"
            }, 500)

    def api_get_health_status(self, handler):
        """获取健康状态"""
        if hasattr(handler, 'monitor') and handler.monitor:
            health = handler.monitor.get_health_status()
            handler.send_json_response(health)
        else:
            handler.send_json_response({
                "status": "unknown",
                "message": "Monitor not available"
            })

    # ==================== 镜像源健康检查 API ====================

    def api_get_source_health(self, handler, query_params):
        """获取镜像源健康状态"""
        try:
            from core.health_check import HealthChecker, HealthStatus

            mirrors = self.config.get('mirrors', {})
            checker = HealthChecker(self.config.get('health_check', {}))

            results = []
            for mirror_type, mirror_config in mirrors.items():
                if not isinstance(mirror_config, dict):
                    continue

                # 获取该镜像类型的所有源
                sources = mirror_config.get('sources', [])
                for source_name in sources:
                    result = checker.check_source(source_name, {
                        'url': self._get_source_url(mirror_type, source_name)
                    })
                    results.append({
                        'mirror_type': mirror_type,
                        'source_name': source_name,
                        'status': result.status.value,
                        'response_time_ms': round(result.response_time, 2),
                        'http_status': result.http_status,
                        'error': result.error_message,
                        'success_rate': round(result.success_rate, 2),
                        'last_check': result.last_check.isoformat() if result.last_check else None,
                        'consecutive_failures': result.consecutive_failures
                    })

            handler.send_json_response({
                'sources': results,
                'count': len(results),
                'summary': checker.get_stats()
            })

        except Exception as e:
            handler.send_json_response({
                'error': str(e)
            }, 500)

    def api_check_source(self, handler, source_name):
        """手动触发单个源的健康检查"""
        try:
            from core.health_check import HealthChecker, HealthStatus

            checker = HealthChecker(self.config.get('health_check', {}))
            mirrors = self.config.get('mirrors', {})

            # 查找源对应的镜像类型
            mirror_type = None
            source_url = ''
            for mtype, mconfig in mirrors.items():
                if not isinstance(mconfig, dict):
                    continue
                sources = mconfig.get('sources', [])
                if source_name in sources:
                    mirror_type = mtype
                    source_config = mconfig.get('sources_config', {}).get(source_name, {})
                    source_url = source_config.get('url', '')
                    break

            if not mirror_type:
                handler.send_json_response({
                    'error': f"Source '{source_name}' not found"
                }, 404)
                return

            result = checker.check_source(source_name, {'url': source_url})

            handler.send_json_response({
                'source_name': source_name,
                'mirror_type': mirror_type,
                'status': result.status.value,
                'response_time_ms': round(result.response_time, 2),
                'http_status': result.http_status,
                'error': result.error_message,
                'success_rate': round(result.success_rate, 2),
                'last_check': result.last_check.isoformat() if result.last_check else None
            })

        except Exception as e:
            handler.send_json_response({
                'error': str(e)
            }, 500)

    def api_get_failover_status(self, handler):
        """获取故障切换状态"""
        try:
            from core.health_check import MirrorFailoverManager

            failover = MirrorFailoverManager(self.config)
            failover.initialize()

            handler.send_json_response({
                'failover_enabled': failover.failover_enabled,
                'active_sources': failover._active_source,
                'health_summary': failover.get_health_summary(),
                'failover_history': failover.get_failover_history()
            })

        except Exception as e:
            handler.send_json_response({
                'error': str(e)
            }, 500)

    def api_trigger_failover(self, handler, mirror_type):
        """手动触发故障切换"""
        try:
            from core.health_check import MirrorFailoverManager

            failover = MirrorFailoverManager(self.config)
            failover.initialize()

            success = failover.perform_failover(mirror_type)

            handler.send_json_response({
                'mirror_type': mirror_type,
                'success': success,
                'active_source': failover.get_active_source(mirror_type),
                'failover_history': failover.get_failover_history()
            })

        except Exception as e:
            handler.send_json_response({
                'error': str(e)
            }, 500)

    def _get_source_url(self, mirror_type: str, source_name: str) -> str:
        """获取源的 URL"""
        mirrors = self.config.get('mirrors', {})
        mirror_config = mirrors.get(mirror_type, {})

        # 先检查 sources_config
        sources_config = mirror_config.get('sources_config', {})
        if source_name in sources_config:
            return sources_config[source_name].get('url', '')

        # 使用 URL 模板
        url_template = mirror_config.get('url_template', '')
        if url_template and '{mirror}' in url_template:
            return url_template.replace('{mirror}', source_name)

        return ''

    # ==================== 缓存管理 API ====================

    def api_get_cache_stats(self, handler):
        """获取缓存统计"""
        if hasattr(handler, 'cache_manager') and handler.cache_manager:
            stats = handler.cache_manager.get_stats()
            # 转换字段名以匹配前端期望
            handler.send_json_response({
                "size": stats.get('total_size', 0),
                "count": stats.get('file_count', 0),
                "hit_rate": stats.get('hit_rate', 0),
                "last_clean": stats.get('last_clean', None),
                "strategy": stats.get('strategy', 'unknown')
            })
        else:
            handler.send_json_response({
                "size": 0,
                "count": 0,
                "hit_rate": 0,
                "last_clean": None,
                "strategy": "unknown"
            })

    def api_clean_cache(self, handler):
        """清理缓存"""
        source = None  # 可以从请求中获取

        if hasattr(handler, 'cache_manager') and handler.cache_manager:
            count = handler.cache_manager.clear(source)
            handler.send_json_response({
                "success": True,
                "deleted_count": count
            })
        else:
            handler.send_json_response({"error": "Cache manager not available"}, 500)

    def api_get_cache_usage(self, handler):
        """获取缓存使用详情"""
        if hasattr(handler, 'cache_manager') and handler.cache_manager:
            usage = handler.cache_manager.get_cache_usage()
            handler.send_json_response({
                "items": usage,
                "count": len(usage)
            })
        else:
            handler.send_json_response({
                "items": [],
                "count": 0
            })

    def api_get_recent_activity(self, handler, query_params):
        """获取最近活动"""
        import traceback
        limit = int(query_params.get('limit', [20])[0])
        limit = min(max(limit, 1), 100)  # 限制在 1-100 之间
        offset = int(query_params.get('offset', [0])[0])
        offset = max(offset, 0)  # 确保 offset 不为负数

        activities = []
        errors = []
        all_activities = []  # 收集所有活动用于统一排序

        # 从同步记录获取
        if hasattr(handler, 'sync_manager') and handler.sync_manager:
            try:
                if hasattr(handler.sync_manager, 'db_enabled') and handler.sync_manager.db_enabled:
                    from core.database import get_db
                    db = get_db()
                    if db:
                        with db.session() as session:
                            from core.database import SyncRecord
                            # 获取足够多的记录用于分页
                            fetch_limit = limit + offset
                            records = session.query(SyncRecord).order_by(
                                SyncRecord.start_time.desc()
                            ).limit(fetch_limit).all()
                            for r in records:
                                all_activities.append({
                                    "time": datetime.fromtimestamp(r.start_time).isoformat() if r.start_time else '',
                                    "timestamp": r.start_time or 0,
                                    "type": "同步",
                                    "content": f"同步任务: {r.source_name or r.sync_id}",
                                    "status": "成功" if r.status == "completed" else ("进行中" if r.status == "running" else "失败"),
                                    "status_type": "success" if r.status == "completed" else ("running" if r.status == "running" else "error")
                                })
                    else:
                        errors.append("同步记录: db 为空")
            except Exception as e:
                errors.append(f"同步记录: {str(e)}")
                traceback.print_exc()

        # 从下载记录获取
        try:
            # 优先使用 handler.db
            db = getattr(handler, 'db', None)
            if db is None:
                from core.database import get_db
                db = get_db()

            if db:
                from core.database import DownloadRecord
                with db.session() as session:
                    # 获取足够多的记录用于分页
                    fetch_limit = limit + offset
                    records = session.query(DownloadRecord).order_by(
                        DownloadRecord.download_time.desc()
                    ).limit(fetch_limit).all()
                    for r in records:
                        all_activities.append({
                            "time": datetime.fromtimestamp(r.download_time).isoformat() if r.download_time else '',
                            "timestamp": r.download_time or 0,
                            "type": "下载",
                            "content": f"下载: {r.file_path or 'Unknown'}",
                            "status": "成功" if r.success else "失败",
                            "status_type": "success" if r.success else "error"
                        })
            else:
                errors.append("下载记录: db 为空")
        except Exception as e:
            errors.append(f"下载记录: {str(e)}")
            traceback.print_exc()

        # 从告警记录获取
        try:
            from core.alerts import AlertManager
            alert_manager = AlertManager(self.config.get('alerts', {}))
            fetch_limit = limit + offset
            alerts = alert_manager.get_alerts(limit=fetch_limit)
            for a in alerts:
                all_activities.append({
                    "time": a.get('timestamp', ''),
                    "timestamp": 0,
                    "type": "告警",
                    "content": a.get('message', ''),
                    "status": a.get('severity', 'info').upper(),
                    "status_type": "error" if a.get('severity') == 'error' else ("warning" if a.get('severity') == 'warning' else "info")
                })
        except Exception as e:
            errors.append(f"告警记录: {str(e)}")
            traceback.print_exc()

        # 按时间戳排序并应用分页
        all_activities.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

        # 应用 offset 和 limit
        paged_activities = all_activities[offset:offset + limit]

        handler.send_json_response({
            "activities": paged_activities,
            "count": len(paged_activities),
            "total": len(all_activities),
            "_debug": {"errors": errors} if errors else {}
        })

    # ==================== 镜像加速源 API ====================

    def api_list_mirrors(self, handler):
        """列出所有镜像加速源（仅从配置文件读取，无内置预设）"""
        # 仅从配置文件读取镜像配置
        mirrors_config = {}
        try:
            import json
            import os
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            # 优先使用 settings.json
            settings_path = os.path.join(project_root, 'settings.json')
            config_path = settings_path
            if not os.path.exists(config_path):
                # 回退到 config.json
                config_path = os.path.join(project_root, 'config.json')

            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    mirrors_config = config_data.get('mirrors', {})
        except Exception:
            pass

        # 如果文件没有配置，回退到内存配置
        if not mirrors_config:
            mirrors_config = self.config.get('mirrors', {})

        # 收集所有镜像（从 mirrors 配置读取）
        available_mirrors = {}

        # 从 mirrors 配置读取所有镜像
        for mirror_name, mirror_config in mirrors_config.items():
            available_mirrors[mirror_name] = {
                "name": mirror_config.get('name', mirror_name),
                "type": mirror_config.get('type', 'http'),
                "description": mirror_config.get('description', f"{mirror_name} 镜像"),
                "url": mirror_config.get('url', ''),
                "target": mirror_config.get('target', ''),
                "enabled": mirror_config.get('enabled', True),
                "custom": mirror_config.get('custom', True),
                "auto_sync": mirror_config.get('auto_sync', False),
                "schedule": mirror_config.get('schedule', {}),
                "last_sync": mirror_config.get('last_sync'),
                "storage_dir": mirror_config.get('storage_dir', mirror_name)
            }

        handler.send_json_response({
            "mirrors": available_mirrors,
            "count": len(available_mirrors)
        })

    def api_get_mirror_info(self, handler, mirror_name):
        """获取镜像加速源信息"""
        from mirrors import get_mirror_handler

        handler_class = get_mirror_handler(mirror_name)
        if not handler_class:
            handler.send_json_response({
                "error": f"Unknown mirror type: {mirror_name}"
            }, 400)
            return

        # 获取镜像配置
        mirror_config = self.config.get('mirrors', {}).get(mirror_name, {})

        handler.send_json_response({
            "name": mirror_name,
            "enabled": mirror_config.get('enabled', False),
            "config": mirror_config
        })

    def api_refresh_mirror(self, handler, mirror_name):
        """刷新镜像元数据"""
        handler.send_json_response({
            "success": True,
            "message": f"Mirror {mirror_name} refresh initiated"
        })

    def api_enable_mirror(self, handler, mirror_name, query_params):
        """启用/禁用镜像源"""
        # 获取 enabled 参数
        enabled = query_params.get('enabled', ['true'])[0].lower() == 'true'

        # 更新内存中的配置
        if 'mirrors' not in self.config:
            self.config['mirrors'] = {}
        if mirror_name not in self.config['mirrors']:
            self.config['mirrors'][mirror_name] = {}
        self.config['mirrors'][mirror_name]['enabled'] = enabled

        # 保存到配置文件 - 使用项目根目录的绝对路径
        try:
            import json
            import os
            # 获取项目根目录 (vs1 目录)
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            # 优先使用 settings.json
            settings_path = os.path.join(project_root, 'settings.json')
            config_path = settings_path
            if not os.path.exists(config_path):
                config_path = os.path.join(project_root, 'config.json')

            config_data = {}

            # 如果配置文件存在，读取它
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)

            # 更新配置
            if 'mirrors' not in config_data:
                config_data['mirrors'] = {}
            if mirror_name not in config_data['mirrors']:
                config_data['mirrors'][mirror_name] = {}
            config_data['mirrors'][mirror_name]['enabled'] = enabled

            # 保存配置
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            handler.send_json_response({
                "success": False,
                "error": f"Failed to save config: {str(e)}"
            }, 500)
            return

        handler.send_json_response({
            "success": True,
            "mirror": mirror_name,
            "enabled": enabled
        })

    def api_add_mirror(self, handler):
        """添加自定义加速源"""
        # 读取请求体
        try:
            content_length = int(handler.headers.get('Content-Length', 0))
            if content_length > 0:
                body = handler.rfile.read(content_length)
                import json
                data = json.loads(body.decode('utf-8'))
            else:
                data = {}
        except Exception as e:
            handler.send_json_response({
                "success": False,
                "error": f"Invalid request body: {str(e)}"
            }, 400)
            return

        # 验证必要参数
        mirror_name = data.get('name', '').strip()
        mirror_type = data.get('type', 'custom').strip()
        mirror_url = data.get('url', '').strip()

        if not mirror_name:
            handler.send_json_response({
                "success": False,
                "error": "Mirror name is required"
            }, 400)
            return

        # 验证名称格式（只允许字母、数字、下划线、连字符）
        if not mirror_name.replace('_', '').replace('-', '').isalnum():
            handler.send_json_response({
                "success": False,
                "error": "Mirror name can only contain letters, numbers, underscores and hyphens"
            }, 400)
            return

        # 保存到配置文件
        try:
            import os
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            # 优先使用 settings.json
            settings_path = os.path.join(project_root, 'settings.json')
            config_path = settings_path
            if not os.path.exists(config_path):
                config_path = os.path.join(project_root, 'config.json')

            config_data = {}
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)

            # 初始化 mirrors 节
            if 'mirrors' not in config_data:
                config_data['mirrors'] = {}

            # 添加新镜像
            config_data['mirrors'][mirror_name] = {
                "type": mirror_type,
                "url": mirror_url,
                "enabled": data.get('enabled', True),
                "description": data.get('description', f"Custom mirror: {mirror_name}"),
                "storage_dir": data.get('storage_dir', mirror_name),
                "custom": True,
                "created_at": datetime.now().isoformat()
            }

            # 保存配置
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            handler.send_json_response({
                "success": False,
                "error": f"Failed to save config: {str(e)}"
            }, 500)
            return

        handler.send_json_response({
            "success": True,
            "message": f"Mirror '{mirror_name}' added successfully",
            "mirror": {
                "name": mirror_name,
                "type": mirror_type,
                "url": mirror_url,
                "enabled": data.get('enabled', True)
            }
        })

    def api_update_mirror(self, handler, mirror_name):
        """更新自定义加速源"""
        # 读取请求体
        try:
            content_length = int(handler.headers.get('Content-Length', 0))
            if content_length > 0:
                body = handler.rfile.read(content_length)
                import json
                data = json.loads(body.decode('utf-8'))
            else:
                data = {}
        except Exception as e:
            handler.send_json_response({
                "success": False,
                "error": f"Invalid request body: {str(e)}"
            }, 400)
            return

        # 读取并更新配置文件
        try:
            import os
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            settings_path = os.path.join(project_root, 'settings.json')
            config_path = settings_path
            if not os.path.exists(config_path):
                config_path = os.path.join(project_root, 'config.json')

            if not os.path.exists(config_path):
                handler.send_json_response({
                    "success": False,
                    "error": "Config file not found"
                }, 404)
                return

            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            # 检查mirrors节是否存在
            if 'mirrors' not in config_data:
                config_data['mirrors'] = {}

            # 检查镜像是否存在
            if mirror_name not in config_data['mirrors']:
                handler.send_json_response({
                    "success": False,
                    "error": f"Mirror '{mirror_name}' not found"
                }, 404)
                return

            # 更新镜像信息（只更新提供的字段）
            mirror_data = config_data['mirrors'][mirror_name]
            if 'type' in data:
                mirror_data['type'] = data['type']
            if 'url' in data:
                mirror_data['url'] = data['url']
            if 'target' in data:
                mirror_data['target'] = data['target']
            if 'description' in data:
                mirror_data['description'] = data['description']
            if 'enabled' in data:
                mirror_data['enabled'] = data['enabled']
            if 'storage_dir' in data:
                mirror_data['storage_dir'] = data['storage_dir']
            mirror_data['updated_at'] = datetime.now().isoformat()

            config_data['mirrors'][mirror_name] = mirror_data

            # 保存配置
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            handler.send_json_response({
                "success": False,
                "error": f"Failed to save config: {str(e)}"
            }, 500)
            return

        handler.send_json_response({
            "success": True,
            "message": f"Mirror '{mirror_name}' updated successfully",
            "mirror": {
                "name": mirror_name,
                "type": mirror_data.get('type'),
                "url": mirror_data.get('url'),
                "enabled": mirror_data.get('enabled')
            }
        })

    def api_delete_mirror(self, handler, mirror_name):
        """删除加速源"""
        # 从配置文件删除
        try:
            import os
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            # 优先使用 settings.json
            settings_path = os.path.join(project_root, 'settings.json')
            config_path = settings_path
            if not os.path.exists(config_path):
                config_path = os.path.join(project_root, 'config.json')

            if not os.path.exists(config_path):
                handler.send_json_response({
                    "success": False,
                    "error": "Config file not found"
                }, 404)
                return

            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            if 'mirrors' not in config_data or mirror_name not in config_data['mirrors']:
                handler.send_json_response({
                    "success": False,
                    "error": f"Mirror '{mirror_name}' not found"
                }, 404)
                return

            # 删除镜像
            del config_data['mirrors'][mirror_name]

            # 保存配置
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            handler.send_json_response({
                "success": False,
                "error": f"Failed to delete mirror: {str(e)}"
            }, 500)
            return

        handler.send_json_response({
            "success": True,
            "message": f"Mirror '{mirror_name}' deleted successfully"
        })

    # ==================== 用户管理 API ====================

    def api_login(self, handler):
        """用户登录"""
        try:
            # 获取配置和数据库
            config = handler.config if hasattr(handler, 'config') else {}
            db = getattr(handler, 'db', None) or (hasattr(handler, 'config') and handler.config.get('_db_instance'))

            # 读取请求体
            content_length = int(handler.headers.get('Content-Length', 0))
            if content_length == 0:
                handler.send_json_response({"success": False, "error": "请求体不能为空"}, 400)
                return

            body = handler.rfile.read(content_length).decode('utf-8')
            import json
            data = json.loads(body)
            username = data.get('username', '')
            password = data.get('password', '')

            if not username or not password:
                handler.send_json_response({"success": False, "error": "用户名和密码不能为空"}, 400)
                return

            # 获取客户端IP
            client_ip = None
            try:
                client_ip = handler.client_address[0]
            except Exception:
                pass

            # 验证凭据
            config_user = config.get('auth_user', '')
            config_pass = config.get('auth_pass', '')

            # 优先验证数据库中的用户（如果存在）
            if db:
                user = db.get_user(username)
                if user and db.verify_password(password, user['password_hash']):
                    # 数据库验证成功
                    token = config.get('auth_token')
                    if not token:
                        import secrets
                        token = secrets.token_hex(32)

                    if db:
                        db.add_login_log(username, client_ip, 'success', '登录成功（数据库）')

                    handler.send_json_response({
                        "success": True,
                        "token": token,
                        "username": username,
                        "level": user.get('role', 'admin')
                    })
                    return

            # 只有当数据库中没有该用户时，才使用配置文件验证
            if not user and username == config_user and password == config_pass:
                # 验证成功，返回 token
                # 优先使用配置的 auth_token，否则生成一个
                token = config.get('auth_token')
                if not token:
                    import secrets
                    token = secrets.token_hex(32)

                # 记录登录日志
                if db:
                    db.add_login_log(username, client_ip, 'success', '登录成功')

                handler.send_json_response({
                    "success": True,
                    "token": token,
                    "username": username,
                    "level": "admin"
                })
            else:
                # 验证失败
                if db:
                    db.add_login_log(username, client_ip, 'failed', '密码错误')
                handler.send_json_response({"success": False, "error": "用户名或密码错误"}, 401)

        except json.JSONDecodeError:
            handler.send_json_response({"success": False, "error": "无效的 JSON"}, 400)
        except Exception as e:
            import traceback
            traceback.print_exc()
            handler.send_json_response({"success": False, "error": str(e)}, 500)

    def api_change_password(self, handler):
        """修改用户密码"""
        try:
            # 获取数据库实例
            db = getattr(handler, 'db', None) or (hasattr(handler, 'config') and handler.config.get('_db_instance'))
            config = handler.config if hasattr(handler, 'config') else {}

            if not db:
                handler.send_json_response({"success": False, "error": "数据库不可用"}, 500)
                return

            # 读取请求体
            content_length = int(handler.headers.get('Content-Length', 0))
            if content_length == 0:
                handler.send_json_response({"error": "请求体不能为空"}, 400)
                return

            body = handler.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            username = data.get('username')
            old_password = data.get('old_password')
            new_password = data.get('new_password')

            if not username or not new_password:
                handler.send_json_response({"error": "缺少必要参数"}, 400)
                return

            # 获取配置中的账号密码
            config_user = config.get('auth_user', '')
            config_pass = config.get('auth_pass', '')

            # 验证旧密码（优先验证数据库，没有则验证配置文件）
            if old_password:
                user = db.get_user(username)
                if user:
                    # 验证数据库密码
                    if not db.verify_password(old_password, user['password_hash']):
                        handler.send_json_response({"success": False, "error": "原密码错误"}, 400)
                        return
                elif username == config_user and old_password != config_pass:
                    # 数据库没有用户，验证配置文件
                    handler.send_json_response({"success": False, "error": "原密码错误"}, 400)
                    return

            # 使用 bcrypt 加密新密码
            new_hash = db.hash_password(new_password)

            # 更新数据库
            existing_user = db.get_user(username)
            if existing_user:
                success = db.update_password(username, new_hash)
            else:
                result = db.create_user(username, new_hash, 'admin')
                success = result.get('success', False)

            if success:
                handler.send_json_response({
                    "success": True,
                    "message": "密码修改成功（已存储到数据库）"
                })
            else:
                handler.send_json_response({"success": False, "error": "用户不存在"}, 404)

        except json.JSONDecodeError:
            handler.send_json_response({"error": "Invalid JSON format"}, 400)
        except Exception as e:
            handler.send_json_response({"error": str(e)}, 500)

    def api_get_login_logs(self, handler, query_params):
        """获取登录日志"""
        try:
            # 尝试从多个位置获取数据库实例
            db = None
            if hasattr(handler, 'db'):
                db = handler.db
            elif hasattr(handler, 'config') and handler.config:
                db = handler.config.get('_db_instance')

            if not db:
                handler.send_json_response({"success": False, "error": "数据库不可用，请确保数据库已启用"}, 500)
                return

            # 安全获取 limit 参数
            try:
                limit = int(query_params.get('limit', ['50'])[0])
            except (ValueError, TypeError):
                limit = 50

            logs = db.get_login_logs(limit=limit)

            handler.send_json_response({
                "success": True,
                "logs": logs,
                "count": len(logs)
            })
        except Exception as e:
            import traceback
            trace = traceback.format_exc()
            print(f"[ERROR] api_get_login_logs: {e}")
            print(trace)
            handler.send_json_response({"error": str(e)}, 500)

    def api_get_config(self, handler):
        """获取配置文件内容 (settings.json)"""
        try:
            import os
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            settings_path = os.path.join(project_root, 'settings.json')

            # 优先使用 settings.json，如果不存在则尝试 config.json
            config_path = settings_path
            if not os.path.exists(config_path):
                config_path = os.path.join(project_root, 'config.json')

            if not os.path.exists(config_path):
                handler.send_json_response({
                    "success": False,
                    "error": "Config file not found (settings.json or config.json)"
                }, 404)
                return

            with open(config_path, 'r', encoding='utf-8') as f:
                config_content = f.read()

            handler.send_json_response({
                "success": True,
                "config": config_content,
                "path": config_path,
                "filename": os.path.basename(config_path)
            })

        except Exception as e:
            handler.send_json_response({
                "success": False,
                "error": f"Failed to read config: {str(e)}"
            }, 500)

    def api_save_config(self, handler):
        """保存配置文件 (settings.json) - 只更新部分配置"""
        try:
            content_length = int(handler.headers.get('Content-Length', 0))
            if content_length > 0:
                config_content = handler.rfile.read(content_length).decode('utf-8')
            else:
                handler.send_json_response({
                    "success": False,
                    "error": "No config content provided"
                }, 400)
                return

            # 验证 JSON 格式
            try:
                updates = json.loads(config_content)
            except json.JSONDecodeError as e:
                handler.send_json_response({
                    "success": False,
                    "error": f"Invalid JSON format: {str(e)}"
                }, 400)
                return

            if not isinstance(updates, dict):
                handler.send_json_response({
                    "success": False,
                    "error": "Config must be a JSON object"
                }, 400)
                return

            # 读取现有配置
            import os
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            settings_path = os.path.join(project_root, 'settings.json')

            if not os.path.exists(settings_path):
                handler.send_json_response({
                    "success": False,
                    "error": "settings.json not found"
                }, 404)
                return

            # 加载现有配置
            from core.config import load_json_config
            current_config = load_json_config(settings_path) or {}

            # 使用 deep_merge 合并更新（只更新传入的字段）
            from core.config import deep_merge
            new_config = deep_merge(current_config, updates)

            # 备份现有配置
            backup_path = settings_path + '.bak'
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    backup_content = f.read()
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(backup_content)
            except Exception:
                pass

            # 保存合并后的配置
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(new_config, f, indent=4, ensure_ascii=False)

            handler.send_json_response({
                "success": True,
                "message": "Config updated successfully (partial update)",
                "path": settings_path,
                "updated_keys": list(updates.keys())
            })

        except Exception as e:
            handler.send_json_response({
                "success": False,
                "error": f"Failed to save config: {str(e)}"
            }, 500)

    def api_reload_config(self, handler):
        """重新加载配置文件（热更新）"""
        try:
            import os
            from core.config import load_json_config

            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            settings_path = os.path.join(project_root, 'settings.json')

            if not os.path.exists(settings_path):
                handler.send_json_response({
                    "success": False,
                    "error": "Config file not found"
                }, 404)
                return

            # 加载并验证配置
            new_config = load_json_config(settings_path)
            if new_config is None:
                handler.send_json_response({
                    "success": False,
                    "error": "Failed to load config"
                }, 500)
                return

            # 计算变更
            old_config = self.config.copy()
            changes = self._compute_config_changes(old_config, new_config)

            # 更新内存配置
            self.config.update(new_config)

            # 通知各模块配置变更
            change_notifications = []
            if 'enable_monitor' in changes.get('modified', []):
                change_notifications.append("Monitor settings changed")
            if 'enable_sync' in changes.get('modified', []):
                change_notifications.append("Sync settings changed")
            if 'mirrors' in changes.get('modified', []):
                change_notifications.append("Mirrors configuration changed")

            handler.send_json_response({
                "success": True,
                "message": "Configuration reloaded successfully",
                "changes": changes,
                "change_notifications": change_notifications,
                "timestamp": datetime.now().isoformat()
            })

        except Exception as e:
            handler.send_json_response({
                "success": False,
                "error": f"Failed to reload config: {str(e)}"
            }, 500)

    def _compute_config_changes(self, old: dict, new: dict) -> dict:
        """计算配置变更"""
        changes = {
            'added': [],
            'removed': [],
            'modified': []
        }

        old_keys = set(old.keys())
        new_keys = set(new.keys())

        for key in new_keys - old_keys:
            changes['added'].append(key)

        for key in old_keys - new_keys:
            changes['removed'].append(key)

        for key in old_keys & new_keys:
            if old[key] != new[key]:
                changes['modified'].append(key)

        return changes

    def api_get_config_changes(self, handler):
        """获取配置变更历史"""
        handler.send_json_response({
            "changes": [],
            "message": "Config change history tracking requires hot reload enabled"
        })

    # ==================== WebSocket/SSE 状态 API ====================

    def api_get_ws_clients(self, handler):
        """获取WebSocket客户端状态"""
        # 需要访问全局ws_manager
        handler.send_json_response({
            "ws_clients": 0,
            "sse_clients": 0
        })

    # ==================== Prometheus 指标 API ====================

    def api_get_metrics(self, handler):
        """获取 Prometheus 格式的指标"""
        from core.prometheus import PrometheusMetrics

        metrics = PrometheusMetrics(self.config)

        # 设置运行时间
        uptime = time.time() - self.config.get('start_time', time.time())
        metrics.set_uptime(uptime)

        # 从数据库获取统计
        if self.db_enabled and self.db:
            try:
                db_stats = self.db.get_stats()
                metrics.set_files(
                    db_stats.get('total_files', 0),
                    db_stats.get('total_size', 0)
                )
                metrics.set_db_stats(
                    db_stats.get('total_files', 0),
                    db_stats.get('total_sync_records', 0),
                    db_stats.get('total_cache_records', 0)
                )
            except Exception as e:
                pass

        # 从缓存获取统计
        if hasattr(handler, 'cache_manager') and handler.cache_manager:
            try:
                cache_stats = handler.cache_manager.get_stats()
                metrics.set_cache(
                    cache_stats.get('size', 0),
                    cache_stats.get('count', 0),
                    cache_stats.get('hits', 0),
                    cache_stats.get('misses', 0)
                )
            except Exception as e:
                pass

        # 从监控模块获取系统指标
        if hasattr(handler, 'monitor') and handler.monitor:
            try:
                monitor_stats = handler.monitor.get_realtime_stats()
                metrics.set_system(
                    cpu=monitor_stats.get('cpu', {}).get('percent', 0),
                    memory=monitor_stats.get('memory', {}).get('percent', 0),
                    disk=monitor_stats.get('disk', {}).get('percent', 0),
                    disk_free=monitor_stats.get('disk', {}).get('free', 0),
                    disk_total=monitor_stats.get('disk', {}).get('total', 0),
                    network_rx=monitor_stats.get('network', {}).get('rx', 0),
                    network_tx=monitor_stats.get('network', {}).get('tx', 0)
                )
            except Exception as e:
                pass

        # 从同步管理器获取镜像状态
        if hasattr(handler, 'sync_manager') and handler.sync_manager:
            mirrors = self.config.get('mirrors', {})
            for mirror_type, mirror_config in mirrors.items():
                if isinstance(mirror_config, dict):
                    enabled = mirror_config.get('enabled', True)
                    last_sync = 0
                    metrics.set_mirror_status(mirror_type, enabled, last_sync)

        # 生成 Prometheus 格式输出
        output = metrics.generate_metrics()

        handler.send_response(200)
        handler.send_header('Content-Type', 'text/plain; charset=utf-8')
        handler.send_header('Content-Length', str(len(output)))
        handler.end_headers()
        handler.wfile.write(output.encode('utf-8'))

    # ==================== 服务器信息 API ====================

    def api_get_server_info(self, handler):
        """获取服务器完整信息"""
        import psutil

        uptime_seconds = time.time() - self.config.get('start_time', time.time())
        uptime_str = self._format_uptime(uptime_seconds)

        handler.send_json_response({
            "name": self.config.get('server_name', 'HYC下载站'),
            "version": "2.2.0",
            "uptime_seconds": round(uptime_seconds, 2),
            "uptime_formatted": uptime_str,
            "api_version": "v2",
            "config": {
                "host": self.config.get('host'),
                "port": self.config.get('port'),
                "base_dir": self.config.get('base_dir'),
                "auth_type": self.config.get('auth_type'),
                "directory_listing": self.config.get('directory_listing'),
                "max_upload_size": self.config.get('max_upload_size')
            },
            "features": {
                "websocket": True,
                "sse": True,
                "sync": True,
                "mirrors": True,
                "cache": True,
                "monitor": True
            }
        })

    # ==================== 告警管理 API ====================

    def api_get_alerts(self, handler, query_params):
        """获取告警列表"""
        try:
            from core.alerts import AlertManager

            alert_manager = AlertManager(self.config.get('alerts', {}))

            # 解析查询参数
            limit = int(query_params.get('limit', [50])[0])
            acknowledged = query_params.get('acknowledged', [None])[0]
            severity = query_params.get('severity', [None])[0]

            if acknowledged is not None:
                acknowledged = acknowledged.lower() == 'true'

            alerts = alert_manager.get_alerts(
                acknowledged=acknowledged,
                severity=severity,
                limit=limit
            )

            stats = alert_manager.get_stats()

            handler.send_json_response({
                'alerts': alerts,
                'count': len(alerts),
                'stats': stats
            })

        except Exception as e:
            handler.send_json_response({
                'error': str(e)
            }, 500)

    def api_acknowledge_alert(self, handler, alert_id):
        """确认告警"""
        try:
            from core.alerts import AlertManager

            alert_manager = AlertManager(self.config.get('alerts', {}))
            success = alert_manager.acknowledge_alert(alert_id)

            handler.send_json_response({
                'success': success,
                'message': f"Alert {alert_id} acknowledged" if success else "Alert not found"
            })

        except Exception as e:
            handler.send_json_response({
                'error': str(e)
            }, 500)

    def api_clear_alerts(self, handler):
        """清除告警历史"""
        try:
            from core.alerts import AlertManager

            alert_manager = AlertManager(self.config.get('alerts', {}))
            success = alert_manager.clear_history()

            handler.send_json_response({
                'success': success,
                'message': 'Alert history cleared'
            })

        except Exception as e:
            handler.send_json_response({
                'error': str(e)
            }, 500)

    def api_test_alert(self, handler):
        """测试告警发送"""
        try:
            from core.alerts import AlertManager, Alert, AlertSeverity

            alert_manager = AlertManager(self.config.get('alerts', {}))

            # 创建测试告警
            test_alert = Alert(
                alert_type='test',
                severity=AlertSeverity.INFO,
                title='Test Alert',
                message='This is a test alert from HYC Mirror Server',
                details={'test': True, 'timestamp': datetime.now().isoformat()}
            )

            success = alert_manager.trigger_alert(test_alert)

            handler.send_json_response({
                'success': success,
                'message': 'Test alert sent successfully' if success else 'Failed to send test alert (check configuration)'
            })

        except Exception as e:
            handler.send_json_response({
                'error': str(e)
            }, 500)

    def api_get_alert_config(self, handler):
        """获取告警配置"""
        alerts_config = self.config.get('alerts', {})

        # 隐藏敏感信息
        config = {
            'enabled': alerts_config.get('enabled', False),
            'email': {
                'enabled': alerts_config.get('email', {}).get('enabled', False),
                'smtp_host': alerts_config.get('email', {}).get('smtp_host', ''),
                'smtp_port': alerts_config.get('email', {}).get('smtp_port', 587),
                'from_address': alerts_config.get('email', {}).get('from_address', ''),
                'to_addresses': alerts_config.get('email', {}).get('to_addresses', []),
                'use_tls': alerts_config.get('email', {}).get('use_tls', True)
            },
            'webhook': {
                'enabled': alerts_config.get('webhook', {}).get('enabled', False),
                'url': '***' if alerts_config.get('webhook', {}).get('url') else ''
            },
            'rules': alerts_config.get('rules', {})
        }

        handler.send_json_response(config)

    def api_save_alert_config(self, handler):
        """保存告警配置"""
        try:
            import os
            from core.alerts import AlertManager

            # 获取请求体
            content_length = int(handler.headers.get('Content-Length', 0))
            if content_length > 0:
                post_data = handler.rfile.read(content_length)
                try:
                    new_config = json.loads(post_data.decode('utf-8'))
                except json.JSONDecodeError as e:
                    handler.send_json_response({
                        'success': False,
                        'error': f"Invalid JSON format: {str(e)}"
                    }, 400)
                    return
            else:
                handler.send_json_response({
                    'success': False,
                    'error': "No configuration data provided"
                }, 400)
                return

            # 更新配置
            if 'alerts' not in self.config:
                self.config['alerts'] = {}

            # 更新告警配置
            if 'enabled' in new_config:
                self.config['alerts']['enabled'] = new_config['enabled']
            if 'email' in new_config:
                self.config['alerts']['email'] = new_config['email']
            if 'webhook' in new_config:
                self.config['alerts']['webhook'] = new_config['webhook']
            if 'rules' in new_config:
                self.config['alerts']['rules'] = new_config['rules']

            # 保存到文件
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            settings_path = os.path.join(project_root, 'settings.json')

            with open(settings_path, 'r', encoding='utf-8') as f:
                settings_data = json.load(f)

            settings_data['alerts'] = self.config['alerts']

            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings_data, f, ensure_ascii=False, indent=4)

            handler.send_json_response({
                'success': True,
                'message': 'Alert configuration saved successfully',
                'config': self.config.get('alerts', {})
            })

        except Exception as e:
            handler.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)

    # ==================== 平滑重启 API ====================

    def api_get_restart_status(self, handler):
        """获取重启状态"""
        from core.graceful_restart import GracefulRestartManager, ServerState

        restart_manager = GracefulRestartManager(self.config.get('restart', {}))
        stats = restart_manager.get_stats()

        handler.send_json_response({
            'state': stats['state'],
            'pending_requests': stats['pending_requests'],
            'graceful_timeout': stats['graceful_timeout'],
            'recent_restarts': stats['recent_restarts']
        })

    def api_get_pending_requests(self, handler):
        """获取待处理请求"""
        from core.graceful_restart import GracefulRestartManager

        restart_manager = GracefulRestartManager(self.config.get('restart', {}))
        pending = restart_manager.get_pending_requests()

        handler.send_json_response({
            'count': len(pending),
            'requests': pending
        })

    def api_graceful_restart(self, handler, query_params):
        """执行优雅重启"""
        from core.graceful_restart import GracefulRestartManager, RestartStrategy

        # 解析策略参数
        strategy_param = query_params.get('strategy', ['graceful'])[0]
        try:
            strategy = RestartStrategy(strategy_param)
        except ValueError:
            strategy = RestartStrategy.GRACEFUL

        restart_manager = GracefulRestartManager(self.config.get('restart', {}))

        # 准备重启
        prepare_result = restart_manager.prepare_restart()
        if not prepare_result['success']:
            handler.send_json_response({
                'success': False,
                'error': prepare_result['message']
            }, 500)
            return

        # 返回待处理请求信息，让客户端决定是否继续
        pending_count = prepare_result['pending_requests']

        handler.send_json_response({
            'success': True,
            'pending_requests': pending_count,
            'message': f'Ready to restart with {pending_count} pending requests',
            'strategy': strategy.value,
            'graceful_timeout': restart_manager.graceful_timeout,
            'continue_url': '/api/v2/server/restart/confirm'
        })

    def api_confirm_restart(self, handler):
        """确认执行重启"""
        from core.graceful_restart import GracefulRestartManager, RestartStrategy

        try:
            content_length = int(handler.headers.get('Content-Length', 0))
            if content_length > 0:
                post_data = json.loads(handler.rfile.read(content_length))
                strategy = post_data.get('strategy', 'graceful')
            else:
                strategy = 'graceful'

            try:
                restart_strategy = RestartStrategy(strategy)
            except ValueError:
                restart_strategy = RestartStrategy.GRACEFUL

        except json.JSONDecodeError:
            restart_strategy = RestartStrategy.GRACEFUL

        restart_manager = GracefulRestartManager(self.config.get('restart', {}))

        # 执行重启
        result = restart_manager.perform_restart(strategy=restart_strategy)

        handler.send_json_response(result)

    def api_immediate_restart(self, handler):
        """立即重启服务器"""
        from core.graceful_restart import GracefulRestartManager

        restart_manager = GracefulRestartManager(self.config.get('restart', {}))

        # 获取脚本路径
        script_path = self.config.get('main_script', 'main.py')

        result = restart_manager.perform_restart(
            strategy='immediate',
            script_path=script_path
        )

        handler.send_json_response(result)

    def api_get_restart_history(self, handler):
        """获取重启历史"""
        from core.graceful_restart import GracefulRestartManager

        restart_manager = GracefulRestartManager(self.config.get('restart', {}))
        history = restart_manager.get_restart_history()

        handler.send_json_response({
            'count': len(history),
            'history': history
        })

    def api_get_restart_config(self, handler):
        """获取重启配置"""
        restart_config = self.config.get('restart', {})

        handler.send_json_response({
            'graceful_timeout': restart_config.get('graceful_timeout', 30),
            'shutdown_timeout': restart_config.get('shutdown_timeout', 10),
            'enabled': True
        })

    def api_update_restart_config(self, handler):
        """更新重启配置"""
        try:
            content_length = int(handler.headers.get('Content-Length', 0))
            if content_length == 0:
                handler.send_json_response({
                    'success': False,
                    'error': 'No configuration data provided'
                }, 400)
                return

            new_config = json.loads(handler.rfile.read(content_length))

            # 更新内存配置
            if 'restart' not in self.config:
                self.config['restart'] = {}

            if 'graceful_timeout' in new_config:
                self.config['restart']['graceful_timeout'] = new_config['graceful_timeout']
            if 'shutdown_timeout' in new_config:
                self.config['restart']['shutdown_timeout'] = new_config['shutdown_timeout']

            # 保存到文件
            import os
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            settings_path = os.path.join(project_root, 'settings.json')

            with open(settings_path, 'r', encoding='utf-8') as f:
                settings_data = json.load(f)

            if 'restart' not in settings_data:
                settings_data['restart'] = {}
            settings_data['restart'] = {**settings_data.get('restart', {}), **new_config}

            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings_data, f, ensure_ascii=False, indent=4)

            handler.send_json_response({
                'success': True,
                'message': 'Restart configuration updated',
                'config': self.config.get('restart', {})
            })

        except json.JSONDecodeError as e:
            handler.send_json_response({
                'success': False,
                'error': f'Invalid JSON format: {str(e)}'
            }, 400)
        except Exception as e:
            handler.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)

    def _format_uptime(self, seconds: float) -> str:
        """格式化运行时间"""
        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            return f"{minutes}分钟"
        elif seconds < 86400:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}小时{minutes}分钟"
        else:
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            return f"{days}天{hours}小时"

    # ==================== 缓存预热 API ====================

    def api_get_prewarm_status(self, handler):
        """获取缓存预热状态"""
        from core.cache_prewarm import CachePrewarmer

        prewarmer = CachePrewarmer(self.config.get('cache_prewarm', {}))
        status = prewarmer.get_status()

        handler.send_json_response(status)

    def api_get_prewarm_stats(self, handler):
        """获取缓存预热统计"""
        from core.cache_prewarm import CachePrewarmer

        prewarmer = CachePrewarmer(self.config.get('cache_prewarm', {}))
        stats = prewarmer.get_stats()

        handler.send_json_response(stats)

    def api_get_prewarm_items(self, handler, query_params):
        """获取预热项目列表"""
        from core.cache_prewarm import CachePrewarmer

        # 解析查询参数
        status = query_params.get('status', [None])[0]
        mirror_type = query_params.get('mirror_type', [None])[0]
        limit = int(query_params.get('limit', [50])[0])

        prewarmer = CachePrewarmer(self.config.get('cache_prewarm', {}))
        items = prewarmer.get_items(status=status, mirror_type=mirror_type, limit=limit)

        handler.send_json_response({
            'count': len(items),
            'items': items
        })

    def api_get_prewarm_history(self, handler):
        """获取预热历史"""
        from core.cache_prewarm import CachePrewarmer

        prewarmer = CachePrewarmer(self.config.get('cache_prewarm', {}))
        history = prewarmer.get_history()

        handler.send_json_response({
            'count': len(history),
            'history': history
        })

    def api_run_prewarm(self, handler, query_params):
        """执行缓存预热"""
        from core.cache_prewarm import CachePrewarmer

        # 解析参数
        mirror_type = query_params.get('mirror_type', [None])[0]
        limit = int(query_params.get('limit', [50])[0])
        priority = query_params.get('priority', ['medium'])[0]

        prewarmer = CachePrewarmer(self.config.get('cache_prewarm', {}))

        # 如果指定了镜像类型，只预热该类型
        targets = None
        if mirror_type:
            targets = []
            from core.cache_prewarm import PrewarmTarget
            targets.append(PrewarmTarget(
                mirror_type=mirror_type,
                priority=priority,
                limit=limit
            ))

        result = prewarmer.run(targets=targets)

        handler.send_json_response(result)

    def api_add_prewarm_items(self, handler):
        """添加预热项目"""
        try:
            content_length = int(handler.headers.get('Content-Length', 0))
            if content_length == 0:
                handler.send_json_response({
                    'success': False,
                    'error': 'No data provided'
                }, 400)
                return

            data = json.loads(handler.rfile.read(content_length))

            mirror_type = data.get('mirror_type')
            items = data.get('items', [])
            priority = data.get('priority', 'medium')

            if not mirror_type or not items:
                handler.send_json_response({
                    'success': False,
                    'error': 'mirror_type and items are required'
                }, 400)
                return

            from core.cache_prewarm import CachePrewarmer

            prewarmer = CachePrewarmer(self.config.get('cache_prewarm', {}))
            prewarmer.add_items_batch(mirror_type, items, priority)

            handler.send_json_response({
                'success': True,
                'message': f'Added {len(items)} items to prewarm queue',
                'mirror_type': mirror_type,
                'count': len(items)
            })

        except json.JSONDecodeError as e:
            handler.send_json_response({
                'success': False,
                'error': f'Invalid JSON format: {str(e)}'
            }, 400)
        except Exception as e:
            handler.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)

    def api_add_popular_items(self, handler, query_params):
        """添加流行项目到预热队列"""
        from core.cache_prewarm import CachePrewarmer

        mirror_type = query_params.get('mirror_type', [None])[0]
        limit = int(query_params.get('limit', [20])[0])
        priority = query_params.get('priority', ['medium'])[0]

        if not mirror_type:
            handler.send_json_response({
                'success': False,
                'error': 'mirror_type is required'
            }, 400)
            return

        prewarmer = CachePrewarmer(self.config.get('cache_prewarm', {}))
        popular = prewarmer.get_popular_items(mirror_type)

        if limit:
            popular = popular[:limit]

        prewarmer.add_popular_items_to_queue(mirror_type, limit, priority)

        handler.send_json_response({
            'success': True,
            'message': f'Added {len(popular)} popular items',
            'mirror_type': mirror_type,
            'count': len(popular),
            'items': popular
        })

    def api_get_popular_items(self, handler, query_params):
        """获取流行项目列表"""
        from core.cache_prewarm import CachePrewarmer

        mirror_type = query_params.get('mirror_type', [None])[0]

        prewarmer = CachePrewarmer(self.config.get('cache_prewarm', {}))

        if mirror_type:
            items = prewarmer.get_popular_items(mirror_type)
            handler.send_json_response({
                'mirror_type': mirror_type,
                'count': len(items),
                'items': items
            })
        else:
            all_popular = prewarmer._popular_items
            handler.send_json_response({
                'mirror_types': list(all_popular.keys()),
                'total_types': len(all_popular)
            })

    def api_clear_prewarm_queue(self, handler):
        """清空预热队列"""
        from core.cache_prewarm import CachePrewarmer

        prewarmer = CachePrewarmer(self.config.get('cache_prewarm', {}))
        prewarmer.clear_items()

        handler.send_json_response({
            'success': True,
            'message': 'Prewarm queue cleared'
        })

    def api_get_prewarm_config(self, handler):
        """获取缓存预热配置"""
        prewarm_config = self.config.get('cache_prewarm', {})

        handler.send_json_response({
            'enabled': prewarm_config.get('enabled', False),
            'schedule': prewarm_config.get('schedule', '0 3 * * *'),
            'batch_size': prewarm_config.get('batch_size', 10),
            'targets': prewarm_config.get('targets', [])
        })

    def api_save_prewarm_config(self, handler):
        """保存缓存预热配置"""
        try:
            content_length = int(handler.headers.get('Content-Length', 0))
            if content_length == 0:
                handler.send_json_response({
                    'success': False,
                    'error': 'No configuration data provided'
                }, 400)
                return

            new_config = json.loads(handler.rfile.read(content_length))

            # 更新内存配置
            if 'cache_prewarm' not in self.config:
                self.config['cache_prewarm'] = {}

            if 'enabled' in new_config:
                self.config['cache_prewarm']['enabled'] = new_config['enabled']
            if 'schedule' in new_config:
                self.config['cache_prewarm']['schedule'] = new_config['schedule']
            if 'batch_size' in new_config:
                self.config['cache_prewarm']['batch_size'] = new_config['batch_size']
            if 'targets' in new_config:
                self.config['cache_prewarm']['targets'] = new_config['targets']

            # 保存到文件
            import os
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            settings_path = os.path.join(project_root, 'settings.json')

            with open(settings_path, 'r', encoding='utf-8') as f:
                settings_data = json.load(f)

            if 'cache_prewarm' not in settings_data:
                settings_data['cache_prewarm'] = {}
            settings_data['cache_prewarm'] = {**settings_data.get('cache_prewarm', {}), **new_config}

            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings_data, f, ensure_ascii=False, indent=4)

            handler.send_json_response({
                'success': True,
                'message': 'Cache prewarm configuration saved',
                'config': self.config.get('cache_prewarm', {})
            })

        except json.JSONDecodeError as e:
            handler.send_json_response({
                'success': False,
                'error': f'Invalid JSON format: {str(e)}'
            }, 400)
        except Exception as e:
            handler.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)

    # ==================== API 文档 ====================

    def api_get_api_docs(self, handler, format: str = 'json'):
        """获取 API 文档"""
        from core.api_docs import generate_api_docs

        docs = generate_api_docs(self.config)

        if format == 'yaml':
            try:
                import yaml
                content = yaml.dump(docs, default_flow_style=False, allow_unicode=True)
                handler.send_response(200)
                handler.send_header('Content-Type', 'text/yaml')
                handler.send_header('Content-Length', len(content.encode('utf-8')))
                handler.end_headers()
                handler.wfile.write(content.encode('utf-8'))
                return
            except ImportError:
                format = 'json'

        content = json.dumps(docs, ensure_ascii=False, indent=2)
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Content-Length', len(content.encode('utf-8')))
        handler.send_header('Access-Control-Allow-Origin', '*')
        handler.end_headers()
        handler.wfile.write(content.encode('utf-8'))

    def api_generate_api_docs(self, handler):
        """生成并保存 API 文档"""
        try:
            from core.api_docs import save_api_docs

            # 获取保存路径
            content_length = int(handler.headers.get('Content-Length', 0))
            if content_length > 0:
                data = json.loads(handler.rfile.read(content_length))
                filepath = data.get('filepath', 'docs/api-docs.json')
                format = data.get('format', 'json')
            else:
                filepath = 'docs/api-docs.json'
                format = 'json'

            # 生成并保存文档
            saved_path = save_api_docs(self.config, filepath, format)

            handler.send_json_response({
                'success': True,
                'message': f'API documentation generated',
                'path': saved_path,
                'format': format
            })

        except Exception as e:
            handler.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
