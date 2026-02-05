# AWS EC2 Deployment - Step-by-Step Guide

## Architecture Diagram
```
┌─────────────────────────────────────────────────────────┐
│                     AWS Region (us-east-1)              │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │            Internet Gateway / ALB                 │   │
│  │         (Route 53 → CloudFront → ALB)             │   │
│  └──────────────────────────────────────────────────┘   │
│                         ↓                                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │          Security Group (Ingress)                 │   │
│  │  • 443 (HTTPS) - Allow All                        │   │
│  │  • 80 (HTTP) - Allow All                          │   │
│  │  • 22 (SSH) - Allow Your IP                       │   │
│  └──────────────────────────────────────────────────┘   │
│                         ↓                                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │     EC2 Instance (Ubuntu 22.04 LTS)              │   │
│  │     • t3.large (Production)                       │   │
│  │     • 8GB RAM, 2 vCPU                             │   │
│  │     • 50GB EBS (gp3)                              │   │
│  │                                                   │   │
│  │  ┌────────────────────────────────────────────┐  │   │
│  │  │  Nginx (Reverse Proxy)                      │  │   │
│  │  │  Port 80/443                                │  │   │
│  │  └────────────────────────────────────────────┘  │   │
│  │           ↓                                      │   │
│  │  ┌────────────────────────────────────────────┐  │   │
│  │  │  Gunicorn + Uvicorn                         │  │   │
│  │  │  Port 8000 (Internal)                       │  │   │
│  │  │  Workers: 2-4                               │  │   │
│  │  │                                              │  │   │
│  │  │  └────────────────────────────────────────┤  │   │
│  │  │  │ FastAPI Application                      │  │   │
│  │  │  │ • ASR (Whisper)                          │  │   │
│  │  │  │ • Detection (DistilBERT)                 │  │   │
│  │  │  │ • Extraction (spaCy)                     │  │   │
│  │  │  │ • Engagement (Phi-2 LLM)                │  │   │
│  │  │  │ • TTS (Tacotron2)                        │  │   │
│  │  │  └────────────────────────────────────────┤  │   │
│  │  └────────────────────────────────────────────┘  │   │
│  │                                                   │   │
│  │  ┌────────────────────────────────────────────┐  │   │
│  │  │  Volume Mount                               │  │   │
│  │  │  • /models (Pre-trained models)             │  │   │
│  │  │  • /logs (Application logs)                 │  │   │
│  │  └────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────┘   │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │         AWS Services                             │   │
│  │ • CloudWatch (Monitoring & Logs)                 │   │
│  │ • S3 (Model backups)                             │   │
│  │ • SNS (Alerts)                                   │   │
│  │ • Route 53 (DNS)                                 │   │
│  └──────────────────────────────────────────────────┘   │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

---

## Pre-Deployment Checklist

- [ ] AWS Account created
- [ ] EC2 key pair generated and saved
- [ ] IAM user with EC2/CloudWatch permissions
- [ ] VPC and subnet configured (or use default)
- [ ] Security group created
- [ ] Domain name purchased (optional)
- [ ] SSL certificate requested (ACM or Let's Encrypt)

---

## Part 1: AWS Infrastructure Setup

### 1.1 Create Security Group

```bash
# Using AWS CLI
aws ec2 create-security-group \
  --group-name scam-honeypot-sg \
  --description "Security group for Scam Honeypot API" \
  --region us-east-1

# Get Group ID (sg-xxxxxxxxx)
SG_ID="sg-xxxxxxxxx"

# Allow SSH from your IP
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 22 \
  --cidr YOUR_IP/32 \
  --region us-east-1

# Allow HTTPS
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0 \
  --region us-east-1

# Allow HTTP (redirect to HTTPS)
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0 \
  --region us-east-1
```

### 1.2 Create Key Pair

```bash
aws ec2 create-key-pair \
  --key-name scam-honeypot-key \
  --region us-east-1 \
  --query 'KeyMaterial' \
  --output text > scam-honeypot-key.pem

chmod 400 scam-honeypot-key.pem
```

### 1.3 Launch EC2 Instance

Using AWS Console:
1. Go to EC2 Dashboard
2. Click "Launch Instance"
3. Choose **Ubuntu Server 22.04 LTS**
4. Select instance type:
   - Development: `t3.medium`
   - Production: `t3.large`
5. Configure details:
   - VPC: Default or your VPC
   - Subnet: Any available
   - Auto-assign Public IP: Enable
6. Storage: 50GB (gp3)
7. Security Group: Select `scam-honeypot-sg`
8. Key Pair: Select `scam-honeypot-key`
9. Click "Launch"

Or using AWS CLI:

```bash
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.large \
  --key-name scam-honeypot-key \
  --security-group-ids sg-xxxxxxxxx \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=50,VolumeType=gp3}' \
  --region us-east-1

# Get instance ID
INSTANCE_ID="i-xxxxxxxxx"
```

### 1.4 Get Instance Details

```bash
aws ec2 describe-instances \
  --instance-ids i-xxxxxxxxx \
  --region us-east-1 \
  --query 'Reservations[0].Instances[0].[PublicIpAddress,PrivateIpAddress,State.Name]'
```

---

## Part 2: EC2 Setup and Deployment

### 2.1 SSH into Instance

```bash
# Wait 1-2 minutes for instance initialization
ssh -i scam-honeypot-key.pem ubuntu@<PUBLIC-IP>
```

### 2.2 Run Deployment Script

```bash
# Download deployment script
curl -O https://raw.githubusercontent.com/your-repo/main/deploy.sh
chmod +x deploy.sh

# Run deployment
./deploy.sh your-domain.com "your-secure-api-key"

# Or run manually following DEPLOYMENT_GUIDE.md steps
```

### 2.3 Configure Domain (Optional)

```bash
# Update Route 53 (if using AWS)
aws route53 change-resource-record-sets \
  --hosted-zone-id Z123456 \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "api.your-domain.com",
        "Type": "A",
        "TTL": 300,
        "ResourceRecords": [{"Value": "YOUR_EC2_PUBLIC_IP"}]
      }
    }]
  }'
```

---

## Part 3: CloudWatch Monitoring

### 3.1 Enable CloudWatch Agent

```bash
# SSH into instance
ssh -i scam-honeypot-key.pem ubuntu@<PUBLIC-IP>

# Download CloudWatch agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb

# Install
sudo dpkg -i -E ./amazon-cloudwatch-agent.deb

# Create configuration
sudo tee /opt/aws/amazon-cloudwatch-agent/etc/config.json > /dev/null <<'EOF'
{
  "metrics": {
    "namespace": "ScamHoneypot",
    "metrics_collected": {
      "mem": {
        "measurement": [
          {
            "name": "mem_used_percent",
            "rename": "MemoryUtilization",
            "unit": "Percent"
          }
        ],
        "metrics_collection_interval": 60
      },
      "disk": {
        "measurement": [
          {
            "name": "used_percent",
            "rename": "DiskUtilization",
            "unit": "Percent"
          }
        ],
        "metrics_collection_interval": 60,
        "resources": ["/"]
      },
      "cpu": {
        "measurement": [
          {
            "name": "cpu_usage_active",
            "rename": "CPUUtilization",
            "unit": "Percent"
          }
        ],
        "metrics_collection_interval": 60,
        "totalcpu": true
      }
    }
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/syslog",
            "log_group_name": "/aws/ec2/scam-honeypot",
            "log_stream_name": "{instance_id}/syslog"
          },
          {
            "file_path": "/opt/scam-honeypot/backend/logs/*.log",
            "log_group_name": "/aws/ec2/scam-honeypot",
            "log_stream_name": "{instance_id}/app"
          }
        ]
      }
    }
  }
}
EOF

# Start agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -s \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/config.json
```

### 3.2 Create CloudWatch Alarms

```bash
# High CPU Alarm
aws cloudwatch put-metric-alarm \
  --alarm-name scam-honeypot-high-cpu \
  --alarm-description "Alert when CPU exceeds 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:us-east-1:123456789012:alerts

# High Memory Alarm
aws cloudwatch put-metric-alarm \
  --alarm-name scam-honeypot-high-memory \
  --alarm-description "Alert when memory exceeds 80%" \
  --metric-name MemoryUtilization \
  --namespace ScamHoneypot \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:us-east-1:123456789012:alerts
```

---

## Part 4: SSL/TLS Certificate

### Option A: Using Let's Encrypt (Free)

```bash
# SSH into instance
ssh -i scam-honeypot-key.pem ubuntu@<PUBLIC-IP>

# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Get certificate
sudo certbot certonly --nginx -d your-domain.com -d www.your-domain.com

# Verify auto-renewal
sudo systemctl enable certbot.timer
```

### Option B: Using AWS ACM

```bash
# Request certificate in AWS Console or CLI
aws acm request-certificate \
  --domain-name your-domain.com \
  --subject-alternative-names www.your-domain.com \
  --region us-east-1

# Copy certificate ARN to Application Load Balancer
```

---

## Part 5: Auto-Scaling (Optional)

### Create Launch Template

```bash
aws ec2 create-launch-template \
  --launch-template-name scam-honeypot-template \
  --version-description "Scam Honeypot v1" \
  --launch-template-data '{
    "ImageId": "ami-0c55b159cbfafe1f0",
    "InstanceType": "t3.large",
    "KeyName": "scam-honeypot-key",
    "SecurityGroupIds": ["sg-xxxxxxxxx"],
    "BlockDeviceMappings": [{
      "DeviceName": "/dev/sda1",
      "Ebs": {"VolumeSize": 50, "VolumeType": "gp3"}
    }],
    "UserData": "..."
  }'
```

### Create Auto Scaling Group

```bash
aws autoscaling create-auto-scaling-group \
  --auto-scaling-group-name scam-honeypot-asg \
  --launch-template LaunchTemplateName=scam-honeypot-template,Version=\$Latest \
  --min-size 2 \
  --max-size 6 \
  --desired-capacity 2 \
  --target-group-arns arn:aws:elasticloadbalancing:... \
  --region us-east-1
```

---

## Part 6: Backup and Disaster Recovery

### 3.1 EBS Snapshots

```bash
# Manual snapshot
aws ec2 create-snapshot \
  --volume-id vol-xxxxxxxxx \
  --description "Scam Honeypot backup $(date +%Y-%m-%d)" \
  --region us-east-1

# Automated snapshots with AWS Backup
# See AWS Backup console
```

### 3.2 Database Backup (if using RDS)

```bash
# Create backup
aws rds create-db-snapshot \
  --db-instance-identifier scam-honeypot-db \
  --db-snapshot-identifier scam-honeypot-backup-$(date +%Y%m%d)
```

---

## Part 7: Logging and Debugging

### View CloudWatch Logs

```bash
# Recent 100 lines
aws logs tail /aws/ec2/scam-honeypot --follow

# Specific time range
aws logs tail /aws/ec2/scam-honeypot --since 1h
```

### SSH Debugging

```bash
# Check systemd service
sudo systemctl status scam-honeypot
sudo journalctl -u scam-honeypot -f

# Check Nginx
sudo systemctl status nginx
sudo tail -f /var/log/nginx/error.log

# Check system resources
free -h
df -h
top -u ubuntu
```

---

## Part 8: Cost Optimization

### Estimated Costs (Monthly)
- **t3.large EC2**: ~$60
- **50GB EBS**: ~$5
- **Data Transfer**: ~$10-20
- **CloudWatch**: ~$5-10
- **Route 53**: ~$0.50
- **Total**: ~$80-100/month

### Cost Reduction Strategies

1. **Use smaller instance**: `t3.medium` saves ~$30/month
2. **Use spot instances**: ~70% cheaper but interruption-prone
3. **Reserved instances**: 30-40% discount for 1-3 year commitment
4. **Data transfer optimization**: Cache models in EBS, not constant downloads

### Set Budget Alert

```bash
aws budgets create-budget \
  --account-id 123456789012 \
  --budget '{
    "BudgetName": "ScamHoneypot",
    "BudgetLimit": {
      "Amount": "100",
      "Unit": "USD"
    },
    "TimeUnit": "MONTHLY",
    "BudgetType": "COST"
  }' \
  --notifications-with-subscribers '[{
    "Notification": {
      "NotificationType": "ACTUAL",
      "ComparisonOperator": "GREATER_THAN",
      "Threshold": 80,
      "ThresholdType": "PERCENTAGE"
    },
    "Subscribers": [{
      "SubscriptionType": "EMAIL",
      "Address": "your-email@example.com"
    }]
  }]'
```

---

## Maintenance Schedule

### Daily
- [ ] Monitor CloudWatch dashboards
- [ ] Check error logs

### Weekly
- [ ] Review CloudWatch metrics
- [ ] Backup database (if used)

### Monthly
- [ ] Security updates: `sudo apt update && sudo apt upgrade`
- [ ] Review and optimize costs
- [ ] Update application (if needed)

### Quarterly
- [ ] Security audit
- [ ] Performance review
- [ ] Disaster recovery drill

---

## Troubleshooting

### Instance won't connect

```bash
# Check security group
aws ec2 describe-security-groups --group-ids sg-xxxxxxxxx

# Check instance status
aws ec2 describe-instance-status --instance-ids i-xxxxxxxxx

# Reboot instance
aws ec2 reboot-instances --instance-ids i-xxxxxxxxx
```

### Service not responding

```bash
# SSH and check
ssh -i key.pem ubuntu@ip
sudo systemctl status scam-honeypot
sudo journalctl -u scam-honeypot -n 50
```

### Out of disk space

```bash
# Check disk usage
df -h
du -sh /opt/scam-honeypot/*

# Clean up logs
sudo journalctl --vacuum=7d
rm -rf /opt/scam-honeypot/backend/logs/old/*
```

---

## Useful AWS CLI Commands

```bash
# List instances
aws ec2 describe-instances --region us-east-1

# Get instance details
aws ec2 describe-instances --instance-ids i-xxxxxxxxx --query 'Reservations[0].Instances[0]'

# Start/Stop instance
aws ec2 start-instances --instance-ids i-xxxxxxxxx
aws ec2 stop-instances --instance-ids i-xxxxxxxxx

# Modify security group
aws ec2 authorize-security-group-ingress --group-id sg-xxx --protocol tcp --port 443 --cidr 0.0.0.0/0

# Monitor metrics
aws cloudwatch get-metric-statistics --namespace AWS/EC2 --metric-name CPUUtilization --dimensions Name=InstanceId,Value=i-xxxxxxxxx --start-time 2024-01-01T00:00:00Z --end-time 2024-01-02T00:00:00Z --period 3600 --statistics Average
```

---

## Quick Rollback Procedure

```bash
# If deployment fails:

# 1. Stop the service
sudo systemctl stop scam-honeypot

# 2. Check last working commit
cd /opt/scam-honeypot
git log --oneline -n 5

# 3. Revert to last known good
git revert HEAD
git reset --hard <commit-hash>

# 4. Restart service
sudo systemctl start scam-honeypot

# 5. Verify
curl http://localhost:8000/health
```
