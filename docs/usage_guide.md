# Cost Optimization Framework - Usage Guide

## Overview

This guide provides detailed instructions for using the Cost Optimization Framework to monitor, analyze, and optimize your cloud costs across AWS and Azure environments.

## Getting Started

### Accessing the Dashboard

#### Streamlit Dashboard
```bash
# Start the dashboard
cd dashboard
streamlit run dashboard.py

# Access at http://localhost:8501
```

#### Grafana Dashboards
- **URL**: http://localhost:3000
- **Username**: admin
- **Password**: admin (change after first login)

### Key Dashboard Views

#### 1. Cost Overview
- **Total Cost by Service**: Breakdown of costs across AWS/Azure services
- **Cost Trends**: Month-over-month cost analysis
- **Budget vs Actual**: Real-time budget tracking

#### 2. Optimization Opportunities
- **Right-Sizing Recommendations**: Under/over-provisioned resources
- **Idle Resources**: Resources that can be shut down or terminated
- **Unused Storage**: Unattached volumes and old snapshots

#### 3. Resource Inventory
- **Instance Counts**: Running instances by type and region
- **Storage Usage**: Bucket/container sizes and growth trends
- **Database Metrics**: Instance utilization and performance

## Cost Analysis

### Understanding Cost Breakdown

#### By Service
```sql
-- Example Prometheus query for service costs
sum(aws_cost_total) by (service)
sum(azure_cost_total) by (service)
```

#### By Environment
```sql
-- Cost by environment tag
sum(aws_cost_total) by (environment_tag)
sum(azure_cost_total) by (environment_tag)
```

#### By Owner/Team
```sql
-- Cost attribution by owner
sum(aws_cost_total) by (owner_tag)
sum(azure_cost_total) by (owner_tag)
```

### Cost Anomaly Detection

#### Automated Alerts
The framework automatically detects cost anomalies using:
- **Statistical Analysis**: Standard deviation from baseline
- **Trend Analysis**: Unusual spikes or drops
- **Peer Comparison**: Comparison with similar resources

#### Manual Analysis
```python
# Example: Analyze cost anomalies
from monitoring.cost_analysis import CostAnalyzer

analyzer = CostAnalyzer()
anomalies = analyzer.detect_anomalies(
    time_range="30d",
    sensitivity="medium"
)

for anomaly in anomalies:
    print(f"Anomaly: {anomaly['service']} - {anomaly['variance']}% change")
```

## Resource Optimization

### Auto-Shutdown Management

#### Scheduling Shutdowns
```yaml
# Configure auto-shutdown policy
shutdown_policy:
  environments: ["dev", "test"]
  schedule:
    weekdays: "18:00"  # 6 PM
    weekends: "20:00"  # 8 PM
  exclusions:
    - resource_name: "jumpbox-*"
    - tag: "Permanent=true"
```

#### Manual Shutdown
```bash
# AWS Lambda trigger
aws lambda invoke --function-name cost-opt-auto-shutdown \
    --payload '{"action": "shutdown", "environment": "dev"}' \
    response.json

# Azure Function trigger
curl -X POST "https://your-function-url/api/auto-shutdown" \
    -H "Content-Type: application/json" \
    -d '{"action": "shutdown", "resource_group": "dev-rg"}'
```

### Right-Sizing Recommendations

#### Viewing Recommendations
```sql
# Underutilized instances
aws_ec2_cpu_utilization_average < 20 AND up == 1

# Overutilized instances
aws_ec2_cpu_utilization_max > 80 AND up == 1
```

#### Applying Recommendations
```bash
# Generate right-sizing report
python automation/aws-lambda/right_sizing.py --generate-report

# Apply recommendations (dry run first)
python automation/aws-lambda/right_sizing.py --apply --dry-run

# Apply with confirmation
python automation/aws-lambda/right_sizing.py --apply --confirm
```

### Resource Cleanup

#### Automated Cleanup
```yaml
# Cleanup policy configuration
cleanup_policy:
  resources:
    - type: "volumes"
      age_threshold: "30d"
      action: "delete"
    - type: "snapshots"
      age_threshold: "90d"
      action: "delete"
    - type: "images"
      age_threshold: "180d"
      action: "deregister"
```

#### Manual Cleanup
```bash
# Find unattached resources
python automation/aws-lambda/cleanup.py --find-unattached

# Clean up resources (dry run)
python automation/aws-lambda/cleanup.py --cleanup --dry-run

# Clean up with confirmation
python automation/aws-lambda/cleanup.py --cleanup --confirm
```

## Budget Management

### Setting Budgets

#### AWS Budgets
```hcl
# Terraform budget configuration
resource "aws_budgets_budget" "monthly" {
  name         = "monthly-cloud-budget"
  budget_type  = "COST"
  limit_amount = "10000"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_email_addresses = ["finops@company.com"]
  }
}
```

#### Azure Budgets
```hcl
# Terraform budget configuration
resource "azurerm_consumption_budget_resource_group" "example" {
  name              = "monthly-budget"
  resource_group_id = azurerm_resource_group.example.id
  amount            = 10000
  time_grain        = "Monthly"

  notification {
    enabled   = true
    threshold = 80.0
    operator  = "GreaterThan"

    contact_emails = ["finops@company.com"]
  }
}
```

### Budget Alerts

#### Alert Configuration
```yaml
# Budget alert policy
budget_alerts:
  thresholds:
    - percentage: 50
      message: "Budget at 50% utilization"
      channels: ["email"]
    - percentage: 75
      message: "Budget at 75% - review spending"
      channels: ["email", "slack"]
    - percentage: 90
      message: "Budget at 90% - immediate action required"
      channels: ["email", "slack", "sms"]
    - percentage: 100
      message: "Budget exceeded"
      actions: ["shutdown_non_prod"]
```

## Policy Management

### Tagging Policies

#### Enforcing Tags
```yaml
# Tagging compliance policy
tagging_policy:
  required_tags:
    - Owner
    - Environment
    - CostCenter
    - Project

  validation:
    Owner:
      pattern: "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
    Environment:
      values: ["prod", "dev", "test", "staging"]
    CostCenter:
      pattern: "^[A-Z]{2,4}-[0-9]{3,6}$"
```

#### Tag Compliance Reports
```bash
# Generate compliance report
python policies/compliance_checker.py --report tagging

# View non-compliant resources
python policies/compliance_checker.py --find-violations
```

### Shutdown Policies

#### Policy Configuration
```yaml
# Shutdown policy for dev/test
shutdown_policy:
  name: "dev-test-policy"
  environments: ["dev", "test", "staging"]
  schedule:
    weekdays:
      shutdown: "18:00"
      startup: "06:00"
    weekends:
      shutdown: "18:00"
      startup: "09:00"
  exclusions:
    - tag: "AutoShutdown=false"
    - name_pattern: "jumpbox-*"
```

### Budget Policies

#### Threshold Policies
```yaml
# Budget threshold policy
budget_policy:
  name: "cost-threshold-policy"
  budgets:
    - name: "monthly-budget"
      limit: 10000
      thresholds:
        - percent: 75
          action: "notify"
        - percent: 90
          action: "warn"
        - percent: 100
          action: "shutdown"
```

## Reporting and Analytics

### Cost Reports

#### Standard Reports
```bash
# Monthly cost report
python reporting/cost_report.py --period monthly --format pdf

# Cost by team report
python reporting/cost_report.py --group-by owner --period quarterly

# Anomaly report
python reporting/anomaly_report.py --time-range 30d
```

#### Custom Reports
```python
# Custom cost analysis
from reporting.cost_analyzer import CostAnalyzer

analyzer = CostAnalyzer()
report = analyzer.generate_report(
    filters={
        'environment': 'prod',
        'service': 'EC2'
    },
    time_range='90d',
    group_by=['owner', 'project']
)

report.export('custom_cost_report.pdf')
```

### Optimization Reports

#### Savings Reports
```bash
# Potential savings report
python reporting/savings_report.py --type all

# Right-sizing savings
python reporting/savings_report.py --type rightsizing

# Idle resource savings
python reporting/savings_report.py --type idle
```

#### ROI Tracking
```python
# Track optimization ROI
from reporting.roi_tracker import ROITracker

tracker = ROITracker()
roi = tracker.calculate_roi(
    optimization_type='auto_shutdown',
    time_period='6months'
)

print(f"Auto-shutdown ROI: {roi['percentage']}%")
print(f"Monthly savings: ${roi['monthly_savings']}")
```

## Automation and Integration

### API Integration

#### REST API Endpoints
```bash
# Get cost data
curl -X GET "http://localhost:8000/api/costs?period=30d"

# Trigger optimization
curl -X POST "http://localhost:8000/api/optimize" \
    -H "Content-Type: application/json" \
    -d '{"action": "right_size", "dry_run": true}'

# Get recommendations
curl -X GET "http://localhost:8000/api/recommendations"
```

#### Webhook Integration
```yaml
# Webhook configuration
webhooks:
  - event: "budget_threshold_exceeded"
    url: "https://slack-webhook-url"
    payload:
      text: "Budget alert: {{budget_name}} at {{percentage}}%"

  - event: "optimization_applied"
    url: "https://teams-webhook-url"
    payload:
      title: "Optimization Applied"
      text: "{{resource_type}} {{resource_name}} optimized"
```

### CI/CD Integration

#### GitHub Actions
```yaml
# .github/workflows/cost-optimization.yml
name: Cost Optimization Checks

on:
  pull_request:
    branches: [ main ]

jobs:
  cost-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Check Terraform costs
        uses: infracost/actions@v1
        with:
          path: terraform/

      - name: Validate policies
        run: |
          python policies/validator.py
```

### Third-Party Integrations

#### Slack Integration
```python
# Slack notifications
from integrations.slack import SlackNotifier

notifier = SlackNotifier(webhook_url=os.environ['SLACK_WEBHOOK'])

notifier.send_alert(
    channel="#finops",
    message="Budget threshold exceeded",
    color="danger"
)
```

#### ServiceNow Integration
```python
# ServiceNow ticket creation
from integrations.servicenow import ServiceNowClient

sn_client = ServiceNowClient(
    instance=os.environ['SNOW_INSTANCE'],
    username=os.environ['SNOW_USER'],
    password=os.environ['SNOW_PASS']
)

# Create incident for budget overrun
incident = sn_client.create_incident(
    short_description="Cloud Budget Exceeded",
    description="Monthly cloud budget has been exceeded by 15%",
    priority="2"
)
```

## Troubleshooting

### Common Issues

#### Dashboard Not Loading
```bash
# Check Streamlit service
ps aux | grep streamlit

# Restart dashboard
cd dashboard
streamlit run dashboard.py --server.port 8501 --server.headless true
```

#### Missing Metrics
```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Restart exporters
docker-compose restart aws-cost-exporter azure-cost-exporter
```

#### Function Failures
```bash
# Check AWS Lambda logs
aws logs tail /aws/lambda/cost-opt-auto-shutdown --follow

# Check Azure Function logs
az functionapp logs show --name cost-opt-functions --resource-group cost-opt-rg
```

### Performance Optimization

#### Database Queries
```sql
-- Optimize Prometheus queries
# Use rate() instead of increase() for better performance
rate(http_requests_total[5m])

# Use aggregation for large datasets
sum(rate(http_requests_total[5m])) by (service)
```

#### Caching Strategies
```python
# Implement caching for cost data
from cachetools import TTLCache

cache = TTLCache(maxsize=1000, ttl=300)  # 5 minute cache

@cache.cache
def get_cost_data(service, time_range):
    return query_cost_explorer(service, time_range)
```

## Best Practices

### Cost Optimization

#### 1. Regular Reviews
- **Weekly**: Review cost anomalies and alerts
- **Monthly**: Analyze optimization opportunities
- **Quarterly**: Review budget performance and adjust forecasts

#### 2. Policy Updates
- Keep policies current with business requirements
- Regularly review and update tagging standards
- Adjust thresholds based on actual spending patterns

#### 3. Team Engagement
- Share cost reports with development teams
- Provide training on cost optimization practices
- Recognize and reward cost-saving initiatives

### Security Considerations

#### Access Control
- Implement least privilege for all service accounts
- Regularly rotate API keys and credentials
- Use MFA for all administrative access

#### Data Protection
- Encrypt sensitive configuration data
- Implement audit logging for all cost-related actions
- Regular security assessments of the framework

### Monitoring Framework Health

#### Health Checks
```bash
# Framework health check
curl http://localhost:8000/health

# Component status
curl http://localhost:9090/-/healthy  # Prometheus
curl http://localhost:3000/api/health  # Grafana
```

#### Alerting on Framework Issues
```yaml
# Framework monitoring alerts
framework_alerts:
  - name: "exporter_down"
    condition: up{job="aws-cost-exporter"} == 0
    message: "AWS Cost Exporter is down"

  - name: "function_failures"
    condition: rate(lambda_errors_total[5m]) > 0.1
    message: "High Lambda function error rate"
```

## Advanced Usage

### Custom Metrics and Alerts

#### Creating Custom Dashboards
```json
// Custom Grafana panel
{
  "title": "Custom Cost Efficiency",
  "type": "stat",
  "targets": [
    {
      "expr": "sum(rate(aws_cost_total[30d])) / sum(rate(aws_resource_count[30d]))",
      "legendFormat": "Cost per Resource"
    }
  ]
}
```

#### Custom Automation Rules
```python
# Custom optimization rule
def custom_optimization_rule(resource):
    """
    Custom logic for specific resource types
    """
    if resource['type'] == 'rds' and resource['cpu'] < 10:
        return {
            'action': 'downsize',
            'target_instance_class': 'db.t3.micro',
            'estimated_savings': calculate_rds_savings(resource)
        }
    return None
```

### Integration with Enterprise Systems

#### ERP Integration
```python
# SAP integration example
from integrations.sap import SAPClient

sap_client = SAPClient(
    server=os.environ['SAP_SERVER'],
    client=os.environ['SAP_CLIENT']
)

# Sync cost data to SAP
sap_client.post_cost_data(cost_data)
```

#### CMDB Integration
```python
# ServiceNow CMDB integration
from integrations.cmdb import CMDBClient

cmdb_client = CMDBClient()

# Update resource ownership
cmdb_client.update_resource_owner(
    resource_id='i-1234567890abcdef0',
    owner='john.doe@company.com',
    cost_center='ENG-123'
)
```

## Support and Resources

### Getting Help
- **Documentation**: Check the docs/ directory for detailed guides
- **GitHub Issues**: Report bugs and request features
- **Community Forum**: Share experiences and best practices
- **Professional Services**: Contact for implementation assistance

### Training Resources
- **FinOps Training**: Online courses and certifications
- **Cloud Cost Management**: AWS and Azure cost optimization guides
- **Framework Tutorials**: Video walkthroughs and examples

---

This usage guide provides comprehensive instructions for effectively using the Cost Optimization Framework. Regular review and updates will ensure continued effectiveness in managing cloud costs.
