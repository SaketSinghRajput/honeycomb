# Docker Deployment Guide

## Why Docker?
- **Consistency**: Same environment on laptop, EC2, and production
- **Isolation**: No dependency conflicts
- **Simplicity**: One command to deploy
- **Scalability**: Easy to scale with Docker Swarm or Kubernetes

---

## Quick Docker Deployment

### 1. Build Docker Image
```bash
cd /opt/scam-honeypot

# Build the image
docker build -f backend/Dockerfile -t scam-honeypot:latest .

# Or use GPU support
docker build -f backend/Dockerfile.gpu -t scam-honeypot:gpu .
```

### 2. Run Docker Container
```bash
# CPU version
docker run -d \
  --name scam-honeypot \
  -p 8000:8000 \
  -v /opt/scam-honeypot/models:/app/models \
  -e API_SECRET_KEY=your-secret-key \
  -e DEVICE=cpu \
  scam-honeypot:latest

# GPU version (requires nvidia-docker)
docker run -d \
  --name scam-honeypot \
  --gpus all \
  -p 8000:8000 \
  -v /opt/scam-honeypot/models:/app/models \
  -e API_SECRET_KEY=your-secret-key \
  -e DEVICE=cuda \
  scam-honeypot:gpu
```

### 3. Verify Container
```bash
# Check if running
docker ps

# View logs
docker logs -f scam-honeypot

# Test health
curl http://localhost:8000/health
```

---

## Docker Installation on EC2

```bash
# Install Docker
sudo apt update
sudo apt install -y docker.io docker-compose

# Start Docker daemon
sudo systemctl start docker
sudo systemctl enable docker

# Add user to docker group
sudo usermod -aG docker ubuntu
newgrp docker

# Test Docker
docker --version
docker run hello-world
```

---

## Docker Compose Setup

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  scam-honeypot:
    build:
      context: .
      dockerfile: backend/Dockerfile
    container_name: scam-honeypot
    ports:
      - "8000:8000"
    environment:
      - API_SECRET_KEY=your-secure-key
      - DEVICE=cpu
      - API_WORKERS=2
      - CORS_ORIGINS=["*"]
      - DEMO_MODE=false
      - LOG_LEVEL=INFO
    volumes:
      - ./backend/models:/app/models
      - ./backend/logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  nginx:
    image: nginx:alpine
    container_name: scam-honeypot-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - scam-honeypot
    restart: unless-stopped

volumes:
  models:
  logs:
```

Run with Docker Compose:

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f scam-honeypot

# Stop services
docker-compose down

# Update and restart
docker-compose pull
docker-compose up -d
```

---

## Docker with AWS ECR

### 1. Create ECR Repository
```bash
# Set region and account
AWS_REGION=us-east-1
AWS_ACCOUNT=123456789012

# Create repository
aws ecr create-repository \
  --repository-name scam-honeypot \
  --region $AWS_REGION

# Get login token
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin \
  $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com
```

### 2. Push Image to ECR
```bash
# Build image
docker build -f backend/Dockerfile \
  -t $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/scam-honeypot:latest .

# Push to ECR
docker push $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/scam-honeypot:latest
```

### 3. Deploy on EC2 from ECR
```bash
# Pull from ECR
docker pull $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/scam-honeypot:latest

# Run container
docker run -d \
  --name scam-honeypot \
  -p 8000:8000 \
  -v /data/models:/app/models \
  $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/scam-honeypot:latest
```

---

## Docker with ECS (Elastic Container Service)

### 1. Create ECS Task Definition
```bash
cat > task-definition.json <<'EOF'
{
  "family": "scam-honeypot",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["EC2"],
  "cpu": "1024",
  "memory": "2048",
  "containerDefinitions": [
    {
      "name": "scam-honeypot",
      "image": "YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/scam-honeypot:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "hostPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "DEVICE",
          "value": "cpu"
        },
        {
          "name": "API_WORKERS",
          "value": "2"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/scam-honeypot",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "mountPoints": [
        {
          "sourceVolume": "models",
          "containerPath": "/app/models"
        }
      ]
    }
  ],
  "volumes": [
    {
      "name": "models",
      "host": {
        "sourcePath": "/data/models"
      }
    }
  ]
}
EOF

# Register task definition
aws ecs register-task-definition \
  --cli-input-json file://task-definition.json
```

### 2. Create ECS Service
```bash
aws ecs create-service \
  --cluster default \
  --service-name scam-honeypot-service \
  --task-definition scam-honeypot \
  --desired-count 2 \
  --launch-type EC2 \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:...,containerName=scam-honeypot,containerPort=8000
```

---

## Docker Useful Commands

```bash
# Container management
docker ps                        # List running containers
docker ps -a                     # List all containers
docker start scam-honeypot       # Start container
docker stop scam-honeypot        # Stop container
docker restart scam-honeypot     # Restart container
docker rm scam-honeypot          # Remove container
docker logs scam-honeypot        # View logs
docker logs -f scam-honeypot     # Follow logs

# Image management
docker images                    # List images
docker build -t name:tag .       # Build image
docker push name:tag             # Push to registry
docker pull name:tag             # Pull from registry
docker rmi name:tag              # Remove image

# Inspection
docker inspect scam-honeypot     # Container details
docker stats                     # Resource usage
docker top scam-honeypot         # Running processes
docker exec -it scam-honeypot bash  # Enter container

# Cleanup
docker system prune              # Remove unused data
docker volume prune              # Remove unused volumes
```

---

## Kubernetes Deployment

### Create K8s Manifests

`deployment.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: scam-honeypot
spec:
  replicas: 3
  selector:
    matchLabels:
      app: scam-honeypot
  template:
    metadata:
      labels:
        app: scam-honeypot
    spec:
      containers:
      - name: scam-honeypot
        image: your-registry/scam-honeypot:latest
        ports:
        - containerPort: 8000
        env:
        - name: DEVICE
          value: "cpu"
        - name: API_WORKERS
          value: "2"
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 60
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 5
        volumeMounts:
        - name: models
          mountPath: /app/models
      volumes:
      - name: models
        persistentVolumeClaim:
          claimName: models-pvc
```

`service.yaml`:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: scam-honeypot-service
spec:
  selector:
    app: scam-honeypot
  ports:
  - protocol: TCP
    port: 8000
    targetPort: 8000
  type: LoadBalancer
```

Deploy:
```bash
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl get pods
kubectl logs -f deployment/scam-honeypot
```

---

## Troubleshooting Docker

### Container won't start
```bash
# Check logs
docker logs scam-honeypot

# Inspect errors
docker inspect scam-honeypot

# Check available disk space
docker system df
```

### High memory usage
```bash
# Check resource limits
docker stats

# Modify compose memory limit
# In docker-compose.yml add:
# deploy:
#   resources:
#     limits:
#       memory: 4G
```

### Port already in use
```bash
# Find process using port
sudo lsof -i :8000

# Change port in docker-compose
ports:
  - "8001:8000"  # External:Internal
```

### Push to ECR fails
```bash
# Re-authenticate
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com

# Check image tag format
docker tag scam-honeypot:latest \
  YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/scam-honeypot:latest
```

---

## Monitoring in Docker

```bash
# View resource usage
docker stats scam-honeypot

# Get container IP
docker inspect scam-honeypot | grep IPAddress

# View network
docker network ls
docker network inspect bridge

# View mounted volumes
docker inspect -f '{{ json .Mounts }}' scam-honeypot | jq
```

---

## Docker Security Best Practices

```yaml
# In docker-compose.yml
services:
  scam-honeypot:
    # Run as non-root user
    user: appuser
    
    # Read-only root filesystem
    read_only: true
    
    # Limited capabilities
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    
    # Security options
    security_opt:
      - no-new-privileges:true
```

---

## Advanced Networking

### Use External Network
```bash
docker network create scam-network

docker run -d \
  --name scam-honeypot \
  --network scam-network \
  -p 8000:8000 \
  scam-honeypot:latest
```

### Expose API securely
```bash
# Behind reverse proxy (no direct port exposure)
docker run -d \
  --name scam-honeypot \
  --network internal \
  scam-honeypot:latest
```
