#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""镜像同步管理模块"""

import os
import json
import time
import ftplib
import shutil
import importlib
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
        self.sync_sources = config.get('sync_sources', {})
        self.sync_threads = {}
        self.sync_status = {}
        self.sync_lock = Lock()
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers=3)
        
        # 加载同步状态
        self.sync_state_file = config.get('sync_state_file', 'sync_state.json')
        self.load_sync_state()
    
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
    
    def add_sync_source(self, name, source_config):
        """添加同步源"""
        with self.sync_lock:
            self.sync_sources[name] = source_config
            self.sync_status[name] = {
                'last_sync': None,
                'status': 'stopped',
                'files_synced': 0,
                'total_files': 0,
                'error': None
            }
            self.save_sync_state()
    
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
    
    def start_sync(self, name):
        """开始同步指定源"""
        if name not in self.sync_sources:
            return False
        
        if name in self.sync_threads and self.sync_threads[name].is_alive():
            return True  # 已经在运行
        
        with self.sync_lock:
            self.sync_status[name]['status'] = 'syncing'
            self.sync_status[name]['error'] = None
        
        thread = Thread(target=self._sync_worker, args=(name,), daemon=True)
        self.sync_threads[name] = thread
        thread.start()
        return True
    
    def stop_sync(self, name):
        """停止同步指定源"""
        if name in self.sync_threads:
            with self.sync_lock:
                self.sync_status[name]['status'] = 'stopping'
            # 等待线程结束
            self.sync_threads[name].join(timeout=10)
            if name in self.sync_threads:
                del self.sync_threads[name]
            with self.sync_lock:
                self.sync_status[name]['status'] = 'stopped'
    
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
        source_config = self.sync_sources[name]
        sync_type = source_config.get('type', 'http')
        
        try:
            if sync_type == 'http' or sync_type == 'https':
                self._sync_http(name, source_config)
            elif sync_type == 'ftp':
                self._sync_ftp(name, source_config)
            elif sync_type == 'sftp':
                self._sync_sftp(name, source_config)
            elif sync_type == 'local':
                self._sync_local(name, source_config)
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
    
    def _sync_http(self, name, config):
        """HTTP/HTTPS同步"""
        # HTTP同步实现（简化版）
        target_dir = os.path.join(self.config['base_dir'], config.get('target', name))
        os.makedirs(target_dir, exist_ok=True)
        
        # 获取文件列表
        file_list = self._get_http_file_list(config.get('url', ''), config)
        
        with self.sync_lock:
            self.sync_status[name]['total_files'] = len(file_list)
        
        synced_count = 0
        for file_info in file_list:
            if not self.running:
                break
            # 同步文件
            local_path = os.path.join(target_dir, file_info['name'])
            if self._need_sync_http(file_info, local_path):
                if self._download_file_http(file_info['url'], local_path, config):
                    synced_count += 1
            with self.sync_lock:
                self.sync_status[name]['files_synced'] = synced_count
    
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
            
            ftp.quit()
            
        except Exception as e:
            raise Exception(f"FTP同步失败: {str(e)}")
    
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
        
        synced_count = self._sync_sftp_directory(sftp, remote_path, target_dir, name)
        
        with self.sync_lock:
            self.sync_status[name]['files_synced'] = synced_count
        
        sftp.close()
        ssh.close()
    
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
        source_dir = config['path']
        target_dir = os.path.join(self.config['base_dir'], config.get('target', name))
        
        if not os.path.exists(source_dir):
            raise ValueError(f"源目录不存在: {source_dir}")
        
        os.makedirs(target_dir, exist_ok=True)
        
        for root, dirs, files in os.walk(source_dir):
            relative_path = os.path.relpath(root, source_dir)
            target_path = os.path.join(target_dir, relative_path)
            os.makedirs(target_path, exist_ok=True)
            
            for file in files:
                if not self.running:
                    break
                source_file = os.path.join(root, file)
                target_file = os.path.join(target_path, file)
                if self._need_sync_local(source_file, target_file):
                    shutil.copy2(source_file, target_file)
    
    def _get_http_file_list(self, base_url, config):
        """获取HTTP文件列表"""
        import urllib.request
        import re
        import base64
        
        file_list = []
        
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
                req = urllib.request.Request(base_url)
                with urllib.request.urlopen(req) as response:
                    html_content = response.read().decode('utf-8', errors='ignore')
                
                link_pattern = r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>'
                matches = re.findall(link_pattern, html_content, re.IGNORECASE)
                
                for href, text in matches:
                    if href in ['../', './'] or href.startswith('?'):
                        continue
                    file_url = href if href.startswith('http') else base_url.rstrip('/') + '/' + href.lstrip('/')
                    file_list.append({
                        'name': href.split('/')[-1],
                        'url': file_url,
                        'size': 0
                    })
                return file_list
            except Exception as e:
                print(f"HTML解析文件列表失败: {e}")
        
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
