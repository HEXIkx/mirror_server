# ============================================
# HYC下载站 v2.2 - Kubernetes 部署指南
# ============================================

## 快速部署

### 1. 创建命名空间 (可选)
```bash
kubectl create namespace hyc
kubectl config set-context --current --namespace=hyc
```

### 2. 部署应用
```bash
# 使用内置 PostgreSQL 和 Redis (可选)
kubectl apply -f deployment.yaml
kubectl apply -f postgres.yaml
kubectl apply -f redis.yaml

# 或只部署应用，使用外部数据库
kubectl apply -f deployment.yaml
```

### 3. 验证部署
```bash
# 查看 Pods
kubectl get pods -l app=hyc-download-server

# 查看日志
kubectl logs -l app=hyc-download-server -f

# 查看服务
kubectl get svc hyc-server
```

### 4. 访问应用
```bash
# Port Forward (开发环境)
kubectl port-forward svc/hyc-server 8080:8080

# 浏览器访问
# http://localhost:8080
# 管理界面: http://localhost:8080/api/ui/
```

## 生产环境部署

### 1. 构建并推送镜像
```bash
# 构建镜像
docker build -t your-registry/hyc-download-station:v2.2 .

# 推送镜像
docker push your-registry/hyc-download-station:v2.2

# 更新 deployment.yaml 中的镜像地址
```

### 2. 配置域名和 TLS
```bash
# 编辑 deployment.yaml，修改 Ingress 配置
# 添加 TLS secret
kubectl create secret tls hyc-tls-secret --cert=certificate.crt --key=private.key

# 应用配置
kubectl apply -f deployment.yaml
```

### 3. 配置资源限制
```yaml
# 根据实际需求调整 deployment.yaml 中的资源限制
resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: 2000m
    memory: 2Gi
```

### 4. 配置 HPA (自动扩缩容)
```bash
# HPA 已内置，查看状态
kubectl get hpa hyc-hpa
kubectl top pods
```

## 使用外部数据库

### PostgreSQL
```bash
# 设置环境变量或 Secret
export DB_TYPE=postgresql
export DB_HOST=your-postgres-host
export DB_PORT=5432
export DB_NAME=hyc
export DB_USER=postgres
export DB_PASSWORD=your-password

# 或使用连接字符串
export DB_CONN_STR=postgresql://user:pass@host:5432/database
```

### MySQL
```bash
export DB_TYPE=mysql
export DB_HOST=your-mysql-host
export DB_PORT=3306
export DB_NAME=hyc
export DB_USER=root
export DB_PASSWORD=your-password
```

## 监控

### Prometheus + Grafana
```bash
# ServiceMonitor 已内置
# 确保 Prometheus Operator 已安装
kubectl get servicemonitor hyc-monitor

# Grafana Dashboard (导入 json/dashboard.json)
```

### 日志
```bash
# 查看应用日志
kubectl logs -l app=hyc-download-server --tail=100

# 实时日志
kubectl logs -l app=hyc-download-server -f
```

## 升级

```bash
# 更新镜像版本
kubectl set image deployment/hyc-server hyc-server=your-registry/hyc-download-station:v2.3

# 查看滚动更新
kubectl rollout status deployment/hyc-server

# 回滚 (如有问题)
kubectl rollout undo deployment/hyc-server
```

## 卸载

```bash
# 删除所有资源
kubectl delete -f deployment.yaml
kubectl delete -f postgres.yaml
kubectl delete -f redis.yaml

# 删除 PVC (数据将丢失)
kubectl delete pvc hyc-data-pvc hyc-downloads-pvc hyc-cache-pvc
```
