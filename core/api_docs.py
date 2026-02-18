#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
API 文档生成器
自动生成 OpenAPI/Swagger 格式的 API 文档
"""

import os
import sys
import json
import inspect
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


@dataclass
class APIDoc:
    """API 文档信息"""
    title: str = "HYC下载站 API"
    version: str = "2.2.0"
    description: str = "HYC镜像下载站 REST API 文档"
    servers: List[Dict] = field(default_factory=list)
    tags: List[Dict] = field(default_factory=list)
    paths: Dict = field(default_factory=dict)
    components: Dict = field(default_factory=dict)


class APIDocGenerator:
    """API 文档生成器"""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.api_doc = APIDoc()

        # 初始化组件
        self._init_components()

    def _init_components(self):
        """初始化文档组件"""
        self.api_doc.components = {
            'securitySchemes': {
                'BearerAuth': {
                    'type': 'http',
                    'scheme': 'bearer',
                    'bearerFormat': 'JWT',
                    'description': 'JWT token 认证'
                },
                'ApiKeyAuth': {
                    'type': 'apiKey',
                    'in': 'header',
                    'name': 'X-API-Key',
                    'description': 'API Key 认证'
                }
            },
            'schemas': {
                'Error': {
                    'type': 'object',
                    'properties': {
                        'error': {'type': 'string', 'description': '错误信息'},
                        'code': {'type': 'string', 'description': '错误代码'},
                        'message': {'type': 'string', 'description': '详细描述'}
                    }
                },
                'Success': {
                    'type': 'object',
                    'properties': {
                        'success': {'type': 'boolean'},
                        'message': {'type': 'string'},
                        'data': {'type': 'object'}
                    }
                },
                'HealthStatus': {
                    'type': 'object',
                    'properties': {
                        'status': {'type': 'string', 'enum': ['healthy', 'degraded', 'unhealthy']},
                        'components': {'type': 'object'},
                        'timestamp': {'type': 'string', 'format': 'date-time'}
                    }
                }
            }
        }

    def generate(self) -> Dict:
        """生成完整的 API 文档"""
        doc = {
            'openapi': '3.0.3',
            'info': {
                'title': self.api_doc.title,
                'version': self.api_doc.version,
                'description': self.api_doc.description,
                'contact': {
                    'name': 'HYC Mirror Support',
                    'email': 'support@hyc-mirror.example.com'
                },
                'license': {
                    'name': 'MIT',
                    'url': 'https://opensource.org/licenses/MIT'
                }
            },
            'servers': self.api_doc.servers,
            'tags': self.api_doc.tags,
            'paths': self.api_doc.paths,
            'components': self.api_doc.components
        }

        return doc

    def add_server(self, url: str, description: str = ''):
        """添加服务器"""
        self.api_doc.servers.append({
            'url': url,
            'description': description
        })

    def add_tag(self, name: str, description: str = ''):
        """添加标签"""
        self.api_doc.tags.append({
            'name': name,
            'description': description
        })

    def add_endpoint(
        self,
        method: str,
        path: str,
        summary: str,
        description: str = '',
        tags: List[str] = None,
        parameters: List[Dict] = None,
        requestBody: Dict = None,
        responses: Dict = None,
        security: List[Dict] = None,
        deprecated: bool = False
    ):
        """
        添加 API 端点

        Args:
            method: HTTP 方法 (GET, POST, PUT, DELETE, PATCH)
            path: API 路径
            summary: 简要描述
            description: 详细描述
            tags: 标签列表
            parameters: 参数列表
            requestBody: 请求体
            responses: 响应定义
            security: 安全要求
            deprecated: 是否废弃
        """
        if parameters is None:
            parameters = []
        if responses is None:
            responses = self._default_responses()
        if security is None:
            security = []

        # 转换路径参数
        path_params = self._extract_path_params(path)
        for param in path_params:
            parameters.append({
                'name': param,
                'in': 'path',
                'required': True,
                'schema': {'type': 'string'},
                'description': f'Path parameter: {param}'
            })

        # 转换查询参数
        query_params = self._extract_query_params(path)
        for param in query_params:
            parameters.append({
                'name': param,
                'in': 'query',
                'required': False,
                'schema': {'type': 'string'},
                'description': f'Query parameter: {param}'
            })

        # 构建路径
        clean_path = path.format(**{p: f'{{{p}}}' for p in path_params})
        if clean_path not in self.api_doc.paths:
            self.api_doc.paths[clean_path] = {}

        endpoint = {
            'summary': summary,
            'description': description,
            'tags': tags or [],
            'parameters': parameters,
            'responses': responses,
            'deprecated': deprecated
        }

        if security:
            endpoint['security'] = security

        if requestBody:
            endpoint['requestBody'] = requestBody

        self.api_doc.paths[clean_path][method.lower()] = endpoint

    def _default_responses(self) -> Dict:
        """获取默认响应"""
        return {
            '200': {
                'description': 'Successful response',
                'content': {
                    'application/json': {
                        'schema': {'type': 'object'}
                    }
                }
            },
            '400': {
                'description': 'Bad request',
                'content': {
                    'application/json': {
                        'schema': {'$ref': '#/components/schemas/Error'}
                    }
                }
            },
            '401': {
                'description': 'Unauthorized',
                'content': {
                    'application/json': {
                        'schema': {'$ref': '#/components/schemas/Error'}
                    }
                }
            },
            '403': {
                'description': 'Forbidden',
                'content': {
                    'application/json': {
                        'schema': {'$ref': '#/components/schemas/Error'}
                    }
                }
            },
            '404': {
                'description': 'Not found',
                'content': {
                    'application/json': {
                        'schema': {'$ref': '#/components/schemas/Error'}
                    }
                }
            },
            '500': {
                'description': 'Internal server error',
                'content': {
                    'application/json': {
                        'schema': {'$ref': '#/components/schemas/Error'}
                    }
                }
            }
        }

    def _extract_path_params(self, path: str) -> List[str]:
        """提取路径参数"""
        import re
        return re.findall(r'\{(\w+)\}', path)

    def _extract_query_params(self, path: str) -> List[str]:
        """提取查询参数"""
        import re
        return re.findall(r':(\w+)', path)

    def save(self, filepath: str, format: str = 'json'):
        """
        保存 API 文档

        Args:
            filepath: 保存路径
            format: 格式 (json, yaml)
        """
        doc = self.generate()

        if format == 'yaml':
            try:
                import yaml
                with open(filepath, 'w', encoding='utf-8') as f:
                    yaml.dump(doc, f, default_flow_style=False, allow_unicode=True)
            except ImportError:
                # 回退为 JSON
                format = 'json'

        if format == 'json':
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)

        return filepath


class APIEndpointRegistry:
    """API 端点注册表"""

    def __init__(self):
        self.endpoints: List[Dict] = []

    def register(self, method: str, path: str, handler_name: str, description: str = ''):
        """注册端点"""
        self.endpoints.append({
            'method': method.upper(),
            'path': path,
            'handler': handler_name,
            'description': description
        })

    def get_all(self) -> List[Dict]:
        """获取所有端点"""
        return self.endpoints

    def generate_docs(self) -> Dict:
        """生成文档"""
        generator = APIDocGenerator()

        for ep in self.endpoints:
            generator.add_endpoint(
                method=ep['method'],
                path=ep['path'],
                summary=ep['description'],
                description=ep['description']
            )

        return generator.generate()


def generate_api_docs(config: Dict = None) -> Dict:
    """
    生成完整的 API 文档

    Args:
        config: 服务器配置

    Returns:
        OpenAPI 格式的文档
    """
    generator = APIDocGenerator(config)

    # 设置服务器信息
    host = config.get('host', 'localhost')
    port = config.get('port', 8080)
    protocol = 'https' if config.get('ssl_cert') else 'http'
    generator.add_server(f'{protocol}://{host}:{port}', 'Production server')

    # 添加标签
    generator.add_tag('Server', '服务器信息')
    generator.add_tag('Monitoring', '监控与指标')
    generator.add_tag('Mirrors', '镜像源管理')
    generator.add_tag('Sync', '同步管理')
    generator.add_tag('Cache', '缓存管理')
    generator.add_tag('Health', '健康检查')
    generator.add_tag('Alerts', '告警管理')
    generator.add_tag('Webhooks', 'Webhook管理')
    generator.add_tag('Configuration', '配置管理')
    generator.add_tag('Authentication', '认证管理')

    # ========== 服务器信息端点 ==========
    generator.add_endpoint(
        'GET', '/api/v2/server/info',
        summary='获取服务器信息',
        description='返回服务器的详细信息，包括版本、运行时间、配置等',
        tags=['Server']
    )

    # ========== 监控端点 ==========
    generator.add_endpoint(
        'GET', '/api/v2/monitor/realtime',
        summary='获取实时监控数据',
        description='返回服务器的实时监控数据，包括 CPU、内存、磁盘使用情况',
        tags=['Monitoring']
    )

    generator.add_endpoint(
        'GET', '/api/v2/monitor/history',
        summary='获取历史监控数据',
        description='返回指定时间段内的历史监控数据',
        tags=['Monitoring'],
        parameters=[{
            'name': 'period',
            'in': 'query',
            'schema': {'type': 'string'},
            'description': '时间周期: 1h, 6h, 24h, 7d, 30d'
        }]
    )

    generator.add_endpoint(
        'GET', '/api/v2/metrics',
        summary='获取 Prometheus 指标',
        description='返回 Prometheus 格式的监控指标',
        tags=['Monitoring']
    )

    # ========== 镜像源端点 ==========
    generator.add_endpoint(
        'GET', '/api/v2/mirrors',
        summary='列出所有镜像加速源',
        description='返回所有可用的镜像加速源列表',
        tags=['Mirrors']
    )

    generator.add_endpoint(
        'GET', '/api/v2/mirrors/:name',
        summary='获取镜像源详情',
        description='返回指定镜像源的详细信息',
        tags=['Mirrors']
    )

    generator.add_endpoint(
        'POST', '/api/v2/mirrors',
        summary='添加自定义镜像源',
        description='添加新的自定义镜像加速源',
        tags=['Mirrors'],
        requestBody={
            'required': True,
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'name': {'type': 'string'},
                            'type': {'type': 'string'},
                            'url': {'type': 'string'},
                            'enabled': {'type': 'boolean'}
                        },
                        'required': ['name', 'url']
                    }
                }
            }
        }
    )

    generator.add_endpoint(
        'DELETE', '/api/v2/mirrors/:name',
        summary='删除自定义镜像源',
        description='删除指定的自定义镜像加速源',
        tags=['Mirrors']
    )

    generator.add_endpoint(
        'POST', '/api/v2/mirrors/:name/refresh',
        summary='刷新镜像源缓存',
        description='刷新指定镜像源的缓存数据',
        tags=['Mirrors']
    )

    # ========== 同步管理端点 ==========
    generator.add_endpoint(
        'GET', '/api/v2/sync/sources',
        summary='获取同步源列表',
        description='返回所有配置的同步源',
        tags=['Sync']
    )

    generator.add_endpoint(
        'POST', '/api/v2/sync/sources',
        summary='添加同步源',
        description='添加新的同步源配置',
        tags=['Sync'],
        requestBody={
            'required': True,
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'name': {'type': 'string'},
                            'type': {'type': 'string'},
                            'url': {'type': 'string'},
                            'schedule': {'type': 'string'}
                        }
                    }
                }
            }
        }
    )

    generator.add_endpoint(
        'POST', '/api/v2/sync/:source_name/start',
        summary='启动同步任务',
        description='启动指定源的同步任务',
        tags=['Sync']
    )

    generator.add_endpoint(
        'POST', '/api/v2/sync/:source_name/stop',
        summary='停止同步任务',
        description='停止指定源的同步任务',
        tags=['Sync']
    )

    generator.add_endpoint(
        'GET', '/api/v2/sync/:source_name/status',
        summary='获取同步状态',
        description='返回指定同步源的当前状态',
        tags=['Sync']
    )

    # ========== 缓存管理端点 ==========
    generator.add_endpoint(
        'GET', '/api/v2/cache/stats',
        summary='获取缓存统计',
        description='返回缓存的使用统计信息',
        tags=['Cache']
    )

    generator.add_endpoint(
        'GET', '/api/v2/cache/usage',
        summary='获取缓存使用详情',
        description='返回缓存的详细使用情况',
        tags=['Cache']
    )

    generator.add_endpoint(
        'POST', '/api/v2/cache/clean',
        summary='清理缓存',
        description='清理指定或全部缓存',
        tags=['Cache'],
        requestBody={
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'source': {'type': 'string'}
                        }
                    }
                }
            }
        }
    )

    # ========== 缓存预热端点 ==========
    generator.add_endpoint(
        'GET', '/api/v2/cache/prewarm',
        summary='获取预热状态',
        description='返回缓存预热的当前状态',
        tags=['Cache']
    )

    generator.add_endpoint(
        'POST', '/api/v2/cache/prewarm',
        summary='执行缓存预热',
        description='手动执行缓存预热任务',
        tags=['Cache']
    )

    generator.add_endpoint(
        'GET', '/api/v2/cache/prewarm/items',
        summary='获取预热项目列表',
        description='返回待预热的项目列表',
        tags=['Cache']
    )

    generator.add_endpoint(
        'POST', '/api/v2/cache/prewarm/clear',
        summary='清空预热队列',
        description='清空待预热的项目队列',
        tags=['Cache']
    )

    # ========== 健康检查端点 ==========
    generator.add_endpoint(
        'GET', '/api/v2/health',
        summary='获取健康状态',
        description='返回服务器的整体健康状态',
        tags=['Health']
    )

    generator.add_endpoint(
        'GET', '/api/v2/health/sources',
        summary='获取镜像源健康状态',
        description='返回所有镜像源的健康检查结果',
        tags=['Health']
    )

    generator.add_endpoint(
        'GET', '/api/v2/health/check/:source_name',
        summary='检查指定源健康',
        description='手动触发指定镜像源的健康检查',
        tags=['Health']
    )

    generator.add_endpoint(
        'GET', '/api/v2/health/failover',
        summary='获取故障切换状态',
        description='返回故障切换系统的当前状态',
        tags=['Health']
    )

    generator.add_endpoint(
        'POST', '/api/v2/health/failover/:mirror_type',
        summary='触发故障切换',
        description='手动触发指定镜像类型的故障切换',
        tags=['Health']
    )

    # ========== 告警管理端点 ==========
    generator.add_endpoint(
        'GET', '/api/v2/alerts',
        summary='获取告警列表',
        description='返回当前告警列表',
        tags=['Alerts'],
        parameters=[{
            'name': 'limit',
            'in': 'query',
            'schema': {'type': 'integer'},
            'description': '返回数量限制'
        }]
    )

    generator.add_endpoint(
        'POST', '/api/v2/alerts/:alert_id/acknowledge',
        summary='确认告警',
        description='确认指定告警',
        tags=['Alerts']
    )

    generator.add_endpoint(
        'POST', '/api/v2/alerts/clear',
        summary='清除告警历史',
        description='清除所有告警历史记录',
        tags=['Alerts']
    )

    generator.add_endpoint(
        'POST', '/api/v2/alerts/test',
        summary='测试告警发送',
        description='发送测试告警以验证配置',
        tags=['Alerts']
    )

    generator.add_endpoint(
        'GET', '/api/v2/alerts/config',
        summary='获取告警配置',
        description='返回当前的告警配置',
        tags=['Alerts']
    )

    generator.add_endpoint(
        'PUT', '/api/v2/alerts/config',
        summary='更新告警配置',
        description='更新告警配置（邮件、Webhook 等）',
        tags=['Alerts']
    )

    # ========== Webhook 端点 ==========
    generator.add_endpoint(
        'GET', '/api/v2/webhooks',
        summary='列出所有 Webhook',
        description='返回所有配置的 Webhook',
        tags=['Webhooks']
    )

    generator.add_endpoint(
        'POST', '/api/v2/webhooks',
        summary='创建 Webhook',
        description='创建新的 Webhook 配置',
        tags=['Webhooks']
    )

    generator.add_endpoint(
        'GET', '/api/v2/webhooks/:webhook_id',
        summary='获取 Webhook 详情',
        description='返回指定 Webhook 的详细信息',
        tags=['Webhooks']
    )

    generator.add_endpoint(
        'PUT', '/api/v2/webhooks/:webhook_id',
        summary='更新 Webhook',
        description='更新指定 Webhook 的配置',
        tags=['Webhooks']
    )

    generator.add_endpoint(
        'DELETE', '/api/v2/webhooks/:webhook_id',
        summary='删除 Webhook',
        description='删除指定的 Webhook',
        tags=['Webhooks']
    )

    generator.add_endpoint(
        'POST', '/api/v2/webhooks/:webhook_id/test',
        summary='测试 Webhook',
        description='发送测试请求到指定的 Webhook',
        tags=['Webhooks']
    )

    generator.add_endpoint(
        'GET', '/api/v2/webhooks/:webhook_id/deliveries',
        summary='获取 Webhook 交付历史',
        description='返回指定 Webhook 的交付历史记录',
        tags=['Webhooks']
    )

    generator.add_endpoint(
        'GET', '/api/v2/webhooks/:webhook_id/stats',
        summary='获取 Webhook 统计',
        description='返回指定 Webhook 的交付统计信息',
        tags=['Webhooks']
    )

    # ========== 配置管理端点 ==========
    generator.add_endpoint(
        'GET', '/api/v2/config',
        summary='获取配置',
        description='返回当前的服务器配置',
        tags=['Configuration']
    )

    generator.add_endpoint(
        'PUT', '/api/v2/config',
        summary='保存配置',
        description='保存配置到 settings.json',
        tags=['Configuration']
    )

    generator.add_endpoint(
        'POST', '/api/v2/config/reload',
        summary='重新加载配置',
        description='重新加载配置文件（热更新）',
        tags=['Configuration']
    )

    generator.add_endpoint(
        'GET', '/api/v2/config/changes',
        summary='获取配置变更历史',
        description='返回配置变更的历史记录',
        tags=['Configuration']
    )

    # ========== 重启管理端点 ==========
    generator.add_endpoint(
        'GET', '/api/v2/server/restart',
        summary='获取重启状态',
        description='返回服务器重启管理的当前状态',
        tags=['Server']
    )

    generator.add_endpoint(
        'POST', '/api/v2/server/restart',
        summary='准备重启',
        description='准备执行服务器重启',
        tags=['Server']
    )

    generator.add_endpoint(
        'POST', '/api/v2/server/restart/confirm',
        summary='确认执行重启',
        description='确认并执行服务器重启',
        tags=['Server']
    )

    generator.add_endpoint(
        'POST', '/api/v2/server/restart/immediate',
        summary='立即重启',
        description='立即重启服务器（不等待请求完成）',
        tags=['Server']
    )

    generator.add_endpoint(
        'GET', '/api/v2/server/restart/pending',
        summary='获取待处理请求',
        description='返回当前待处理的请求列表',
        tags=['Server']
    )

    generator.add_endpoint(
        'GET', '/api/v2/server/restart/history',
        summary='获取重启历史',
        description='返回服务器重启的历史记录',
        tags=['Server']
    )

    # ========== 认证端点 ==========
    generator.add_endpoint(
        'POST', '/api/v2/admin/auth/verify',
        summary='验证认证状态',
        description='验证当前请求的认证状态',
        tags=['Authentication']
    )

    return generator.generate()


def save_api_docs(config: Dict, filepath: str = None, format: str = 'json'):
    """
    生成并保存 API 文档

    Args:
        config: 服务器配置
        filepath: 保存路径
        format: 输出格式 (json, yaml)
    """
    doc = generate_api_docs(config)

    if filepath is None:
        # 默认保存到项目根目录
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        filepath = os.path.join(script_dir, 'docs', 'api-docs.json')

    # 确保目录存在
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    if format == 'yaml':
        try:
            import yaml
            with open(filepath, 'w', encoding='utf-8') as f:
                yaml.dump(doc, f, default_flow_style=False, allow_unicode=True)
        except ImportError:
            format = 'json'

    if format == 'json':
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

    return filepath
