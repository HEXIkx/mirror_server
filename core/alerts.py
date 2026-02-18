#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
告警模块
支持邮件告警、Webhook 告警、告警规则引擎
"""

import os
import sys
import json
import time
import threading
import logging
import smtplib
import requests
from datetime import datetime
from typing import Dict, List, Optional, Callable
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from enum import Enum

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(Enum):
    """告警类型"""
    DISK_HIGH = "disk_high"
    DISK_CRITICAL = "disk_critical"
    SYNC_FAILED = "sync_failed"
    SOURCE_UNHEALTHY = "source_unhealthy"
    CACHE_FULL = "cache_full"
    SERVICE_DOWN = "service_down"
    CUSTOM = "custom"


class Alert:
    """告警对象"""

    def __init__(
        self,
        alert_type: str,
        severity: AlertSeverity,
        title: str,
        message: str,
        details: Dict = None,
        source: str = None
    ):
        self.id = f"{int(time.time())}_{threading.get_ident()}"
        self.type = alert_type
        self.severity = severity
        self.title = title
        self.message = message
        self.details = details or {}
        self.source = source
        self.timestamp = datetime.now()
        self.sent = False
        self.acknowledged = False

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'id': self.id,
            'type': self.type,
            'severity': self.severity.value,
            'title': self.title,
            'message': self.message,
            'details': self.details,
            'source': self.source,
            'timestamp': self.timestamp.isoformat(),
            'sent': self.sent,
            'acknowledged': self.acknowledged
        }


class EmailAlerter:
    """邮件告警器"""

    def __init__(self, config: Dict = None):
        """
        初始化邮件告警器

        Args:
            config: 邮件配置
        """
        self.config = config or {}
        self.enabled = self.config.get('enabled', False)
        self.smtp_host = self.config.get('smtp_host', 'localhost')
        self.smtp_port = self.config.get('smtp_port', 587)
        self.smtp_user = self.config.get('smtp_user', '')
        self.smtp_password = self.config.get('smtp_password', '')
        self.from_address = self.config.get('from_address', 'hyc-mirror@localhost')
        self.to_addresses = self.config.get('to_addresses', [])
        self.use_tls = self.config.get('use_tls', True)

        # 连接池
        self._connection: Optional[smtplib.SMTP] = None
        self._last_connect_time: Optional[datetime] = None
        self._connection_timeout = 30

    def _get_connection(self) -> smtplib.SMTP:
        """获取 SMTP 连接"""
        if self._connection:
            # 检查连接是否仍然有效
            try:
                self._connection.noop()
                return self._connection
            except Exception:
                try:
                    self._connection.quit()
                except Exception:
                    pass
                self._connection = None

        # 创建新连接
        try:
            self._connection = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self._connection_timeout)
            if self.use_tls:
                self._connection.starttls()
            if self.smtp_user and self.smtp_password:
                self._connection.login(self.smtp_user, self.smtp_password)
            self._last_connect_time = datetime.now()
            return self._connection
        except Exception as e:
            logger.error(f"Failed to connect to SMTP server: {e}")
            raise

    def send(self, alert: Alert) -> bool:
        """
        发送告警邮件

        Args:
            alert: 告警对象

        Returns:
            是否发送成功
        """
        if not self.enabled:
            logger.debug("Email alerts disabled")
            return False

        if not self.to_addresses:
            logger.warning("No recipients configured for email alerts")
            return False

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[{alert.severity.value.upper()}] {alert.title}"
            msg['From'] = self.from_address
            msg['To'] = ', '.join(self.to_addresses)

            # HTML 格式
            html_content = self._format_html(alert)
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))

            # 纯文本格式
            text_content = self._format_text(alert)
            msg.attach(MIMEText(text_content, 'plain', 'utf-8'))

            # 发送邮件
            server = self._get_connection()
            server.send_message(msg)
            logger.info(f"Alert email sent: {alert.title}")
            return True

        except Exception as e:
            logger.error(f"Failed to send alert email: {e}")
            return False

    def _format_html(self, alert: Alert) -> str:
        """格式化 HTML 内容"""
        severity_colors = {
            'info': '#2196F3',
            'warning': '#FF9800',
            'error': '#F44336',
            'critical': '#9C27B0'
        }
        color = severity_colors.get(alert.severity.value, '#666666')

        details_html = ''
        if alert.details:
            details_html = '<h3>Details</h3><table>'
            for key, value in alert.details.items():
                details_html += f'<tr><td><b>{key}:</b></td><td>{value}</td></tr>'
            details_html += '</table>'

        return f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: {color}; color: white; padding: 10px; }}
                .title {{ font-size: 24px; margin: 20px 0; }}
                .message {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                .details {{ margin-top: 20px; }}
                .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>HYC Mirror Alert</h1>
            </div>
            <div class="title">[{alert.severity.value.upper()}] {alert.title}</div>
            <div class="message">
                <p><b>Message:</b> {alert.message}</p>
                <p><b>Time:</b> {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p><b>Type:</b> {alert.type}</p>
                {details_html}
            </div>
            <div class="footer">
                <p>This is an automated alert from HYC Mirror Server</p>
            </div>
        </body>
        </html>
        """

    def _format_text(self, alert: Alert) -> str:
        """格式化纯文本内容"""
        details_text = ''
        if alert.details:
            details_text = '\nDetails:\n'
            for key, value in alert.details.items():
                details_text += f"  {key}: {value}\n"

        return f"""
HYC Mirror Alert
================

Severity: {alert.severity.value.upper()}
Title: {alert.title}
Message: {alert.message}
Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
Type: {alert.type}
{details_text}
---
This is an automated alert from HYC Mirror Server
"""

    def test_connection(self) -> Dict:
        """测试 SMTP 连接"""
        try:
            server = self._get_connection()
            return {
                'success': True,
                'message': 'SMTP connection successful'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'SMTP connection failed: {str(e)}'
            }

    def close(self):
        """关闭连接"""
        if self._connection:
            try:
                self._connection.quit()
            except Exception:
                pass
            self._connection = None


class WebhookAlerter:
    """Webhook 告警器"""

    def __init__(self, config: Dict = None):
        """
        初始化 Webhook 告警器

        Args:
            config: Webhook 配置
        """
        self.config = config or {}
        self.enabled = self.config.get('enabled', False)
        self.webhook_url = self.config.get('webhook_url', '')

    def send(self, alert: Alert) -> bool:
        """
        发送告警到 Webhook

        Args:
            alert: 告警对象

        Returns:
            是否发送成功
        """
        if not self.enabled:
            logger.debug("Webhook alerts disabled")
            return False

        if not self.webhook_url:
            logger.warning("No webhook URL configured")
            return False

        try:
            payload = {
                'event': 'alert',
                'alert': alert.to_dict(),
                'timestamp': datetime.now().isoformat()
            }

            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'HYC-Mirror-Alerts/1.0'
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                headers=headers,
                timeout=30
            )

            if response.status_code < 400:
                logger.info(f"Alert webhook sent: {alert.title}")
                return True
            else:
                logger.error(f"Webhook returned error: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")
            return False


class AlertManager:
    """告警管理器"""

    def __init__(self, config: Dict = None):
        """
        初始化告警管理器

        Args:
            config: 告警配置
        """
        self.config = config or {}
        self.enabled = self.config.get('enabled', False)

        # 初始化告警器
        self.email_alerter = EmailAlerter(self.config.get('email', {}))
        self.webhook_alerter = WebhookAlerter(self.config.get('webhook', {}))

        # 告警规则
        self.rules = self.config.get('rules', {})

        # 告警历史
        self._alerts: List[Alert] = []
        self._alerts_lock = threading.Lock()
        self._max_history = 100

        # 回调函数
        self._on_alert: Optional[Callable] = None
        self._on_ack: Optional[Callable] = None

        # 告警冷却（防止重复告警）
        self._alert_cooldowns: Dict[str, float] = {}
        self._default_cooldown = 300  # 5 分钟

    def set_alert_callback(self, callback: Callable):
        """设置告警回调"""
        self._on_alert = callback

    def set_ack_callback(self, callback: Callable):
        """设置确认回调"""
        self._on_ack = callback

    def check_rule(self, rule_name: str, data: Dict) -> Optional[Alert]:
        """
        检查规则并生成告警

        Args:
            rule_name: 规则名称
            data: 检查数据

        Returns:
            告警对象或 None
        """
        if not self.enabled:
            return None

        rule = self.rules.get(rule_name, {})
        if not rule.get('enabled', False):
            return None

        severity = AlertSeverity(rule.get('severity', 'warning'))
        threshold = rule.get('threshold')

        # 磁盘空间检查
        if rule_name == 'disk_high' and threshold:
            disk_percent = data.get('disk_percent', 0)
            if disk_percent >= threshold:
                return Alert(
                    alert_type=AlertType.DISK_HIGH.value,
                    severity=severity,
                    title=f"Disk usage is high: {disk_percent}%",
                    message=f"Disk usage has reached {disk_percent}%, which is above the {threshold}% threshold.",
                    details={'disk_percent': disk_percent, 'threshold': threshold},
                    source='monitor'
                )

        if rule_name == 'disk_critical' and threshold:
            disk_percent = data.get('disk_percent', 0)
            if disk_percent >= threshold:
                return Alert(
                    alert_type=AlertType.DISK_CRITICAL.value,
                    severity=severity,
                    title=f"Disk usage is critical: {disk_percent}%",
                    message=f"Disk usage has reached {disk_percent}%, which is above the {critical_threshold}% threshold. Immediate action required!",
                    details={'disk_percent': disk_percent, 'threshold': threshold},
                    source='monitor'
                )

        # 同步失败检查
        if rule_name == 'sync_failed':
            sync_result = data.get('sync_result')
            if sync_result and not sync_result.get('success', True):
                return Alert(
                    alert_type=AlertType.SYNC_FAILED.value,
                    severity=severity,
                    title=f"Sync failed: {sync_result.get('source', 'unknown')}",
                    message=sync_result.get('error', 'Unknown sync error'),
                    details=sync_result,
                    source='sync'
                )

        # 源不健康检查
        if rule_name == 'source_unhealthy':
            unhealthy_sources = data.get('unhealthy_sources', [])
            if unhealthy_sources:
                return Alert(
                    alert_type=AlertType.SOURCE_UNHEALTHY.value,
                    severity=severity,
                    title=f"Unhealthy mirror sources detected: {len(unhealthy_sources)}",
                    message=f"The following mirror sources are unhealthy: {', '.join(unhealthy_sources)}",
                    details={'unhealthy_sources': unhealthy_sources},
                    source='health_check'
                )

        return None

    def trigger_alert(self, alert: Alert) -> bool:
        """
        触发告警

        Args:
            alert: 告警对象

        Returns:
            是否发送成功
        """
        if not self.enabled:
            return False

        # 检查冷却时间
        cooldown_key = f"{alert.type}:{alert.source or 'unknown'}"
        last_alert = self._alert_cooldowns.get(cooldown_key, 0)
        if time.time() - last_alert < self._default_cooldown:
            logger.debug(f"Alert {alert.type} in cooldown, skipping")
            return False

        # 发送告警
        email_sent = self.email_alerter.send(alert)
        webhook_sent = self.webhook_alerter.send(alert)

        alert.sent = email_sent or webhook_sent

        # 记录告警
        with self._alerts_lock:
            self._alerts.append(alert)
            if len(self._alerts) > self._max_history:
                self._alerts = self._alerts[-self._max_history:]

        # 更新冷却时间
        self._alert_cooldowns[cooldown_key] = time.time()

        # 触发回调
        if self._on_alert and alert.sent:
            try:
                self._on_alert(alert)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

        return alert.sent

    def acknowledge_alert(self, alert_id: str) -> bool:
        """
        确认告警

        Args:
            alert_id: 告警 ID

        Returns:
            是否成功
        """
        with self._alerts_lock:
            for alert in self._alerts:
                if alert.id == alert_id:
                    alert.acknowledged = True
                    if self._on_ack:
                        try:
                            self._on_ack(alert)
                        except Exception as e:
                            logger.error(f"Ack callback failed: {e}")
                    return True
        return False

    def get_alerts(
        self,
        acknowledged: bool = None,
        severity: str = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        获取告警列表

        Args:
            acknowledged: 过滤已确认状态
            severity: 过滤级别
            limit: 返回数量限制

        Returns:
            告警列表
        """
        with self._alerts_lock:
            alerts = [a.to_dict() for a in self._alerts]

        # 过滤
        if acknowledged is not None:
            alerts = [a for a in alerts if a['acknowledged'] == acknowledged]

        if severity:
            alerts = [a for a in alerts if a['severity'] == severity]

        # 返回最近的告警
        return alerts[-limit:]

    def get_stats(self) -> Dict:
        """获取告警统计"""
        with self._alerts_lock:
            total = len(self._alerts)
            unack = sum(1 for a in self._alerts if not a['acknowledged'])
            by_severity = {}
            for a in self._alerts:
                by_severity[a['severity']] = by_severity.get(a['severity'], 0) + 1

        return {
            'total_alerts': total,
            'unacknowledged': unack,
            'by_severity': by_severity,
            'email_enabled': self.email_alerter.enabled,
            'webhook_enabled': self.webhook_alerter.enabled,
            'rules_enabled': sum(1 for r in self.rules.values() if r.get('enabled', False))
        }

    def clear_history(self) -> bool:
        """清除告警历史"""
        with self._alerts_lock:
            self._alerts = []
        return True

    def test_email(self, to_address: str) -> Dict:
        """测试邮件发送"""
        test_alert = Alert(
            alert_type=AlertType.CUSTOM.value,
            severity=AlertSeverity.INFO,
            title="Test Alert",
            message="This is a test alert from HYC Mirror Server",
            details={'test': True}
        )

        # 临时添加收件人
        original_recipients = self.email_alerter.to_addresses
        self.email_alerter.to_addresses = [to_address]

        success = self.email_alerter.send(test_alert)

        # 恢复收件人
        self.email_alerter.to_addresses = original_recipients

        return {
            'success': success,
            'message': 'Test email sent successfully' if success else 'Failed to send test email'
        }
