"""
Cost Optimization Dashboard
Web dashboard for visualizing cost optimization metrics and recommendations
"""

import json
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import boto3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from monitoring.azure_client import AzureClient

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


cloudwatch = boto3.client("cloudwatch", region_name=AWS_REGION)
ce = boto3.client("ce", region_name=AWS_REGION)


def main():
    st.set_page_config(
        page_title="Cost Optimization Dashboard", page_icon="💰", layout="wide"
    )

    st.title("💰 Cost Optimization Framework Dashboard")

    st.sidebar.header("Filters")

    date_range = st.sidebar.selectbox(
        "Time Range",
        ["Last 7 days", "Last 30 days", "Last 90 days", "Last year"],
        index=1,
    )

    cloud_provider = st.sidebar.selectbox(
        "Cloud Provider", ["AWS", "Azure", "Both"], index=0
    )

    environment = st.sidebar.multiselect(
        "Environment", ["dev", "staging", "prod"], default=["dev", "staging", "prod"]
    )

    start_date, end_date = get_date_range(date_range)

    azure_client = AzureClient()

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📊 Cost Overview",
            "🔍 Resource Utilization",
            "💡 Recommendations",
            "⚙️ Settings",
        ]
    )

    with tab1:
        show_cost_overview(
            start_date, end_date, cloud_provider, environment, azure_client
        )

    with tab2:
        show_resource_utilization(
            start_date, end_date, cloud_provider, environment, azure_client
        )

    with tab3:
        show_recommendations(cloud_provider, environment)

    with tab4:
        show_settings()


def get_date_range(date_range: str) -> tuple:
    """Get start and end dates based on selection"""
    end_date = datetime.now()
    if date_range == "Last 7 days":
        start_date = end_date - timedelta(days=7)
    elif date_range == "Last 30 days":
        start_date = end_date - timedelta(days=30)
    elif date_range == "Last 90 days":
        start_date = end_date - timedelta(days=90)
    else:
        start_date = end_date - timedelta(days=365)

    return start_date.date(), end_date.date()


def show_cost_overview(start_date, end_date, cloud_provider, environment, azure_client):
    """Display cost overview dashboard"""
    st.header("Cost Overview")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Cost", "$12,450", "+5.2%")

    with col2:
        st.metric("Compute Cost", "$8,200", "+3.1%")

    with col3:
        st.metric("Storage Cost", "$2,800", "-2.4%")

    with col4:
        st.metric("Database Cost", "$1,450", "+8.7%")

    st.subheader("Cost Trend")
    cost_data = get_cost_trend_data(start_date, end_date, cloud_provider, azure_client)
    fig = px.line(cost_data, x="Date", y="Cost", title="Daily Cost Trend")
    st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Cost by Service")
        service_cost_data = get_service_cost_data(
            start_date, end_date, cloud_provider, azure_client
        )
        fig = px.pie(
            service_cost_data,
            values="Cost",
            names="Service",
            title="Cost Distribution by Service",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Cost by Environment")
        env_cost_data = get_environment_cost_data(
            start_date, end_date, environment, cloud_provider, azure_client
        )
        fig = px.bar(
            env_cost_data, x="Environment", y="Cost", title="Cost by Environment"
        )
        st.plotly_chart(fig, use_container_width=True)


def show_resource_utilization(
    start_date, end_date, cloud_provider, environment, azure_client
):
    """Display resource utilization metrics"""
    st.header("Resource Utilization")

    st.subheader("CPU Utilization Trends")
    cpu_data = get_cpu_utilization_data(
        start_date, end_date, cloud_provider, azure_client
    )
    fig = px.line(
        cpu_data,
        x="Timestamp",
        y="CPUUtilization",
        color="InstanceId",
        title="CPU Utilization Over Time",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Memory Utilization Trends")
    memory_data = get_memory_utilization_data(
        start_date, end_date, cloud_provider, azure_client
    )
    if not memory_data.empty:
        fig = px.line(
            memory_data,
            x="Timestamp",
            y="MemoryUtilization",
            color="InstanceId",
            title="Memory Utilization Over Time",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Memory utilization data not available for all instances")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Storage Utilization")
        storage_data = get_storage_utilization_data(cloud_provider, azure_client)
        fig = px.bar(
            storage_data,
            x="Bucket",
            y="Utilization",
            title="Storage Bucket Utilization (%)",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Database Connections")
        db_connections_data = get_db_connections_data(
            start_date, end_date, cloud_provider, azure_client
        )
        fig = px.line(
            db_connections_data,
            x="Timestamp",
            y="Connections",
            color="Database",
            title="Database Connections Over Time",
        )
        st.plotly_chart(fig, use_container_width=True)


def show_recommendations(cloud_provider, environment, azure_client):
    """Display cost optimization recommendations"""
    st.header("Optimization Recommendations")

    recommendations = get_recommendations(cloud_provider, environment, azure_client)

    if recommendations:
        total_savings = sum(rec["potential_savings"] for rec in recommendations)
        st.metric("Total Potential Savings", f"${total_savings:,.2f}")

        st.subheader("Detailed Recommendations")

        df = pd.DataFrame(recommendations)
        df["potential_savings"] = df["potential_savings"].apply(lambda x: f"${x:,.2f}")

        st.dataframe(df, use_container_width=True)

        st.subheader("Recommendations by Category")
        category_data = (
            df.groupby("category")
            .agg({"potential_savings": "sum", "resource_id": "count"})
            .reset_index()
        )
        category_data.columns = ["Category", "Total Savings", "Count"]

        fig = px.bar(
            category_data,
            x="Category",
            y="Total Savings",
            title="Potential Savings by Category",
        )
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("No recommendations available at this time.")


def show_settings():
    """Display settings and configuration"""
    st.header("Settings")

    try:
        with open("monitoring/settings.json", "r") as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        settings = {}

    st.subheader("Dashboard Configuration")

    refresh_interval = st.selectbox(
        "Auto-refresh interval",
        ["Off", "30 seconds", "1 minute", "5 minutes"],
        index=["Off", "30 seconds", "1 minute", "5 minutes"].index(
            settings.get("auto_refresh_interval", "Off")
        ),
    )

    st.subheader("Alert Thresholds")

    cpu_threshold = st.slider(
        "CPU utilization alert threshold (%)", 0, 100, settings.get("cpu_threshold", 80)
    )
    memory_threshold = st.slider(
        "Memory utilization alert threshold (%)",
        0,
        100,
        settings.get("memory_threshold", 80),
    )
    cost_threshold = st.slider(
        "Cost increase alert threshold (%)",
        0,
        100,
        settings.get("cost_threshold", 20),
    )

    st.subheader("Notifications")

    email_notifications = st.checkbox(
        "Email notifications", value=settings.get("email_notifications", True)
    )
    slack_notifications = st.checkbox(
        "Slack notifications", value=settings.get("slack_notifications", False)
    )

    if email_notifications:
        alert_email = st.text_input(
            "Alert email address",
            value=settings.get("alert_email", "admin@example.com"),
        )

    if slack_notifications:
        slack_webhook = st.text_input(
            "Slack webhook URL",
            type="password",
            value=settings.get("slack_webhook", ""),
        )

    if st.button("Save Settings"):
        settings = {
            "auto_refresh_interval": refresh_interval,
            "cpu_threshold": cpu_threshold,
            "memory_threshold": memory_threshold,
            "cost_threshold": cost_threshold,
            "email_notifications": email_notifications,
            "slack_notifications": slack_notifications,
            "alert_email": alert_email,
            "slack_webhook": slack_webhook,
        }
        with open("monitoring/settings.json", "w") as f:
            json.dump(settings, f, indent=4)
        st.success("Settings saved successfully!")

    # Auto-refresh logic
    if refresh_interval != "Off":
        interval_seconds = {
            "30 seconds": 30,
            "1 minute": 60,
            "5 minutes": 300,
        }[refresh_interval]
        time.sleep(interval_seconds)
        st.experimental_rerun()


def get_cost_trend_data(start_date, end_date, cloud_provider, azure_client):
    """Get cost trend data from AWS Cost Explorer or Azure Cost Management"""
    data = []
    if cloud_provider in ["AWS", "Both"]:
        try:
            response = ce.get_cost_and_usage(
                TimePeriod={"Start": str(start_date), "End": str(end_date)},
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
            )
            for item in response["ResultsByTime"]:
                data.append(
                    {
                        "Date": item["TimePeriod"]["Start"],
                        "Cost": float(item["Total"]["UnblendedCost"]["Amount"]),
                        "Provider": "AWS",
                    }
                )
        except Exception as e:
            st.error(f"Error getting AWS cost trend data: {e}")

    if cloud_provider in ["Azure", "Both"]:
        try:
            response = azure_client.get_cost_and_usage(
                str(start_date), str(end_date), "Daily"
            )
            if response and "properties" in response:
                for row in response["properties"]["rows"]:
                    data.append({"Date": row[1], "Cost": row[0], "Provider": "Azure"})
        except Exception as e:
            st.error(f"Error getting Azure cost trend data: {e}")

    return pd.DataFrame(data)


def get_service_cost_data(start_date, end_date, cloud_provider, azure_client):
    """Get cost breakdown by service"""
    data = []
    if cloud_provider in ["AWS", "Both"]:
        try:
            response = ce.get_cost_and_usage(
                TimePeriod={"Start": str(start_date), "End": str(end_date)},
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )
            for item in response["ResultsByTime"][0]["Groups"]:
                data.append(
                    {
                        "Service": item["Keys"][0],
                        "Cost": float(item["Metrics"]["UnblendedCost"]["Amount"]),
                        "Provider": "AWS",
                    }
                )
        except Exception as e:
            st.error(f"Error getting AWS service cost data: {e}")

    if cloud_provider in ["Azure", "Both"]:
        try:
            response = azure_client.get_cost_and_usage(
                str(start_date),
                str(end_date),
                "None",
                [{"Type": "Dimension", "Name": "ServiceName"}],
            )
            if response and "properties" in response:
                for row in response["properties"]["rows"]:
                    data.append(
                        {"Service": row[1], "Cost": row[0], "Provider": "Azure"}
                    )
        except Exception as e:
            st.error(f"Error getting Azure service cost data: {e}")

    return pd.DataFrame(data)


def get_environment_cost_data(
    start_date, end_date, environments, cloud_provider, azure_client
):
    """Get cost breakdown by environment"""
    data = []
    if cloud_provider in ["AWS", "Both"]:
        try:
            response = ce.get_cost_and_usage(
                TimePeriod={"Start": str(start_date), "End": str(end_date)},
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "TAG", "Key": "Environment"}],
                Filter={
                    "Tags": {
                        "Key": "Environment",
                        "Values": environments,
                        "MatchOptions": ["EQUALS"],
                    }
                },
            )
            for item in response["ResultsByTime"][0]["Groups"]:
                data.append(
                    {
                        "Environment": item["Keys"][0].split("$")[1],
                        "Cost": float(item["Metrics"]["UnblendedCost"]["Amount"]),
                        "Provider": "AWS",
                    }
                )
        except Exception as e:
            st.error(f"Error getting AWS environment cost data: {e}")

    if cloud_provider in ["Azure", "Both"]:
        try:
            filter_payload = {
                "Dimensions": {"Name": "tag", "Operator": "In", "Values": environments}
            }
            response = azure_client.get_cost_and_usage(
                str(start_date),
                str(end_date),
                "None",
                [{"Type": "Dimension", "Name": "tag"}],
                filter_payload,
            )
            if response and "properties" in response:
                for row in response["properties"]["rows"]:
                    data.append(
                        {"Environment": row[1], "Cost": row[0], "Provider": "Azure"}
                    )
        except Exception as e:
            st.error(f"Error getting Azure environment cost data: {e}")

    return pd.DataFrame(data)


def get_cpu_utilization_data(start_date, end_date, cloud_provider, azure_client):
    """Get CPU utilization data"""
    data = []
    if cloud_provider in ["AWS", "Both"]:
        try:
            ec2 = boto3.client("ec2", region_name=AWS_REGION)
            paginator = ec2.get_paginator("describe_instances")
            pages = paginator.paginate(
                Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
            )

            metric_queries = []
            for page in pages:
                for reservation in page["Reservations"]:
                    for instance in reservation["Instances"]:
                        metric_queries.append(
                            {
                                "Id": f"cpu_{instance['InstanceId'].replace('-', '_')}",
                                "MetricStat": {
                                    "Metric": {
                                        "Namespace": "AWS/EC2",
                                        "MetricName": "CPUUtilization",
                                        "Dimensions": [
                                            {
                                                "Name": "InstanceId",
                                                "Value": instance["InstanceId"],
                                            }
                                        ],
                                    },
                                    "Period": 3600,
                                    "Stat": "Average",
                                },
                                "ReturnData": True,
                            }
                        )

            if not metric_queries:
                return pd.DataFrame()

            response = cloudwatch.get_metric_data(
                MetricDataQueries=metric_queries,
                StartTime=start_date,
                EndTime=end_date,
                ScanBy="TimestampAscending",
            )

            for metric in response["MetricDataResults"]:
                instance_id = metric["Label"].split(" ")[0]
                for i in range(len(metric["Timestamps"])):
                    data.append(
                        {
                            "Timestamp": metric["Timestamps"][i],
                            "InstanceId": instance_id,
                            "CPUUtilization": metric["Values"][i],
                            "Provider": "AWS",
                        }
                    )
        except Exception as e:
            st.error(f"Error getting AWS CPU utilization data: {e}")

    if cloud_provider in ["Azure", "Both"]:
        try:
            vms = azure_client.list_resources("virtualMachines")
            for vm in vms:
                response = azure_client.get_metric_data(
                    vm["id"], "Percentage CPU", str(start_date), str(end_date)
                )
                if response and "value" in response:
                    for metric in response["value"][0]["timeseries"][0]["data"]:
                        data.append(
                            {
                                "Timestamp": metric["timeStamp"],
                                "InstanceId": vm["name"],
                                "CPUUtilization": metric["average"],
                                "Provider": "Azure",
                            }
                        )
        except Exception as e:
            st.error(f"Error getting Azure CPU utilization data: {e}")

    return pd.DataFrame(data)


def get_memory_utilization_data(start_date, end_date, cloud_provider, azure_client):
    """Get memory utilization data"""
    data = []
    if cloud_provider in ["AWS", "Both"]:
        try:
            ec2 = boto3.client("ec2", region_name=AWS_REGION)
            paginator = ec2.get_paginator("describe_instances")
            pages = paginator.paginate(
                Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
            )

            metric_queries = []
            for page in pages:
                for reservation in page["Reservations"]:
                    for instance in reservation["Instances"]:
                        metric_queries.append(
                            {
                                "Id": f"mem_{instance['InstanceId'].replace('-', '_')}",
                                "MetricStat": {
                                    "Metric": {
                                        "Namespace": "CWAgent",
                                        "MetricName": "mem_used_percent",
                                        "Dimensions": [
                                            {
                                                "Name": "InstanceId",
                                                "Value": instance["InstanceId"],
                                            }
                                        ],
                                    },
                                    "Period": 3600,
                                    "Stat": "Average",
                                },
                                "ReturnData": True,
                            }
                        )

            if not metric_queries:
                return pd.DataFrame()

            response = cloudwatch.get_metric_data(
                MetricDataQueries=metric_queries,
                StartTime=start_date,
                EndTime=end_date,
                ScanBy="TimestampAscending",
            )

            for metric in response["MetricDataResults"]:
                instance_id = metric["Label"].split(" ")[0]
                for i in range(len(metric["Timestamps"])):
                    data.append(
                        {
                            "Timestamp": metric["Timestamps"][i],
                            "InstanceId": instance_id,
                            "MemoryUtilization": metric["Values"][i],
                            "Provider": "AWS",
                        }
                    )
        except Exception as e:
            st.warning(
                f"Could not get AWS memory utilization data. Ensure the CloudWatch agent is installed and configured to collect memory metrics. Error: {e}"
            )

    if cloud_provider in ["Azure", "Both"]:
        try:
            vms = azure_client.list_resources("virtualMachines")
            for vm in vms:
                response = azure_client.get_metric_data(
                    vm["id"], "Available Memory Bytes", str(start_date), str(end_date)
                )
                if response and "value" in response:
                    for metric in response["value"][0]["timeseries"][0]["data"]:
                        # Azure returns available bytes, so we need to calculate percentage used. This is a simplification and requires knowing the total memory.
                        # For now, we will just return the available bytes. A more complete solution would require getting the VM size and calculating the percentage.
                        data.append(
                            {
                                "Timestamp": metric["timeStamp"],
                                "InstanceId": vm["name"],
                                "MemoryUtilization": metric["average"],
                                "Provider": "Azure",
                            }
                        )
        except Exception as e:
            st.warning(
                f"Could not get Azure memory utilization data. Ensure the necessary diagnostics are enabled. Error: {e}"
            )

    return pd.DataFrame(data)


def get_storage_utilization_data(cloud_provider, azure_client):
    """Get storage utilization data"""

    data = []

    if cloud_provider in ["AWS", "Both"]:
        try:
            s3 = boto3.client("s3", region_name=AWS_REGION)

            buckets = s3.list_buckets()

            for bucket in buckets["Buckets"]:
                try:
                    response = cloudwatch.get_metric_statistics(
                        Namespace="AWS/S3",
                        MetricName="BucketSizeBytes",
                        Dimensions=[
                            {"Name": "BucketName", "Value": bucket["Name"]},
                            {"Name": "StorageType", "Value": "StandardStorage"},
                        ],
                        StartTime=datetime.now() - timedelta(days=2),
                        EndTime=datetime.now(),
                        Period=86400,
                        Statistics=["Average"],
                    )

                    if response["Datapoints"]:
                        # Convert to GB

                        size_gb = response["Datapoints"][0]["Average"] / (1024**3)

                        data.append(
                            {
                                "Bucket": bucket["Name"],
                                "Utilization": size_gb,
                                "Provider": "AWS",
                            }
                        )

                except Exception as e:
                    st.warning(
                        f"Could not get storage utilization for bucket {bucket['Name']}. Error: {e}"
                    )

        except Exception as e:
            st.error(f"Error getting AWS storage utilization data: {e}")

    if cloud_provider in ["Azure", "Both"]:
        try:
            storage_accounts = azure_client.list_resources("storageAccounts")

            for sa in storage_accounts:
                response = azure_client.get_metric_data(
                    sa["id"],
                    "UsedCapacity",
                    str(datetime.now() - timedelta(days=2)),
                    str(datetime.now()),
                )

                if response and "value" in response:
                    for metric in response["value"][0]["timeseries"][0]["data"]:
                        size_gb = metric["average"] / (1024**3)

                        data.append(
                            {
                                "Bucket": sa["name"],
                                "Utilization": size_gb,
                                "Provider": "Azure",
                            }
                        )

        except Exception as e:
            st.error(f"Error getting Azure storage utilization data: {e}")

    return pd.DataFrame(data)


def get_db_connections_data(start_date, end_date, cloud_provider, azure_client):
    """Get database connections data"""
    data = []
    if cloud_provider in ["AWS", "Both"]:
        try:
            rds = boto3.client("rds", region_name=AWS_REGION)
            paginator = rds.get_paginator("describe_db_instances")
            pages = paginator.paginate()

            metric_queries = []
            for page in pages:
                for db_instance in page["DBInstances"]:
                    metric_queries.append(
                        {
                            "Id": f"db_{db_instance['DBInstanceIdentifier'].replace('-', '_')}",
                            "MetricStat": {
                                "Metric": {
                                    "Namespace": "AWS/RDS",
                                    "MetricName": "DatabaseConnections",
                                    "Dimensions": [
                                        {
                                            "Name": "DBInstanceIdentifier",
                                            "Value": db_instance[
                                                "DBInstanceIdentifier"
                                            ],
                                        }
                                    ],
                                },
                                "Period": 3600,
                                "Stat": "Average",
                            },
                            "ReturnData": True,
                        }
                    )

            if not metric_queries:
                return pd.DataFrame()

            response = cloudwatch.get_metric_data(
                MetricDataQueries=metric_queries,
                StartTime=start_date,
                EndTime=end_date,
                ScanBy="TimestampAscending",
            )

            for metric in response["MetricDataResults"]:
                db_name = metric["Label"].split(" ")[0]
                for i in range(len(metric["Timestamps"])):
                    data.append(
                        {
                            "Timestamp": metric["Timestamps"][i],
                            "Database": db_name,
                            "Connections": metric["Values"][i],
                            "Provider": "AWS",
                        }
                    )
        except Exception as e:
            st.error(f"Error getting AWS database connections data: {e}")

    if cloud_provider in ["Azure", "Both"]:
        try:
            sql_servers = azure_client.list_resources("sqlServers")
            for server in sql_servers:
                response = azure_client.get_metric_data(
                    server["id"],
                    "sqlserver_connections",
                    str(start_date),
                    str(end_date),
                )
                if response and "value" in response:
                    for metric in response["value"][0]["timeseries"][0]["data"]:
                        data.append(
                            {
                                "Timestamp": metric["timeStamp"],
                                "Database": server["name"],
                                "Connections": metric["average"],
                                "Provider": "Azure",
                            }
                        )
        except Exception as e:
            st.error(f"Error getting Azure database connections data: {e}")

    return pd.DataFrame(data)


def get_instance_hourly_rate(instance_type: str) -> float:
    """Get hourly rate for instance type (simplified pricing)"""
    rates = {
        "t3.nano": 0.0052,
        "t3.micro": 0.0104,
        "t3.small": 0.0208,
        "t3.medium": 0.0416,
        "t3.large": 0.0832,
        "t3.xlarge": 0.1664,
        "t3.2xlarge": 0.3328,
        "m5.large": 0.096,
        "m5.xlarge": 0.192,
        "m5.2xlarge": 0.384,
        "m5.4xlarge": 0.768,
        "c5.large": 0.085,
        "c5.xlarge": 0.17,
        "r5.large": 0.126,
        "r5.xlarge": 0.252,
    }
    return rates.get(instance_type, 0.05)


def get_next_size_down(instance_type: str) -> str:
    """Get next smaller instance size"""
    try:
        family, size = instance_type.split(".")
        sizes = [
            "nano",
            "micro",
            "small",
            "medium",
            "large",
            "xlarge",
            "2xlarge",
            "4xlarge",
            "8xlarge",
            "12xlarge",
            "16xlarge",
            "24xlarge",
        ]
        if size in sizes:
            current_index = sizes.index(size)
            if current_index > 0:
                return f"{family}.{sizes[current_index - 1]}"
    except (ValueError, IndexError):
        pass
    return None


def calculate_right_sizing_savings(current_type: str, recommended_type: str) -> float:
    """Calculate monthly savings from right-sizing"""
    if not recommended_type:
        return 0.0

    current_rate = get_instance_hourly_rate(current_type)
    recommended_rate = get_instance_hourly_rate(recommended_type)

    if recommended_rate < current_rate:
        return (current_rate - recommended_rate) * 730  # ~730 hours in a month
    return 0.0


def calculate_shutdown_savings(instance_type: str, hours_off: int = 400) -> float:
    """Calculate monthly savings from auto-shutdown (assuming nights/weekends off)"""
    rate = get_instance_hourly_rate(instance_type)
    return rate * hours_off


def get_recommendations(cloud_provider, environment, azure_client):
    """Get cost optimization recommendations"""
    recommendations = []
    start_date, end_date = get_date_range("Last 30 days")

    # Right-sizing recommendations
    cpu_data = get_cpu_utilization_data(
        start_date, end_date, cloud_provider, azure_client
    )
    if not cpu_data.empty:
        avg_cpu = cpu_data.groupby("InstanceId")["CPUUtilization"].mean()
        for instance_id, avg_cpu_util in avg_cpu.items():
            if avg_cpu_util < 20:
                # Attempt to find instance type from AWS
                current_type = "t3.medium" # Default fallback
                if cloud_provider in ["AWS", "Both"]:
                    try:
                        ec2 = boto3.client("ec2", region_name=AWS_REGION)
                        resp = ec2.describe_instances(InstanceIds=[instance_id])
                        current_type = resp["Reservations"][0]["Instances"][0]["InstanceType"]
                    except:
                        pass

                recommended_type = get_next_size_down(current_type)
                savings = calculate_right_sizing_savings(current_type, recommended_type)

                if savings > 0:
                    recommendations.append(
                        {
                            "resource_id": instance_id,
                            "resource_type": "EC2 Instance"
                            if "i-" in instance_id
                            else "Virtual Machine",
                            "category": "Right-sizing",
                            "recommendation": f"Instance {instance_id} ({current_type}) has low CPU ({avg_cpu_util:.1f}%) -> Resize to {recommended_type}.",
                            "potential_savings": savings,
                            "confidence": "Medium",
                            "environment": "dev",  # Placeholder, should fetch real tag
                        }
                    )

    # Auto-shutdown recommendations
    if cloud_provider in ["AWS", "Both"]:
        try:
            ec2 = boto3.client("ec2", region_name=AWS_REGION)
            paginator = ec2.get_paginator("describe_instances")
            pages = paginator.paginate(
                Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
            )
            for page in pages:
                for reservation in page["Reservations"]:
                    for instance in reservation["Instances"]:
                        tags = {
                            tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])
                        }
                        if (
                            tags.get("Environment") != "prod"
                            and tags.get("AutoShutdown") != "true"
                        ):
                            instance_type = instance["InstanceType"]
                            savings = calculate_shutdown_savings(instance_type)

                            recommendations.append(
                                {
                                    "resource_id": instance["InstanceId"],
                                    "resource_type": "EC2 Instance",
                                    "category": "Auto-shutdown",
                                    "recommendation": f"Enable auto-shutdown for non-prod {instance_type} instance {instance['InstanceId']}.",
                                    "potential_savings": savings,
                                    "confidence": "High",
                                    "environment": tags.get("Environment", "dev"),
                                }
                            )
        except Exception as e:
            st.error(f"Error generating AWS shutdown recommendations: {e}")

    if cloud_provider in ["Azure", "Both"]:
        vms = azure_client.list_resources("virtualMachines")
        for vm in vms:
            if (
                vm.get("tags", {}).get("Environment") != "prod"
                and vm.get("tags", {}).get("AutoShutdown") != "true"
            ):
                recommendations.append(
                    {
                        "resource_id": vm["name"],
                        "resource_type": "Virtual Machine",
                        "category": "Auto-shutdown",
                        "recommendation": f"Enable auto-shutdown for non-production instance {vm['name']}.",
                        "potential_savings": 100.00,  # Placeholder value
                        "confidence": "High",
                        "environment": vm.get("tags", {}).get("Environment", "dev"),
                    }
                )

    # Storage optimization recommendations
    storage_data = get_storage_utilization_data(cloud_provider, azure_client)
    if not storage_data.empty:
        for index, row in storage_data.iterrows():
            if row["Utilization"] < 100:  # Placeholder value
                recommendations.append(
                    {
                        "resource_id": row["Bucket"],
                        "resource_type": "S3 Bucket"
                        if row["Provider"] == "AWS"
                        else "Storage Account",
                        "category": "Storage Optimization",
                        "recommendation": f"Storage {row['Bucket']} has low utilization ({row['Utilization']:.2f} GB) and could be moved to a cheaper storage class.",
                        "potential_savings": 20.00,  # Placeholder value
                        "confidence": "Low",
                        "environment": "N/A",
                    }
                )

    filtered_recs = [
        rec for rec in recommendations if rec["environment"] in environment
    ]
    return filtered_recs


if __name__ == "__main__":
    main()
