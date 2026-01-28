"""
AWS Cost Exporter for Prometheus
Exports AWS cost and usage metrics to Prometheus
"""

import logging
import os
import time
from datetime import datetime, timedelta

import boto3
from prometheus_client import Counter, Gauge, Histogram, start_http_server

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


cost_gauge = Gauge("aws_cost_total", "Total AWS cost by service", ["service", "region"])
budget_gauge = Gauge("aws_budget_limit", "AWS budget limits", ["budget_name"])
budget_spent_gauge = Gauge(
    "aws_budget_spent", "AWS budget spent amount", ["budget_name"]
)
resource_count_gauge = Gauge(
    "aws_resource_count", "Count of AWS resources by type", ["resource_type", "region"]
)


ce = boto3.client("ce", region_name=AWS_REGION)
budgets = boto3.client("budgets", region_name=AWS_REGION)


def get_cost_by_service(start_date: str, end_date: str) -> dict:
    """Get cost breakdown by AWS service"""
    try:
        response = ce.get_cost_and_usage(
            TimePeriod={"Start": start_date, "End": end_date},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        costs = {}
        for group in response["ResultsByTime"][0]["Groups"]:
            service = group["Keys"][0]
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            costs[service] = amount

        return costs

    except Exception as e:
        logger.error(f"Error getting cost by service: {e}")
        return {}


def get_budget_info() -> list:
    """Get AWS budget information"""
    try:
        budgets_list = []
        paginator = budgets.get_paginator("describe_budgets")
        account_id = os.environ.get("AWS_ACCOUNT_ID")
        pages = paginator.paginate(AccountId=account_id)
        for page in pages:
            for budget in page["Budgets"]:
                budget_name = budget["BudgetName"]
                limit = float(budget["BudgetLimit"]["Amount"])
                spent = 0.0

                if "CalculatedSpend" in budget:
                    spent = float(budget["CalculatedSpend"]["ActualSpend"]["Amount"])

                budgets_list.append(
                    {"name": budget_name, "limit": limit, "spent": spent}
                )

        return budgets_list

    except Exception as e:
        logger.error(f"Error getting budget info: {e}")
        return []


def get_resource_counts() -> dict:
    """Get counts of various AWS resources"""
    try:
        ec2 = boto3.client("ec2", region_name=AWS_REGION)
        paginator = ec2.get_paginator("describe_instances")
        pages = paginator.paginate(
            Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
        )
        running_instances = 0
        for page in pages:
            for reservation in page["Reservations"]:
                running_instances += len(reservation["Instances"])

        s3 = boto3.client("s3", region_name=AWS_REGION)
        buckets = s3.list_buckets()
        bucket_count = len(buckets["Buckets"])

        rds = boto3.client("rds", region_name=AWS_REGION)
        paginator = rds.get_paginator("describe_db_instances")
        pages = paginator.paginate()
        db_count = 0
        for page in pages:
            db_count += len(page["DBInstances"])

        return {
            "ec2_instances": running_instances,
            "s3_buckets": bucket_count,
            "rds_instances": db_count,
        }

    except Exception as e:
        logger.error(f"Error getting resource counts: {e}")
        return {}


def update_metrics():
    """Update all Prometheus metrics"""
    try:
        time_period_days = int(os.environ.get("COST_METRICS_TIME_PERIOD_DAYS", "30"))
        end_date = datetime.now()
        start_date = end_date - timedelta(days=time_period_days)

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        costs = get_cost_by_service(start_str, end_str)
        for service, cost in costs.items():
            cost_gauge.labels(service=service, region=AWS_REGION).set(cost)

        budget_info = get_budget_info()
        for budget in budget_info:
            budget_gauge.labels(budget_name=budget["name"]).set(budget["limit"])
            budget_spent_gauge.labels(budget_name=budget["name"]).set(budget["spent"])

        resource_counts = get_resource_counts()
        for resource_type, count in resource_counts.items():
            resource_count_gauge.labels(
                resource_type=resource_type, region=AWS_REGION
            ).set(count)

        logger.info("Metrics updated successfully")

    except Exception as e:
        logger.error(f"Error updating metrics: {e}")


def main():
    """Main function to run the exporter"""

    port = int(os.environ.get("PORT", 8080))
    start_http_server(port)
    logger.info(f"AWS Cost Exporter started on port {port}")

    while True:
        update_metrics()
        time.sleep(300)


if __name__ == "__main__":
    main()
