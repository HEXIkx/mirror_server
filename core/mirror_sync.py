#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""镜像同步管理模块"""

import os
import json
import time
import ftplib
import shutil
# import importlib  # 未使用
from datetime import datetime
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor

try:
    import paramiko
except ImportError:
    paramiko = None


class MirrorSyncManager:
    """镜像同步管理器"""

    def __init__(self, config):
        self.config = config
        # 从settings.json加载同步源配置
        self.sync_sources = self._load_sync_sources()
        self.sync_threads = {}
        self.sync_status = {}
        self.sync_lock = Lock()
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers=3)

        # 定时同步调度器
        self.scheduler_thread = None
        self.scheduler_running = False

        # 加载同步状态
        self.sync_state_file = config.get('sync_state_file', 'sync_state.json')
        self.load_sync_state()

        # 合并状态和源
        for name in list(self.sync_sources.keys()):
            if name not in self.sync_status:
                self.sync_status[name] = {
                    'last_sync': None,
                    'status': 'stopped',
                    'files_synced': 0,
                    'total_files': 0,
                    'error': None,
                    'schedule': self.sync_sources[name].get('schedule', {}),
                    'next_sync': None
                }

        # 启动定时同步调度器
        self._start_scheduler()

    def _load_sync_sources(self):
        """加载同步源配置 - 从settings.json读取"""
        sources = self.config.get('sync_sources', {})
        if sources:
            print(f"[Sync] 从settings.json加载了 {len(sources)} 个同步源")
        return sources

    def _save_sync_sources(self):
        """保存同步源配置到settings.json"""
        try:
            # 读取现有settings.json
            settings_file = 'settings.json'
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)

                # 更新sync_sources
                settings['sync_sources'] = self.sync_sources

                # 写回settings.json
                with open(settings_file, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, ensure_ascii=False, indent=2)

                print(f"[Sync] 保存了 {len(self.sync_sources)} 个同步源到settings.json")

                # 更新内存中的配置
                self.config['sync_sources'] = self.sync_sources
        except Exception as e:
            print(f"保存同步源到settings.json失败: {e}")
    
    def load_sync_state(self):
        """加载同步状态"""
        try:
            if os.path.exists(self.sync_state_file):
                with open(self.sync_state_file, 'r', encoding='utf-8') as f:
                    self.sync_status = json.load(f)
        except Exception as e:
            print(f"加载同步状态失败: {e}")
            self.sync_status = {}
    
    def save_sync_state(self):
        """保存同步状态"""
        try:
            with open(self.sync_state_file, 'w', encoding='utf-8') as f:
                json.dump(self.sync_status, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存同步状态失败: {e}")

    def get_sync_history(self, limit=100):
        """获取同步历史记录

        Args:
            limit: 返回记录数量限制

        Returns:
            list: 同步历史记录列表
        """
        history = []

        # 从 sync_status 中提取历史记录
        with self.sync_lock:
            for name, status in self.sync_status.items():
                # 跳过临时同步任务
                if status.get('is_temp_sync'):
                    continue

                # 只记录已完成或错误的同步
                if status.get('status') in ('completed', 'error') and status.get('last_sync'):
                    history.append({
                        'source_name': name,
                        'status': status.get('status'),
                        'last_sync': status.get('last_sync'),
                        'files_synced': status.get('files_synced', 0),
                        'total_files': status.get('total_files', 0),
                        'error': status.get('error')
                    })

        # 按时间倒序排列
        history.sort(key=lambda x: x.get('last_sync', ''), reverse=True)

        return history[:limit]
    
    def add_sync_source(self, name, source_config):
        """添加同步源"""
        with self.sync_lock:
            self.sync_sources[name] = source_config
            self.sync_status[name] = {
                'last_sync': None,
                'status': 'stopped',
                'files_synced': 0,
                'total_files': 0,
                'error': None,
                'schedule': source_config.get('schedule', {}),  # 定时同步配置
                'next_sync': None  # 下次同步时间
            }
            self._calculate_next_sync(name)
            self.save_sync_state()
            self._save_sync_sources()

    def _calculate_next_sync(self, name):
        """计算下次同步时间"""
        try:
            import croniter
        except ImportError:
            print("[WARN] croniter not installed")
            return

        if name not in self.sync_status:
            return

        schedule = self.sync_status[name].get('schedule', {})
        if not schedule.get('enabled'):
            self.sync_status[name]['next_sync'] = None
            return

        cron_str = schedule.get('cron')
        if cron_str:
            try:
                cron = croniter.croniter(cron_str)
                self.sync_status[name]['next_sync'] = cron.get_next(datetime).isoformat()
            except Exception as e:
                print(f"[WARN] croniter error: {e}")
                self.sync_status[name]['next_sync'] = None

    def _start_scheduler(self):
        """启动定时同步调度器"""
        if self.scheduler_running:
            return
        self.scheduler_running = True
        self.scheduler_thread = Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()

    def _scheduler_loop(self):
        """定时同步调度循环"""
        while self.scheduler_running:
            try:
                now = datetime.now()
                with self.sync_lock:
                    for name, status in self.sync_status.items():
                        source = self.sync_sources.get(name, {})
                        schedule = status.get('schedule', {}) or source.get('schedule', {})
                        if not schedule.get('enabled'):
                            continue

                        next_sync = status.get('next_sync')
                        if next_sync:
                            next_time = datetime.fromisoformat(next_sync)
                            if now >= next_time:
                                # 触发同步
                                print(f"[定时同步] 触发同步: {name}")
                                self.start_sync(name)
                                # 计算下次同步时间
                                self._calculate_next_sync(name)
            except Exception as e:
                print(f"定时同步调度错误: {e}")
            time.sleep(60)  # 每分钟检查一次

    def stop_scheduler(self):
        """停止定时同步调度器"""
        self.scheduler_running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)

    def remove_sync_source(self, name):
        """移除同步源"""
        with self.sync_lock:
            if name in self.sync_sources:
                del self.sync_sources[name]
            if name in self.sync_status:
                del self.sync_status[name]
            if name in self.sync_threads:
                self.stop_sync(name)
            self.save_sync_state()
            self._save_sync_sources()
    
    def start_sync(self, name):
        """开始同步指定源"""
        if name not in self.sync_sources:
            return False

        if name in self.sync_threads and self.sync_threads[name].is_alive():
            return True  # 已经在运行

        # 设置运行标志，确保同步循环可以执行
        self.running = True

        with self.sync_lock:
            self.sync_status[name]['status'] = 'syncing'
            self.sync_status[name]['error'] = None

        thread = Thread(target=self._sync_worker, args=(name,), daemon=True)
        self.sync_threads[name] = thread
        thread.start()
        return True

    def sync_packages(self, source_name, packages):
        """临时单次同步指定源的特定包

        Args:
            source_name: 同步源名称（如 'pypi-mirrord'）
            packages: 包名列表（如 ['requests', 'numpy']）

        Returns:
            dict: 包含 success 状态和 task_id
        """
        if source_name not in self.sync_sources:
            return {"success": False, "error": f"同步源 '{source_name}' 不存在"}

        if not packages or not isinstance(packages, list):
            return {"success": False, "error": "请提供有效的包名列表"}

        # 生成临时任务ID
        import time
        task_id = f"temp_sync_{int(time.time())}"

        # 使用临时任务名进行同步
        temp_name = f"{source_name}_temp_{int(time.time())}"

        # 设置状态
        with self.sync_lock:
            self.sync_status[temp_name] = {
                'last_sync': time.strftime('%Y-%m-%dT%H:%M:%S'),
                'status': 'syncing',
                'files_synced': 0,
                'total_files': 0,
                'error': None,
                'schedule': {},
                'next_sync': None,
                'is_temp_sync': True,
                'source_name': source_name,
                'packages': packages
            }

        # 设置运行标志
        self.running = True

        # 在后台线程执行临时同步
        thread = Thread(
            target=self._sync_worker_temp,
            args=(temp_name, source_name, packages),
            daemon=True
        )
        self.sync_threads[temp_name] = thread
        thread.start()

        return {"success": True, "task_id": task_id, "source": source_name, "packages": packages}

    def _sync_worker_temp(self, temp_name, source_name, packages):
        """临时同步工作线程"""
        print(f"[Temp Sync] 开始临时同步: {source_name}, 包: {', '.join(packages[:3])}{'...' if len(packages) > 3 else ''}")

        config = self.sync_sources[source_name]
        try:
            self._sync_http(temp_name, config, specific_packages=packages)
            with self.sync_lock:
                if temp_name in self.sync_status:
                    self.sync_status[temp_name]['status'] = 'completed'
            print(f"[Temp Sync] 临时同步完成: {source_name}")
        except Exception as e:
            with self.sync_lock:
                if temp_name in self.sync_status:
                    self.sync_status[temp_name]['status'] = 'error'
                    self.sync_status[temp_name]['error'] = str(e)
            print(f"[Temp Sync] 临时同步失败: {e}")

    def stop_sync(self, name):
        """停止同步指定源 - 立即停止"""
        # 立即设置状态为停止
        with self.sync_lock:
            self.sync_status[name]['status'] = 'stopped'
        # 设置停止标志，让线程提前退出
        self.running = False
        # 立即返回，不等待线程结束
        if name in self.sync_threads:
            del self.sync_threads[name]
        # 短暂等待后重置运行标志
        import time
        time.sleep(0.5)
        self.running = True
    
    def start_all_sync(self):
        """开始所有同步源"""
        for name in self.sync_sources:
            self.start_sync(name)
    
    def stop_all_sync(self):
        """停止所有同步源"""
        for name in list(self.sync_threads.keys()):
            self.stop_sync(name)
    
    def _sync_worker(self, name):
        """同步工作线程"""
        print(f"[SYNC] 开始同步: {name}")
        source_config = self.sync_sources[name]
        sync_type = source_config.get('type', 'http')
        print(f"[SYNC] 类型: {sync_type}, URL: {source_config.get('url', 'N/A')}")

        try:
            if sync_type in ('http', 'https'):
                self._sync_http(name, source_config)
            elif sync_type == 'ftp':
                self._sync_ftp(name, source_config)
            elif sync_type == 'sftp':
                self._sync_sftp(name, source_config)
            elif sync_type == 'local':
                self._sync_local(name, source_config)
            # 新增同步类型
            elif sync_type == 'rsync':
                self._sync_rsync(name, source_config)
            elif sync_type == 'git':
                self._sync_git(name, source_config)
            elif sync_type == 'aws' or sync_type == 's3':
                self._sync_s3(name, source_config)
            elif sync_type == 'oss':
                self._sync_oss(name, source_config)
            elif sync_type == 'cos':
                self._sync_cos(name, source_config)
            elif sync_type == 'webdav':
                self._sync_webdav(name, source_config)
            elif sync_type == 'rsync':
                self._sync_rsync(name, source_config)
            else:
                raise ValueError(f"不支持的同步类型: {sync_type}")
            
            with self.sync_lock:
                self.sync_status[name]['status'] = 'completed'
                self.sync_status[name]['last_sync'] = datetime.now().isoformat()
        
        except Exception as e:
            with self.sync_lock:
                self.sync_status[name]['status'] = 'error'
                self.sync_status[name]['error'] = str(e)
        
        finally:
            self.save_sync_state()
    
    def _sync_http(self, name, config, specific_packages=None):
        """HTTP/HTTPS同步 - 完整版

        Args:
            name: 同步源名称
            config: 同步源配置
            specific_packages: 可选的特定包列表，用于临时单次同步
        """
        print(f"[HTTP Sync] 开始同步: {name}")
        target_dir = os.path.join(self.config['base_dir'], config.get('target', name))
        os.makedirs(target_dir, exist_ok=True)
        print(f"[HTTP Sync] 目标目录: {target_dir}")

        # 获取文件列表
        source_url = config.get('url', '')
        print(f"[HTTP Sync] 源URL: {source_url}")
        file_list = self._get_http_file_list(source_url, config, specific_packages)

        total_files = len(file_list)
        print(f"[HTTP Sync] 获取到 {total_files} 个文件")

        with self.sync_lock:
            self.sync_status[name]['total_files'] = total_files

        if total_files == 0:
            print(f"[HTTP Sync] 没有文件需要同步")
            return

        synced_count = 0
        failed_count = 0

        for i, file_info in enumerate(file_list):
            if not self.running:
                print(f"[HTTP Sync] 同步被中断")
                break

            # 更新进度
            with self.sync_lock:
                self.sync_status[name]['files_synced'] = synced_count

            # 获取本地路径
            filename = file_info.get('name', '')
            if not filename:
                continue

            # 处理子目录
            local_path = os.path.join(target_dir, filename)
            local_dir = os.path.dirname(local_path)
            if local_dir and not os.path.exists(local_dir):
                os.makedirs(local_dir, exist_ok=True)

            # 检查是否需要同步
            if self._need_sync_http(file_info, local_path):
                try:
                    if self._download_file_http(file_info['url'], local_path, config):
                        synced_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    print(f"[HTTP Sync] 下载失败 {filename}: {e}")
                    failed_count += 1

            # 每10个文件输出一次进度
            if (i + 1) % 10 == 0:
                print(f"[HTTP Sync] 进度: {i+1}/{total_files}, 已同步: {synced_count}")

        with self.sync_lock:
            self.sync_status[name]['files_synced'] = synced_count

        print(f"[HTTP Sync] 完成: 成功 {synced_count}, 失败 {failed_count}")
    
    def _sync_ftp(self, name, config):
        """FTP同步实现"""
        try:
            host = config['host']
            port = config.get('port', 21)
            username = config.get('username', 'anonymous')
            password = config.get('password', 'anonymous@')
            remote_path = config.get('remote_path', '/')
            target_dir = os.path.join(self.config['base_dir'], config.get('target', name))
            
            os.makedirs(target_dir, exist_ok=True)
            print(f"开始FTP同步 {name} -> {target_dir}")
            
            ftp = ftplib.FTP()
            ftp.connect(host, port)
            ftp.login(username, password)
            
            if remote_path:
                ftp.cwd(remote_path)
            
            file_list = []
            ftp.retrlines('LIST', file_list.append)
            
            remote_files = {}
            for line in file_list:
                parts = line.split()
                if len(parts) < 9:
                    continue
                filename = ' '.join(parts[8:])
                if filename in ['.', '..']:
                    continue
                is_dir = parts[0].startswith('d')
                size = int(parts[4]) if not is_dir else 0
                remote_files[filename] = {
                    'name': filename,
                    'size': size,
                    'is_dir': is_dir
                }
            
            synced_count = 0
            for filename, file_info in remote_files.items():
                if not self.running:
                    break
                local_path = os.path.join(target_dir, filename)
                if file_info['is_dir']:
                    sub_config = config.copy()
                    sub_config['remote_path'] = os.path.join(remote_path, filename).replace('\\', '/')
                    sub_config['target'] = os.path.join(config.get('target', name), filename)
                    self._sync_ftp(name + '/' + filename, sub_config)
                else:
                    if self._need_sync_ftp(ftp, filename, local_path, file_info):
                        if self._download_ftp_file(ftp, filename, local_path, file_info):
                            synced_count += 1

            with self.sync_lock:
                self.sync_status[name]['files_synced'] = synced_count
                self.sync_status[name]['total_files'] = len([f for f in remote_files.values() if not f['is_dir']])

        except Exception as e:
            # 确保连接被关闭
            try:
                ftp.quit()
            except Exception:
                pass
            raise Exception(f"FTP同步失败: {str(e)}")

        finally:
            try:
                ftp.quit()
            except Exception:
                pass
    
    def _sync_sftp(self, name, config):
        """SFTP同步实现"""
        if not paramiko:
            raise ImportError("paramiko未安装，无法使用SFTP同步")

        host = config['host']
        port = config.get('port', 22)
        username = config.get('username', 'anonymous')
        password = config.get('password')
        private_key = config.get('private_key')
        remote_path = config.get('remote_path', '/')
        target_dir = os.path.join(self.config['base_dir'], config.get('target', name))

        os.makedirs(target_dir, exist_ok=True)
        print(f"开始SFTP同步 {name} -> {target_dir}")

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {'hostname': host, 'port': port, 'username': username}
        if private_key:
            key = paramiko.RSAKey.from_private_key_file(private_key)
            connect_kwargs['pkey'] = key
        else:
            connect_kwargs['password'] = password

        ssh.connect(**connect_kwargs)
        sftp = ssh.open_sftp()

        try:
            synced_count = self._sync_sftp_directory(sftp, remote_path, target_dir, name)

            with self.sync_lock:
                self.sync_status[name]['files_synced'] = synced_count

        finally:
            try:
                sftp.close()
            except Exception:
                pass
            try:
                ssh.close()
            except Exception:
                pass
    
    def _sync_sftp_directory(self, sftp, remote_path, local_path, sync_name):
        """递归同步SFTP目录"""
        synced_count = 0
        os.makedirs(local_path, exist_ok=True)
        
        file_list = sftp.listdir_attr(remote_path)
        
        for file_attr in file_list:
            if not self.running:
                break
            remote_filename = file_attr.filename
            remote_filepath = os.path.join(remote_path, remote_filename).replace('\\', '/')
            local_filepath = os.path.join(local_path, remote_filename)
            
            if remote_filename in ['.', '..']:
                continue
            
            if file_attr.st_mode & 0o40000:
                sub_synced = self._sync_sftp_directory(sftp, remote_filepath, local_filepath, sync_name)
                synced_count += sub_synced
            else:
                if self._need_sync_sftp(file_attr, local_filepath):
                    if self._download_sftp_file(sftp, remote_filepath, local_filepath):
                        synced_count += 1
        
        return synced_count
    
    def _sync_local(self, name, config):
        """本地目录同步"""
        print(f"[Local Sync] 开始同步: {name}")
        source_dir = config['path']
        target_dir = os.path.join(self.config['base_dir'], config.get('target', name))

        if not os.path.exists(source_dir):
            raise ValueError(f"源目录不存在: {source_dir}")

        os.makedirs(target_dir, exist_ok=True)
        print(f"[Local Sync] 源: {source_dir} -> 目标: {target_dir}")

        # 统计文件总数
        all_files = []
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                all_files.append(os.path.join(root, file))

        total_files = len(all_files)
        print(f"[Local Sync] 共 {total_files} 个文件")

        with self.sync_lock:
            self.sync_status[name]['total_files'] = total_files

        synced_count = 0
        for i, source_file in enumerate(all_files):
            if not self.running:
                break

            relative_path = os.path.relpath(source_file, source_dir)
            target_file = os.path.join(target_dir, relative_path)

            if self._need_sync_local(source_file, target_file):
                # 确保目标目录存在
                target_file_dir = os.path.dirname(target_file)
                if not os.path.exists(target_file_dir):
                    os.makedirs(target_file_dir, exist_ok=True)

                try:
                    shutil.copy2(source_file, target_file)
                    synced_count += 1
                except Exception as e:
                    print(f"[Local Sync] 复制失败 {relative_path}: {e}")

            with self.sync_lock:
                self.sync_status[name]['files_synced'] = synced_count

            if (i + 1) % 100 == 0:
                print(f"[Local Sync] 进度: {i+1}/{total_files}")

        with self.sync_lock:
            self.sync_status[name]['files_synced'] = synced_count
        print(f"[Local Sync] 完成: 成功同步 {synced_count} 个文件")

    def _sync_rsync(self, name, config):
        """Rsync同步 - 需要系统安装rsync命令"""
        import subprocess

        source = config.get('source', config.get('url', ''))
        target_dir = os.path.join(self.config['base_dir'], config.get('target', name))
        os.makedirs(target_dir, exist_ok=True)

        print(f"开始Rsync同步 {name} -> {target_dir}")

        # rsync选项
        options = ['-avz', '--progress', '--delete']
        if config.get('exclude'):
            for pattern in config['exclude']:
                options.extend(['--exclude', pattern])

        # 添加SSH选项（如果需要）
        if config.get('ssh'):
            options.extend(['-e', 'ssh'])

        rsync_cmd = ['rsync'] + options + [source, target_dir]

        try:
            result = subprocess.run(
                rsync_cmd,
                capture_output=True,
                text=True,
                timeout=config.get('timeout', 3600)
            )
            if result.returncode != 0:
                raise Exception(f"rsync失败: {result.stderr}")
        except FileNotFoundError:
            raise Exception("rsync命令未安装，请运行: apt install rsync")

    def _sync_git(self, name, config):
        """Git仓库同步 - 克隆或更新Git仓库"""
        import subprocess

        repo_url = config.get('url')
        target_dir = os.path.join(self.config['base_dir'], config.get('target', name))
        branch = config.get('branch', 'main')
        depth = config.get('depth', 1)  # 浅克隆

        os.makedirs(target_dir, exist_ok=True)
        repo_path = os.path.join(target_dir, '.repo')

        print(f"开始Git同步 {name} -> {target_dir}")

        if os.path.exists(os.path.join(target_dir, '.git')):
            # 已存在，执行git pull
            try:
                subprocess.run(['git', 'fetch', '--all'], cwd=target_dir, check=True, capture_output=True)
                subprocess.run(['git', 'reset', '--hard', f'origin/{branch}'], cwd=target_dir, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                raise Exception(f"Git pull失败: {e}")
        else:
            # 克隆新仓库
            cmd = ['git', 'clone']
            if depth:
                cmd.extend(['--depth', str(depth)])
            if branch != 'main':
                cmd.extend(['-b', branch])
            cmd.extend([repo_url, target_dir])

            try:
                subprocess.run(cmd, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                raise Exception(f"Git clone失败: {e}")

    def _sync_s3(self, name, config):
        """AWS S3兼容存储同步 (S3/OSS/COS/MinIO等)"""
        try:
            import boto3
        except ImportError:
            raise Exception("请安装boto3库: pip install boto3")

        print(f"[S3 Sync] 开始同步: {name}")
        endpoint = config.get('endpoint', config.get('url'))
        bucket = config.get('bucket')
        access_key = config.get('access_key', config.get('aws_access_key_id'))
        secret_key = config.get('secret_key', config.get('aws_secret_access_key'))
        region = config.get('region', 'us-east-1')

        target_dir = os.path.join(self.config['base_dir'], config.get('target', name))
        os.makedirs(target_dir, exist_ok=True)
        print(f"[S3 Sync] 目标目录: {target_dir}")

        # 创建S3客户端
        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )

        prefix = config.get('prefix', '')

        # 首先统计文件数量
        total_files = 0
        try:
            paginator = s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                if 'Contents' in page:
                    total_files += len([o for o in page['Contents'] if not o['Key'].endswith('/')])
        except Exception as e:
            print(f"[S3 Sync] 统计文件数失败: {e}")

        print(f"[S3 Sync] 共 {total_files} 个文件")

        with self.sync_lock:
            self.sync_status[name]['total_files'] = total_files

        synced_count = 0

        try:
            paginator = s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                if 'Contents' not in page:
                    continue

                for obj in page['Contents']:
                    if not self.running:
                        break

                    key = obj['Key']
                    if key.endswith('/'):
                        continue

                    local_path = os.path.join(target_dir, key[len(prefix):].lstrip('/'))
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)

                    # 检查是否需要下载
                    need_download = True
                    if os.path.exists(local_path):
                        local_size = os.path.getsize(local_path)
                        if local_size == obj['Size']:
                            need_download = False

                    if need_download:
                        try:
                            s3_client.download_file(bucket, key, local_path)
                            synced_count += 1
                        except Exception as e:
                            print(f"[S3 Sync] 下载失败 {key}: {e}")

                    with self.sync_lock:
                        self.sync_status[name]['files_synced'] = synced_count

        except Exception as e:
            raise Exception(f"S3同步失败: {e}")

        print(f"[S3 Sync] 完成: 成功同步 {synced_count} 个文件")

    def _sync_oss(self, name, config):
        """阿里云OSS同步"""
        config['type'] = 's3'  # 复用S3逻辑
        config['endpoint'] = config.get('endpoint', f"https://{config.get('bucket')}.oss-{config.get('region', 'cn-hangzhou')}.aliyuncs.com")
        self._sync_s3(name, config)

    def _sync_cos(self, name, config):
        """腾讯云COS同步"""
        config['type'] = 's3'  # 复用S3逻辑
        config['endpoint'] = config.get('endpoint', f"https://{config.get('bucket')}.cos.{config.get('region', 'ap-guangzhou')}.myqcloud.com")
        self._sync_s3(name, config)

    def _sync_webdav(self, name, config):
        """WebDAV同步"""
        import urllib.request

        url = config.get('url', config.get('server'))
        username = config.get('username')
        password = config.get('password')
        remote_path = config.get('remote_path', '/')

        target_dir = os.path.join(self.config['base_dir'], config.get('target', name))
        os.makedirs(target_dir, exist_ok=True)

        print(f"开始WebDAV同步 {name} -> {target_dir}")

        # 构建认证
        if username and password:
            import base64
            auth_string = f"{username}:{password}"
            encoded_auth = base64.b64encode(auth_string.encode()).decode()

        # PROPFIND获取文件列表
        req = urllib.request.Request(
            f"{url}{remote_path}",
            method='PROPFIND',
            headers={'Authorization': f'Basic {encoded_auth}'}
        )

        # 简化实现 - 实际需要解析XML
        raise Exception("WebDAV同步需要完整实现，目前仅支持基础配置")

    def _get_http_file_list(self, base_url, config, specific_packages=None):
        """获取HTTP文件列表 - 支持PyPI等复杂索引

        Args:
            base_url: 源URL
            config: 配置信息
            specific_packages: 可选的特定包列表
        """
        import urllib.request
        import re

        file_list = []

        # 检测是否为PyPI simple索引
        is_pypi = 'pypi' in base_url.lower() or config.get('is_pypi', False)

        if is_pypi:
            print(f"[HTTP] 检测到PyPI索引，使用PyPI专用解析")
            return self._get_pypi_file_list(base_url, config, specific_packages)

        if 'api_url' in config:
            try:
                req = urllib.request.Request(config['api_url'])
                if 'username' in config and 'password' in config:
                    auth_string = f"{config['username']}:{config['password']}"
                    encoded_auth = base64.b64encode(auth_string.encode()).decode()
                    req.add_header('Authorization', f'Basic {encoded_auth}')

                with urllib.request.urlopen(req) as response:
                    api_data = json.loads(response.read().decode())
                    if 'files' in api_data:
                        for file_info in api_data['files']:
                            file_list.append({
                                'name': file_info.get('name', ''),
                                'url': file_info.get('url', ''),
                                'size': file_info.get('size', 0)
                            })
                return file_list
            except Exception as e:
                print(f"API获取文件列表失败: {e}")

        if config.get('parse_html', True):
            try:
                file_list = self._fetch_http_directory(base_url, config, max_depth=3)
                return file_list
            except Exception as e:
                print(f"HTML解析文件列表失败: {e}")

        return file_list

    def _get_pypi_file_list(self, base_url, config, specific_packages=None):
        """获取PyPI文件列表

        Args:
            base_url: PyPI镜像源URL
            config: 配置信息
            specific_packages: 可选的特定包列表，如果提供则只获取这些包的文件
        """
        import urllib.request
        import urllib.parse
        import re

        print(f"[PyPI] 获取PyPI包列表: {base_url}")

        # 获取包名列表
        package_index_url = base_url.rstrip('/') + '/'
        if not package_index_url.endswith('/simple/') and not package_index_url.endswith('/simple'):
            if package_index_url.endswith('/'):
                package_index_url += 'simple/'
            else:
                package_index_url += '/simple/'

        # 获取包列表
        if specific_packages:
            # 指定了特定包，直接使用
            packages = list(specific_packages)
            print(f"[PyPI] 将只同步指定 {len(packages)} 个包: {', '.join(packages[:5])}{'...' if len(packages) > 5 else ''}")
        else:
            # 获取所有包
            try:
                # 添加User-Agent避免被拒绝
                req = urllib.request.Request(package_index_url, headers={'User-Agent': 'MirrorSync/1.0'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    html_content = response.read().decode('utf-8', errors='ignore')

                # 提取所有包名 - 兼容不同格式
                # 格式1: <a href="/simple/package/">package</a>
                package_pattern = r'<a[^>]+href="/simple/([^/"]+)/"[^>]*>'
                packages = re.findall(package_pattern, html_content)

                if not packages:
                    # 格式2: <a href="package/">package</a> (清华源格式)
                    package_pattern = r'<a[^>]+href="([^/"]+)/"[^>]*>'
                    packages = re.findall(package_pattern, html_content)

                # 过滤掉非包名
                packages = [p for p in packages if p and not p.startswith('..')]

                print(f"[PyPI] 发现 {len(packages)} 个包")

                # 限制包数量
                max_packages = config.get('max_packages', 50)
                packages = packages[:max_packages]
                print(f"[PyPI] 将获取前 {max_packages} 个包的文件")
            except Exception as e:
                print(f"[PyPI] 获取包列表失败: {e}")
                return []

        file_list = []
        success_count = 0
        fail_count = 0

        for i, package_name in enumerate(packages):
            if not self.running:
                break

            # 更新进度
            with self.sync_lock:
                if hasattr(self, 'sync_status') and self.sync_status:
                    for name in self.sync_status:
                        if 'total_files' in self.sync_status[name]:
                            self.sync_status[name]['files_synced'] = i

            # 获取每个包的文件列表
            package_url = f"{package_index_url}{package_name}/"
            try:
                req = urllib.request.Request(package_url, headers={'User-Agent': 'MirrorSync/1.0'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    pkg_html = response.read().decode('utf-8', errors='ignore')

                # 提取whl文件 - 允许前面有路径，后面可能有 #sha256= 锚点
                file_pattern = r'<a[^>]+href="([^"]*\.whl)(?:#[^"]*)?"[^>]*>'
                whl_files = re.findall(file_pattern, pkg_html)

                # 也提取tar.gz文件 - 允许前面有路径，后面可能有 #sha256= 锚点
                file_pattern = r'<a[^>]+href="([^"]*\.tar\.gz)(?:#[^"]*)?"[^>]*>'
                tar_files = re.findall(file_pattern, pkg_html)
                whl_files.extend(tar_files)

                # 也提取zip文件 - 允许前面有路径，后面可能有 #sha256= 锚点
                file_pattern = r'<a[^>]+href="([^"]*\.zip)(?:#[^"]*)?"[^>]*>'
                zip_files = re.findall(file_pattern, pkg_html)
                whl_files.extend(zip_files)

                if whl_files:
                    success_count += 1
                    for filename in whl_files:
                        # 使用urljoin正确处理相对路径
                        # PyPI页面中的href可能是 "../../packages/.../file.tar.gz" 格式
                        file_url = urllib.parse.urljoin(package_url, filename)
                        file_list.append({
                            'name': f"{package_name}/{filename.split('/')[-1]}",
                            'url': file_url,
                            'size': 0,
                            'is_package_file': True
                        })
                else:
                    fail_count += 1

            except Exception as e:
                fail_count += 1
                if fail_count <= 3:  # 只显示前几个错误
                    print(f"[PyPI] 获取包 {package_name} 文件列表失败: {e}")
                elif fail_count == 4:
                    print(f"[PyPI] 更多错误不再显示...")

        print(f"[PyPI] 获取完成: 成功 {success_count} 个包, 失败 {fail_count} 个包, 共 {len(file_list)} 个文件")
        return file_list

    def _fetch_http_directory(self, base_url, config, max_depth=3, current_depth=0):
        """递归获取HTTP目录内容"""
        import urllib.request
        import re

        if current_depth > max_depth:
            return []

        file_list = []

        try:
            req = urllib.request.Request(base_url)
            with urllib.request.urlopen(req, timeout=30) as response:
                html_content = response.read().decode('utf-8', errors='ignore')

            # 更健壮的链接提取
            link_pattern = r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]*)</a>'
            matches = re.findall(link_pattern, html_content)

            for href, text in matches:
                href = href.strip()
                if not href or href in ['../', './', '/', ''] or href.startswith('?'):
                    continue
                if href.startswith('#'):
                    continue

                # 构建完整URL
                if href.startswith('http'):
                    file_url = href
                else:
                    file_url = base_url.rstrip('/') + '/' + href.lstrip('/')

                # 获取文件名
                filename = href.split('/')[-1] if '/' in href else href

                # 判断是目录还是文件
                is_directory = href.endswith('/')

                if is_directory:
                    # 递归获取子目录
                    sub_files = self._fetch_http_directory(file_url, config, max_depth, current_depth + 1)
                    file_list.extend(sub_files)
                else:
                    # 添加文件
                    file_list.append({
                        'name': filename,
                        'url': file_url,
                        'size': 0
                    })

        except Exception as e:
            print(f"获取目录 {base_url} 失败: {e}")

        return file_list
    
    def _need_sync_http(self, file_info, local_path):
        """检查HTTP文件是否需要同步"""
        if not os.path.exists(local_path):
            return True
        local_size = os.path.getsize(local_path)
        remote_size = file_info.get('size', 0)
        return local_size != remote_size
    
    def _need_sync_ftp(self, ftp, remote_filename, local_path, file_info):
        """检查FTP文件是否需要同步"""
        if not os.path.exists(local_path):
            return True
        local_size = os.path.getsize(local_path)
        remote_size = file_info['size']
        return local_size != remote_size
    
    def _need_sync_sftp(self, file_attr, local_path):
        """检查SFTP文件是否需要同步"""
        if not os.path.exists(local_path):
            return True
        local_size = os.path.getsize(local_path)
        remote_size = file_attr.st_size
        if local_size != remote_size:
            return True
        local_mtime = os.path.getmtime(local_path)
        remote_mtime = file_attr.st_mtime
        return abs(local_mtime - remote_mtime) > 1
    
    def _need_sync_local(self, source_path, target_path):
        """检查本地文件是否需要同步"""
        if not os.path.exists(target_path):
            return True
        source_mtime = os.path.getmtime(source_path)
        target_mtime = os.path.getmtime(target_path)
        return source_mtime > target_mtime or os.path.getsize(source_path) != os.path.getsize(target_path)
    
    def _download_file_http(self, url, local_path, config):
        """下载HTTP文件"""
        import urllib.request
        import base64
        from email.utils import parsedate
        
        try:
            req = urllib.request.Request(url)
            headers = config.get('headers', {})
            for key, value in headers.items():
                req.add_header(key, value)
            
            if 'username' in config and 'password' in config:
                auth_string = f"{config['username']}:{config['password']}"
                encoded_auth = base64.b64encode(auth_string.encode()).decode()
                req.add_header('Authorization', f'Basic {encoded_auth}')
            
            timeout = config.get('timeout', 30)
            
            start_byte = 0
            if os.path.exists(local_path):
                start_byte = os.path.getsize(local_path)
                if start_byte > 0:
                    req.add_header('Range', f'bytes={start_byte}-')
            
            temp_path = local_path + '.tmp'
            mode = 'ab' if start_byte > 0 else 'wb'
            
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.getcode() not in [200, 206]:
                    raise Exception(f"HTTP错误: {response.getcode()}")
                
                with open(temp_path, mode) as f:
                    while True:
                        if not self.running:
                            break
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
            
            if self.running:
                if os.path.exists(local_path):
                    os.remove(local_path)
                os.rename(temp_path, local_path)
                
                last_modified = response.headers.get('Last-Modified')
                if last_modified:
                    try:
                        timestamp = time.mktime(parsedate(last_modified))
                        os.utime(local_path, (timestamp, timestamp))
                    except:
                        pass
                return True
            else:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return False
                
        except Exception as e:
            print(f"下载HTTP文件失败 {url}: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False
    
    def _download_ftp_file(self, ftp, remote_filename, local_path, file_info):
        """下载FTP文件"""
        try:
            mode = 'wb'
            start_pos = 0
            if os.path.exists(local_path):
                start_pos = os.path.getsize(local_path)
                if start_pos < file_info['size']:
                    mode = 'ab'
                else:
                    return True
            
            with open(local_path, mode) as f:
                if start_pos > 0:
                    ftp.voidcmd('TYPE I')
                    ftp.retrbinary(f'RETR {remote_filename}', f.write, rest=start_pos)
                else:
                    ftp.retrbinary(f'RETR {remote_filename}', f.write)
            
            return True
        except Exception as e:
            print(f"下载FTP文件失败 {remote_filename}: {e}")
            return False
    
    def _download_sftp_file(self, sftp, remote_path, local_path):
        """下载SFTP文件"""
        try:
            start_pos = 0
            if os.path.exists(local_path):
                start_pos = os.path.getsize(local_path)
            
            file_attr = sftp.stat(remote_path)
            remote_size = file_attr.st_size
            
            if start_pos >= remote_size:
                return True
            
            with sftp.open(remote_path, 'rb') as remote_file:
                if start_pos > 0:
                    remote_file.seek(start_pos)
                
                with open(local_path, 'ab' if start_pos > 0 else 'wb') as local_file:
                    while True:
                        if not self.running:
                            break
                        chunk = remote_file.read(8192)
                        if not chunk:
                            break
                        local_file.write(chunk)
            
            os.utime(local_path, (file_attr.st_atime, file_attr.st_mtime))
            return True
        except Exception as e:
            print(f"下载SFTP文件失败 {remote_path}: {e}")
            return False
    
    def get_sync_status(self):
        """获取同步状态"""
        with self.sync_lock:
            return self.sync_status.copy()
    
    def start(self):
        """启动同步管理器"""
        self.running = True
        auto_sync_sources = [name for name, config in self.sync_sources.items() 
                           if config.get('auto_sync', False)]
        for name in auto_sync_sources:
            self.start_sync(name)
    
    def stop(self):
        """停止同步管理器"""
        self.running = False
        self.stop_all_sync()
        self.executor.shutdown(wait=False)
