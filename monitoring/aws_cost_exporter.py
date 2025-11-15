"""
AWS Cost Exporter for Prometheus
Exports AWS cost and usage metrics to Prometheus
"""

import boto3
import time
from datetime import datetime, timedelta
from prometheus_client import start_http_server, Gauge, Counter, Histogram
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AWS Configuration
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Prometheus metrics
cost_gauge = Gauge('aws_cost_total', 'Total AWS cost by service', ['service', 'region'])
budget_gauge = Gauge('aws_budget_limit', 'AWS budget limits', ['budget_name'])
budget_spent_gauge = Gauge('aws_budget_spent', 'AWS budget spent amount', ['budget_name'])
resource_count_gauge = Gauge('aws_resource_count', 'Count of AWS resources by type', ['resource_type', 'region'])

# Cost Explorer client
ce = boto3.client('ce', region_name=AWS_REGION)
budgets = boto3.client('budgets', region_name=AWS_REGION)

def get_cost_by_service(start_date: str, end_date: str) -> dict:
    """Get cost breakdown by AWS service"""
    try:
        response = ce.get_cost_and_usage(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Granularity='DAILY',
            Metrics=['BlendedCost'],
            GroupBy=[
                {
                    'Type': 'DIMENSION',
                    'Key': 'SERVICE'
                }
            ]
        )

        costs = {}
        for group in response['ResultsByTime'][0]['Groups']:
            service = group['Keys'][0]
            amount = float(group['Metrics']['BlendedCost']['Amount'])
            costs[service] = amount

        return costs

    except Exception as e:
        logger.error(f"Error getting cost by service: {e}")
        return {}

def get_budget_info() -> list:
    """Get AWS budget information"""
    try:
        budgets_list = []
        response = budgets.describe_budgets()

        for budget in response['Budgets']:
            budget_name = budget['BudgetName']
            limit = float(budget['BudgetLimit']['Amount'])
            spent = 0.0

            # Get actual spend
            if 'CalculatedSpend' in budget:
                spent = float(budget['CalculatedSpend']['ActualSpend']['Amount'])

            budgets_list.append({
                'name': budget_name,
                'limit': limit,
                'spent': spent
            })

        return budgets_list

    except Exception as e:
        logger.error(f"Error getting budget info: {e}")
        return []

def get_resource_counts() -> dict:
    """Get counts of various AWS resources"""
    try:
        # EC2 instances
        ec2 = boto3.client('ec2', region_name=AWS_REGION)
        instances = ec2.describe_instances()
        running_instances = 0
        for reservation in instances['Reservations']:
            for instance in reservation['Instances']:
                if instance['State']['Name'] == 'running':
                    running_instances += 1

        # S3 buckets
        s3 = boto3.client('s3', region_name=AWS_REGION)
        buckets = s3.list_buckets()
        bucket_count = len(buckets['Buckets'])

        # RDS instances
        rds = boto3.client('rds', region_name=AWS_REGION)
        db_instances = rds.describe_db_instances()
        db_count = len(db_instances['DBInstances'])

        return {
            'ec2_instances': running_instances,
            's3_buckets': bucket_count,
            'rds_instances': db_count
        }

    except Exception as e:
        logger.error(f"Error getting resource counts: {e}")
        return {}

def update_metrics():
    """Update all Prometheus metrics"""
    try:
        # Get date range (last 30 days)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')

        # Update cost metrics
        costs = get_cost_by_service(start_str, end_str)
        for service, cost in costs.items():
            cost_gauge.labels(service=service, region=AWS_REGION).set(cost)

        # Update budget metrics
        budget_info = get_budget_info()
        for budget in budget_info:
            budget_gauge.labels(budget_name=budget['name']).set(budget['limit'])
            budget_spent_gauge.labels(budget_name=budget['name']).set(budget['spent'])

        # Update resource counts
        resource_counts = get_resource_counts()
        for resource_type, count in resource_counts.items():
            resource_count_gauge.labels(resource_type=resource_type, region=AWS_REGION).set(count)

        logger.info("Metrics updated successfully")

    except Exception as e:
        logger.error(f"Error updating metrics: {e}")

def main():
    """Main function to run the exporter"""
    # Start Prometheus HTTP server
    port = int(os.environ.get('PORT', 8080))
    start_http_server(port)
    logger.info(f"AWS Cost Exporter started on port {port}")

    # Update metrics every 5 minutes
    while True:
        update_metrics()
        time.sleep(300)  # 5 minutes

if __name__ == "__main__":
    main()
