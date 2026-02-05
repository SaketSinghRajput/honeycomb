# EC2 Deployment Quick Reference

## Quick Start (5 minutes)

### 1. SSH into EC2
```bash
ssh -i your-key.pem ubuntu@<EC2-PUBLIC-IP>
```

### 2. Run automated deployment
```bash
# Download and run the deployment script
curl -O https://raw.githubusercontent.com/your-username/buildathon-ai-impact/main/deploy.sh
bash deploy.sh your-domain.com "your-secure-api-key"
```

### 3. Verify deployment
```bash
# Check service status
sudo systemctl status scam-honeypot

# View logs
sudo journalctl -u scam-honeypot -f

# Test health endpoint
curl http://localhost:8000/health
```

---

## Essential Commands

### Service Management
```bash
sudo systemctl start scam-honeypot          # Start service
sudo systemctl stop scam-honeypot           # Stop service
sudo systemctl restart scam-honeypot        # Restart service
sudo systemctl status scam-honeypot         # Check status
sudo systemctl enable scam-honeypot         # Enable on boot
sudo systemctl disable scam-honeypot        # Disable on boot
```

### Viewing Logs
```bash
# Application logs (last 50 lines)
sudo journalctl -u scam-honeypot -n 50

# Follow application logs in real-time
sudo journalctl -u scam-honeypot -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# Full application logs
tail -f /opt/scam-honeypot/backend/logs/app.log
```

### Configuration Updates
```bash
# Edit environment variables
nano /opt/scam-honeypot/backend/.env

# Restart after changes
sudo systemctl restart scam-honeypot
```

### Manual Testing
```bash
# Health check
curl http://localhost:8000/health

# Detect scam
curl -X POST http://localhost:8000/api/v1/detect \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-api-key" \
  -d '{"transcript": "Send OTP now!"}'

# Extract entities
curl -X POST http://localhost:8000/api/v1/extract \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-api-key" \
  -d '{"transcript": "UPI: scam@paytm, +919876543210"}'
```

---

## Troubleshooting

### Service won't start
```bash
# Check detailed error
sudo journalctl -u scam-honeypot -n 100 --all

# Check if port is in use
sudo lsof -i :8000

# Fix permissions
sudo chown -R ubuntu:ubuntu /opt/scam-honeypot
```

### Model loading errors
```bash
# Re-download models
cd /opt/scam-honeypot/backend
source ../venv/bin/activate
python scripts/download_models.py

# Restart service
sudo systemctl restart scam-honeypot
```

### Nginx issues
```bash
# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx

# Check Nginx status
sudo systemctl status nginx
```

### High memory/CPU usage
```bash
# Check process usage
ps aux | grep gunicorn

# Monitor in real-time
top -u ubuntu

# Reduce worker processes in systemd service
sudo nano /etc/systemd/system/scam-honeypot.service
# Change: --workers 2 (reduce from 3)
sudo systemctl daemon-reload
sudo systemctl restart scam-honeypot
```

---

## Configuration Guide

### .env Settings (Production)
```env
# Hostname and port
API_HOST=0.0.0.0
API_PORT=8000

# Worker processes (CPU cores - 1)
API_WORKERS=2

# Device (cpu or cuda)
DEVICE=cpu

# API authentication
API_SECRET_KEY=your-strong-secret-key-here

# CORS origins
CORS_ORIGINS=["https://your-domain.com"]

# Logging
LOG_LEVEL=INFO

# Models
WHISPER_MODEL_NAME=base
LLM_USE_API=false
DEMO_MODE=false
```

### Instance Sizing Guide
```
Development:     t3.medium (2 vCPU, 4GB RAM)
Production:      t3.large  (2 vCPU, 8GB RAM)
High Traffic:    t3.xlarge (4 vCPU, 16GB RAM)
GPU Inference:   g4dn.xlarge (4 vCPU, 16GB RAM + GPU)
```

---

## Monitoring Commands

### Resource Usage
```bash
# CPU and Memory
free -h              # Memory usage
df -h                # Disk usage
top -u ubuntu        # Process monitoring

# Network
ss -tunap | grep 8000
netstat -an | grep ESTABLISHED | wc -l
```

### Application Health
```bash
# API response time
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8000/health

# Check active connections
sudo ss -tunap | grep 8000

# Model validation
python -c "from app.models.model_loader import get_model_loader; ml=get_model_loader(); ml.validate_all_models()"
```

---

## Backup and Recovery

### Backup models
```bash
# Backup to S3
tar -czf models_backup.tar.gz backend/models/
aws s3 cp models_backup.tar.gz s3://your-bucket/backups/

# Restore from backup
aws s3 cp s3://your-bucket/backups/models_backup.tar.gz .
tar -xzf models_backup.tar.gz
```

### Backup configuration
```bash
# Backup .env
cp backend/.env backup/.env.$(date +%Y%m%d)
```

---

## Security Checklist

- [ ] Change `API_SECRET_KEY` to strong value
- [ ] Set specific `CORS_ORIGINS` (not "*")
- [ ] Enable SSL certificates (Let's Encrypt)
- [ ] Restrict Security Group to needed ports
- [ ] Use SSH keys (disable password auth)
- [ ] Enable VPC encryption
- [ ] Set up CloudWatch monitoring
- [ ] Enable automatic updates
- [ ] Configure firewall rules
- [ ] Set up DDoS protection

---

## Performance Tuning

### Increase worker processes
```bash
# Edit systemd service
sudo nano /etc/systemd/system/scam-honeypot.service

# Change --workers 2 to --workers 4
# (set to CPU cores - 1)

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart scam-honeypot
```

### Enable model caching
```bash
# Models are cached in-memory after first load
# Monitor memory: free -h
# Restart if memory grows: sudo systemctl restart scam-honeypot
```

### Use smaller models for faster response
```env
# In .env
WHISPER_MODEL_NAME=tiny    # Faster, less accurate
WHISPER_MODEL_NAME=base    # Balanced (default)
WHISPER_MODEL_NAME=large   # Slower, more accurate
```

---

## Useful Aliases

Add to `~/.bashrc` for convenience:

```bash
# Service shortcuts
alias hps='sudo systemctl status scam-honeypot'
alias hpstart='sudo systemctl start scam-honeypot'
alias hpstop='sudo systemctl stop scam-honeypot'
alias hprestart='sudo systemctl restart scam-honeypot'
alias hplogs='sudo journalctl -u scam-honeypot -f'

# Directory shortcuts
alias hp='cd /opt/scam-honeypot'
alias hpback='cd /opt/scam-honeypot/backend'

# Useful commands
alias hphealth='curl -s http://localhost:8000/health | jq'
alias hpenv='nano /opt/scam-honeypot/backend/.env'
```

Apply with: `source ~/.bashrc`

---

## Additional Resources

- **Documentation**: `/opt/scam-honeypot/DEPLOYMENT_GUIDE.md`
- **API Guide**: `/opt/scam-honeypot/API_TESTING_GUIDE.md`
- **Logs**: `sudo journalctl -u scam-honeypot`
- **Config**: `/opt/scam-honeypot/backend/.env`
- **System Service**: `/etc/systemd/system/scam-honeypot.service`
- **Nginx Config**: `/etc/nginx/sites-available/scam-honeypot`

---

## Support and Debugging

### Enable debug logging
```bash
# Edit .env
LOG_LEVEL=DEBUG

# Restart service
sudo systemctl restart scam-honeypot

# View detailed logs
sudo journalctl -u scam-honeypot -f
```

### Check system resources
```bash
# Memory
free -m

# CPU cores
nproc

# Disk space
df -h

# Network interfaces
ip addr show
```

### Test connectivity
```bash
# Test to server
curl -v http://localhost:8000/health

# Check DNS
nslookup your-domain.com

# Check port listening
sudo netstat -tuln | grep 8000
```
