# Lurnexa HRMS

Lurnexa HRMS is an enterprise-grade Human Resource Management System built with Python Django and Amazon DynamoDB.

## Architecture Highlights
- **100% DynamoDB:** Bypasses Django's standard SQL ORM and relies purely on `boto3` queries.
- **Custom Authentication:** Session management mapped to DynamoDB Users table.
- **Role-Based Access Control (RBAC):** Strict boundaries for HR, Managers, and Employees.
- **Enterprise Design:** Bootstrap 5 with a custom professional white/blue theme.

## Setup Instructions

### 1. Prerequisites
- Python 3.10+
- AWS Account or Local DynamoDB (`amazon/dynamodb-local`)
- Virtual Environment

### 2. Installation
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Setup
Copy `.env.example` to `.env` and fill out your AWS credentials.
If running DynamoDB locally, set `DYNAMODB_ENDPOINT_URL=http://localhost:8000`.

### 4. DynamoDB Initialization
This project automatically creates required tables if they don't exist:
```bash
python manage.py init_dynamo
python manage.py init_demo_users
```

### 5. Running Locally
```bash
python manage.py runserver
```

## Demo Accounts
- HR: `hr@lurnexa.com`
- Manager: `manager@lurnexa.com`
- Employee: `employee@lurnexa.com`
**Password:** `Password@123`

## Deployment to AWS EC2 (Ubuntu)
1. Clone repository to `/home/ubuntu/lurnexa_hrms`
2. Run installation steps above.
3. Configure Gunicorn: `sudo cp gunicorn.service /etc/systemd/system/`
4. Configure Nginx: `sudo cp nginx.conf /etc/nginx/sites-available/lurnexa`
5. Enable services:
```bash
sudo systemctl start gunicorn
sudo systemctl enable gunicorn
sudo ln -s /etc/nginx/sites-available/lurnexa /etc/nginx/sites-enabled
sudo systemctl restart nginx
```
6. Ensure your EC2 Instance Profile has DynamoDB Full Access or provide `.env` keys.
