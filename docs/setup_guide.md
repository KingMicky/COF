# Cost Optimization Framework - Setup Guide

## Prerequisites

Before deploying the Cost Optimization Framework, ensure you have the following:

### Required Tools
- **Terraform** (>= 1.0): Infrastructure as Code
- **Python** (>= 3.8): For automation functions and exporters
- **Docker** (>= 20.0): For containerized monitoring stack
- **AWS CLI** (>= 2.0): For AWS operations
- **Azure CLI** (>= 2.0): For Azure operations

### Cloud Provider Access
- **AWS**: IAM user/role with appropriate permissions
- **Azure**: Service principal with contributor access

### Required Permissions

#### AWS Permissions
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ce:GetCostAndUsage",
                "ce:GetReservationCoverage",
                "ce:GetReservationPurchaseRecommendation",
                "ec2:DescribeInstances",
                "ec2:DescribeVolumes",
                "ec2:DescribeSnapshots",
                "rds:DescribeDBInstances",
                "s3:ListAllMyBuckets",
                "s3:GetBucketLocation",
                "lambda:CreateFunction",
                "lambda:InvokeFunction",
                "cloudwatch:*",
                "budgets:*",
                "organizations:ListPolicies",
                "organizations:DescribePolicy"
            ],
            "Resource": "*"
        }
    ]
}
```

#### Azure Permissions
```json
{
    "permissions": [
        {
            "actions": [
                "Microsoft.CostManagement/exports/read",
                "Microsoft.CostManagement/exports/write",
                "Microsoft.CostManagement/exports/delete",
                "Microsoft.CostManagement/query/read",
                "Microsoft.Compute/virtualMachines/read",
                "Microsoft.Compute/virtualMachines/write",
                "Microsoft.Compute/virtualMachineScaleSets/read",
                "Microsoft.Compute/virtualMachineScaleSets/write",
                "Microsoft.Network/virtualNetworks/read",
                "Microsoft.Resources/subscriptions/resourceGroups/read",
                "Microsoft.Storage/storageAccounts/read",
                "Microsoft.Sql/servers/read",
                "Microsoft.Sql/databases/read"
            ],
            "notActions": [],
            "dataActions": [],
            "notDataActions": []
        }
    ]
}
```

## Quick Start Deployment

### 1. Clone the Repository
```bash
git clone https://github.com/your-org/cost-optimization-framework.git
cd cost-optimization-framework
```

### 2. Configure Environment Variables

#### AWS Configuration
```bash
export AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
```

#### Azure Configuration
```bash
export AZURE_TENANT_ID=your-tenant-id
export AZURE_CLIENT_ID=your-client-id
export AZURE_CLIENT_SECRET=your-client-secret
export AZURE_SUBSCRIPTION_ID=your-subscription-id
```

### 3. Initialize Terraform
```bash
cd terraform/aws  # or terraform/azure
terraform init
```

### 4. Plan Deployment
```bash
terraform plan -var-file=terraform.tfvars
```

### 5. Deploy Infrastructure
```bash
terraform apply -var-file=terraform.tfvars
```

## Detailed Setup by Component

### Infrastructure Deployment

#### AWS Setup
```hcl
# terraform/aws/terraform.tfvars
aws_region = "us-east-1"
environment = "dev"
vpc_id = "vpc-12345678"
subnet_ids = ["subnet-12345678", "subnet-87654321"]

# Cost optimization settings
auto_shutdown_enabled = true
shutdown_schedule = "0 18 * * 1-5"  # 6 PM weekdays
budget_limit = 1000
alert_email = "finops@company.com"
```

#### Azure Setup
```hcl
# terraform/azure/terraform.tfvars
location = "East US"
environment = "dev"
resource_group_name = "cost-opt-rg"
vnet_id = "/subscriptions/.../virtualNetworks/vnet"
subnet_id = "/subscriptions/.../subnets/subnet"

# Cost optimization settings
auto_shutdown_enabled = true
shutdown_schedule = "0 18 * * 1-5"
budget_limit = 1000
alert_email = "finops@company.com"
```

### Automation Functions Setup

#### AWS Lambda Functions
```bash
# Deploy Lambda functions
cd automation/aws-lambda
pip install -r requirements.txt

# Package and deploy (or use Terraform automation)
zip -r lambda-package.zip .
aws lambda create-function --function-name cost-opt-auto-shutdown \
    --runtime python3.8 \
    --role arn:aws:iam::account:role/lambda-role \
    --handler auto_shutdown.lambda_handler \
    --zip-file fileb://lambda-package.zip
```

#### Azure Functions
```bash
# Deploy Azure Functions
cd automation/azure-functions
pip install -r requirements.txt

# Deploy using Azure CLI
az functionapp create --resource-group cost-opt-rg \
    --consumption-plan-location "East US" \
    --runtime python \
    --runtime-version 3.8 \
    --functions-version 4 \
    --name cost-opt-functions \
    --storage-account costoptstorage

# Deploy functions
func azure functionapp publish cost-opt-functions
```

### Monitoring Stack Setup

#### Using Docker Compose
```bash
cd monitoring
docker-compose up -d
```

#### Manual Setup
```bash
# Start Prometheus
docker run -d -p 9090:9090 \
    -v $(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml \
    prom/prometheus

# Start Grafana
docker run -d -p 3000:3000 \
    -e GF_SECURITY_ADMIN_PASSWORD=admin \
    grafana/grafana

# Start cost exporters
docker build -t aws-cost-exporter -f Dockerfile.aws .
docker run -d -p 8080:8080 \
    -e AWS_REGION=us-east-1 \
    aws-cost-exporter

docker build -t azure-cost-exporter -f Dockerfile.azure .
docker run -d -p 8081:8080 \
    -e AZURE_TENANT_ID=... \
    azure-cost-exporter
```

### Dashboard Setup

#### Streamlit Dashboard
```bash
cd dashboard
pip install -r requirements.txt
streamlit run dashboard.py --server.port 8501
```

#### Grafana Dashboards
1. Access Grafana at http://localhost:3000
2. Login with admin/admin
3. Add Prometheus as data source
4. Import dashboards from `monitoring/grafana/dashboards/`

## Configuration Files

### Terraform Variables

#### Common Variables
```hcl
# terraform.tfvars
environment = "dev"
owner = "platform-team"
cost_center = "engineering"
project = "cost-optimization"

# Tagging
mandatory_tags = {
  Owner = "platform-team@company.com"
  Environment = "dev"
  CostCenter = "ENG-123"
  Project = "cost-opt-framework"
}

# Cost optimization
auto_shutdown = true
shutdown_schedule = "0 18 * * 1-5"
budget_alerts = true
budget_limit = 5000
alert_emails = ["finops@company.com", "engineering@company.com"]
```

### Environment Configuration

#### .env File
```bash
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret

# Azure Configuration
AZURE_TENANT_ID=your-tenant
AZURE_CLIENT_ID=your-client
AZURE_CLIENT_SECRET=your-secret
AZURE_SUBSCRIPTION_ID=your-subscription

# Monitoring
PROMETHEUS_URL=http://localhost:9090
GRAFANA_URL=http://localhost:3000

# Application
LOG_LEVEL=INFO
DRY_RUN=true
```

## Policy Configuration

### Tagging Policies
```yaml
# policies/tagging/compliance.yaml
apiVersion: v1
kind: TaggingPolicy
metadata:
  name: cost-optimization-tagging

spec:
  requiredTags:
    - name: Owner
      validation:
        pattern: "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
    - name: Environment
      allowedValues: ["prod", "dev", "test", "staging"]
    - name: CostCenter
      pattern: "^[A-Z]{2,4}-[0-9]{3,6}$"
    - name: Project

  enforcement:
    mode: "audit"  # Change to "deny" for strict enforcement
```

### Shutdown Policies
```yaml
# policies/shutdown/dev-test-policy.yaml
apiVersion: v1
kind: ShutdownPolicy
metadata:
  name: dev-test-auto-shutdown

spec:
  environments: ["dev", "test", "staging"]
  schedule:
    timezone: "UTC"
    weekdays:
      shutdownTime: "18:00"
      startupTime: "06:00"
    weekends:
      shutdownTime: "18:00"
      startupTime: "09:00"

  exclusions:
    tags:
      - key: "AutoShutdown"
        value: "false"
      - key: "Critical"
        value: "true"
```

### Budget Policies
```yaml
# policies/budgets/threshold-policy.yaml
apiVersion: v1
kind: BudgetPolicy
metadata:
  name: cost-threshold-alerts

spec:
  budgets:
    - name: "monthly-budget"
      amount: 10000
      period: "monthly"

  thresholds:
    - percentage: 75
      actions:
        - type: "notification"
          channels: ["email", "slack"]
    - percentage: 90
      actions:
        - type: "shutdown"
          resources: ["dev", "test"]
```

## Testing the Deployment

### Infrastructure Tests
```bash
# Validate Terraform
terraform validate

# Run security checks
terraform plan -out=tfplan.binary
terraform show -json tfplan.binary | jq . > tfplan.json
checkov -f tfplan.json

# Test connectivity
aws ec2 describe-instances --region us-east-1
az vm list --resource-group cost-opt-rg
```

### Function Tests
```bash
# Test Lambda functions
aws lambda invoke --function-name cost-opt-auto-shutdown \
    --payload '{}' response.json

# Test Azure Functions
curl -X POST "https://cost-opt-functions.azurewebsites.net/api/auto-shutdown" \
    -H "Content-Type: application/json" \
    -d "{}"
```

### Monitoring Tests
```bash
# Test Prometheus
curl http://localhost:9090/api/v1/query?query=up

# Test Grafana
curl http://localhost:3000/api/health

# Test cost exporters
curl http://localhost:8080/metrics  # AWS
curl http://localhost:8081/metrics  # Azure
```

## Troubleshooting

### Common Issues

#### Terraform Issues
```bash
# Clear Terraform cache
rm -rf .terraform/
terraform init

# Debug Terraform
export TF_LOG=DEBUG
terraform apply
```

#### Permission Issues
```bash
# Test AWS credentials
aws sts get-caller-identity

# Test Azure credentials
az account show
```

#### Function Deployment Issues
```bash
# Check Lambda logs
aws logs tail /aws/lambda/cost-opt-auto-shutdown --follow

# Check Azure Function logs
az functionapp logs show --name cost-opt-functions --resource-group cost-opt-rg
```

### Monitoring Issues
```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Check Grafana logs
docker logs grafana

# Restart monitoring stack
docker-compose down
docker-compose up -d
```

## Next Steps

### Post-Deployment Configuration
1. **Customize Policies**: Adjust policies based on your organization's requirements
2. **Set Up Alerts**: Configure notification channels and thresholds
3. **User Training**: Train teams on cost optimization practices
4. **Integration**: Connect with existing tools and processes

### Ongoing Maintenance
1. **Monitor Performance**: Regularly review framework effectiveness
2. **Update Policies**: Keep policies current with business changes
3. **Cost Analysis**: Review optimization results and ROI
4. **Security Updates**: Keep all components updated and secure

### Advanced Configuration
1. **Multi-Environment**: Deploy to additional environments
2. **CI/CD Integration**: Automate deployment and testing
3. **Custom Dashboards**: Create organization-specific views
4. **Integration APIs**: Connect with existing enterprise systems

## Support and Resources

### Documentation
- [Architecture Guide](architecture.md)
- [FinOps Principles](finops_principles.md)
- [Usage Guide](usage_guide.md)

### Community Resources
- GitHub Issues: Report bugs and request features
- Discussions: Share experiences and best practices
- Wiki: Community-contributed guides and examples

### Professional Services
- Implementation assistance
- Custom policy development
- Integration consulting
- Training and enablement

---

For additional support, please contact the platform team or create an issue in the GitHub repository.
