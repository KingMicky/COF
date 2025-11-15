"""
Cost Optimization Dashboard
Web dashboard for visualizing cost optimization metrics and recommendations
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import boto3
import os
from typing import Dict, List, Any
import json

# AWS Configuration
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Initialize AWS clients
cloudwatch = boto3.client('cloudwatch', region_name=AWS_REGION)
ce = boto3.client('ce', region_name=AWS_REGION)  # Cost Explorer

def main():
    st.set_page_config(
        page_title="Cost Optimization Dashboard",
        page_icon="💰",
        layout="wide"
    )

    st.title("💰 Cost Optimization Framework Dashboard")

    # Sidebar for filters
    st.sidebar.header("Filters")

    # Date range selector
    date_range = st.sidebar.selectbox(
        "Time Range",
        ["Last 7 days", "Last 30 days", "Last 90 days", "Last year"],
        index=1
    )

    # Cloud provider selector
    cloud_provider = st.sidebar.selectbox(
        "Cloud Provider",
        ["AWS", "Azure", "Both"],
        index=0
    )

    # Environment selector
    environment = st.sidebar.multiselect(
        "Environment",
        ["dev", "staging", "prod"],
        default=["dev", "staging", "prod"]
    )

    # Get date range
    start_date, end_date = get_date_range(date_range)

    # Main dashboard tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Cost Overview",
        "🔍 Resource Utilization",
        "💡 Recommendations",
        "⚙️ Settings"
    ])

    with tab1:
        show_cost_overview(start_date, end_date, cloud_provider, environment)

    with tab2:
        show_resource_utilization(start_date, end_date, cloud_provider, environment)

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
    else:  # Last year
        start_date = end_date - timedelta(days=365)

    return start_date.date(), end_date.date()

def show_cost_overview(start_date, end_date, cloud_provider, environment):
    """Display cost overview dashboard"""
    st.header("Cost Overview")

    col1, col2, col3, col4 = st.columns(4)

    # Mock data for demonstration - replace with actual AWS/Azure API calls
    with col1:
        st.metric("Total Cost", "$12,450", "+5.2%")

    with col2:
        st.metric("Compute Cost", "$8,200", "+3.1%")

    with col3:
        st.metric("Storage Cost", "$2,800", "-2.4%")

    with col4:
        st.metric("Database Cost", "$1,450", "+8.7%")

    # Cost trend chart
    st.subheader("Cost Trend")
    cost_data = get_cost_trend_data(start_date, end_date)
    fig = px.line(cost_data, x='Date', y='Cost', title='Daily Cost Trend')
    st.plotly_chart(fig, use_container_width=True)

    # Cost by service
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Cost by Service")
        service_cost_data = get_service_cost_data(start_date, end_date)
        fig = px.pie(service_cost_data, values='Cost', names='Service',
                    title='Cost Distribution by Service')
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Cost by Environment")
        env_cost_data = get_environment_cost_data(start_date, end_date, environment)
        fig = px.bar(env_cost_data, x='Environment', y='Cost',
                    title='Cost by Environment')
        st.plotly_chart(fig, use_container_width=True)

def show_resource_utilization(start_date, end_date, cloud_provider, environment):
    """Display resource utilization metrics"""
    st.header("Resource Utilization")

    # CPU Utilization
    st.subheader("CPU Utilization Trends")
    cpu_data = get_cpu_utilization_data(start_date, end_date)
    fig = px.line(cpu_data, x='Timestamp', y='CPUUtilization',
                 color='InstanceId', title='CPU Utilization Over Time')
    st.plotly_chart(fig, use_container_width=True)

    # Memory Utilization (if available)
    st.subheader("Memory Utilization Trends")
    memory_data = get_memory_utilization_data(start_date, end_date)
    if not memory_data.empty:
        fig = px.line(memory_data, x='Timestamp', y='MemoryUtilization',
                     color='InstanceId', title='Memory Utilization Over Time')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Memory utilization data not available for all instances")

    # Storage utilization
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Storage Utilization")
        storage_data = get_storage_utilization_data()
        fig = px.bar(storage_data, x='Bucket', y='Utilization',
                    title='Storage Bucket Utilization (%)')
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Database Connections")
        db_connections_data = get_db_connections_data(start_date, end_date)
        fig = px.line(db_connections_data, x='Timestamp', y='Connections',
                     color='Database', title='Database Connections Over Time')
        st.plotly_chart(fig, use_container_width=True)

def show_recommendations(cloud_provider, environment):
    """Display cost optimization recommendations"""
    st.header("Optimization Recommendations")

    # Get recommendations from various sources
    recommendations = get_recommendations(cloud_provider, environment)

    if recommendations:
        # Summary metrics
        total_savings = sum(rec['potential_savings'] for rec in recommendations)
        st.metric("Total Potential Savings", f"${total_savings:,.2f}")

        # Recommendations table
        st.subheader("Detailed Recommendations")

        # Convert to DataFrame for better display
        df = pd.DataFrame(recommendations)
        df['potential_savings'] = df['potential_savings'].apply(lambda x: f"${x:,.2f}")

        st.dataframe(df, use_container_width=True)

        # Recommendations by category
        st.subheader("Recommendations by Category")
        category_data = df.groupby('category').agg({
            'potential_savings': 'sum',
            'resource_id': 'count'
        }).reset_index()
        category_data.columns = ['Category', 'Total Savings', 'Count']

        fig = px.bar(category_data, x='Category', y='Total Savings',
                    title='Potential Savings by Category')
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("No recommendations available at this time.")

def show_settings():
    """Display settings and configuration"""
    st.header("Settings")

    st.subheader("Dashboard Configuration")

    # Refresh interval
    refresh_interval = st.selectbox(
        "Auto-refresh interval",
        ["Off", "30 seconds", "1 minute", "5 minutes"],
        index=0
    )

    # Alert thresholds
    st.subheader("Alert Thresholds")

    cpu_threshold = st.slider("CPU utilization alert threshold (%)", 0, 100, 80)
    memory_threshold = st.slider("Memory utilization alert threshold (%)", 0, 100, 80)
    cost_threshold = st.slider("Cost increase alert threshold (%)", 0, 100, 20)

    # Notification settings
    st.subheader("Notifications")

    email_notifications = st.checkbox("Email notifications", value=True)
    slack_notifications = st.checkbox("Slack notifications", value=False)

    if email_notifications:
        alert_email = st.text_input("Alert email address", "admin@example.com")

    if slack_notifications:
        slack_webhook = st.text_input("Slack webhook URL", type="password")

    # Save settings button
    if st.button("Save Settings"):
        st.success("Settings saved successfully!")

# Data fetching functions (mock implementations - replace with actual API calls)

def get_cost_trend_data(start_date, end_date):
    """Get cost trend data from AWS Cost Explorer"""
    # Mock data
    dates = pd.date_range(start=start_date, end=end_date, freq='D')
    costs = [12000 + i * 10 + (i % 7) * 50 for i in range(len(dates))]

    return pd.DataFrame({
        'Date': dates,
        'Cost': costs
    })

def get_service_cost_data(start_date, end_date):
    """Get cost breakdown by service"""
    return pd.DataFrame({
        'Service': ['EC2', 'S3', 'RDS', 'Lambda', 'Other'],
        'Cost': [8200, 2800, 1450, 450, 550]
    })

def get_environment_cost_data(start_date, end_date, environments):
    """Get cost breakdown by environment"""
    env_costs = {'dev': 3200, 'staging': 4800, 'prod': 4450}
    data = [{'Environment': env, 'Cost': cost}
            for env, cost in env_costs.items() if env in environments]
    return pd.DataFrame(data)

def get_cpu_utilization_data(start_date, end_date):
    """Get CPU utilization data"""
    # Mock data
    timestamps = pd.date_range(start=start_date, end=end_date, freq='H')
    instances = ['i-1234567890abcdef0', 'i-0987654321fedcba0']

    data = []
    for instance in instances:
        for ts in timestamps:
            cpu = 20 + (ts.hour % 24) * 2 + (hash(instance) % 20)
            data.append({
                'Timestamp': ts,
                'InstanceId': instance,
                'CPUUtilization': min(cpu, 100)
            })

    return pd.DataFrame(data)

def get_memory_utilization_data(start_date, end_date):
    """Get memory utilization data"""
    # Mock data - not all instances have memory metrics
    timestamps = pd.date_range(start=start_date, end=end_date, freq='H')
    instances = ['i-1234567890abcdef0']  # Only one instance has memory data

    data = []
    for instance in instances:
        for ts in timestamps:
            memory = 30 + (ts.hour % 24) * 1.5 + (hash(instance) % 15)
            data.append({
                'Timestamp': ts,
                'InstanceId': instance,
                'MemoryUtilization': min(memory, 100)
            })

    return pd.DataFrame(data)

def get_storage_utilization_data():
    """Get storage utilization data"""
    return pd.DataFrame({
        'Bucket': ['cost-opt-data', 'cost-opt-logs', 'cost-opt-backup'],
        'Utilization': [65, 45, 80]
    })

def get_db_connections_data(start_date, end_date):
    """Get database connections data"""
    timestamps = pd.date_range(start=start_date, end=end_date, freq='H')
    databases = ['cost-opt-db-1', 'cost-opt-db-2']

    data = []
    for db in databases:
        for ts in timestamps:
            connections = 10 + (ts.hour % 24) * 2 + (hash(db) % 10)
            data.append({
                'Timestamp': ts,
                'Database': db,
                'Connections': connections
            })

    return pd.DataFrame(data)

def get_recommendations(cloud_provider, environment):
    """Get cost optimization recommendations"""
    # Mock recommendations - replace with actual recommendation engine
    recommendations = [
        {
            'resource_id': 'i-1234567890abcdef0',
            'resource_type': 'EC2 Instance',
            'category': 'Right-sizing',
            'recommendation': 'Change instance type from t3.medium to t3.small',
            'potential_savings': 150.00,
            'confidence': 'High',
            'environment': 'dev'
        },
        {
            'resource_id': 'cost-opt-bucket-1',
            'resource_type': 'S3 Bucket',
            'category': 'Storage Optimization',
            'recommendation': 'Move objects to Standard-IA storage class',
            'potential_savings': 75.50,
            'confidence': 'Medium',
            'environment': 'prod'
        },
        {
            'resource_id': 'db-cost-opt-001',
            'resource_type': 'RDS Instance',
            'category': 'Auto-shutdown',
            'recommendation': 'Enable auto-shutdown for non-production hours',
            'potential_savings': 200.00,
            'confidence': 'High',
            'environment': 'staging'
        },
        {
            'resource_id': 'vmss-cost-opt-001',
            'resource_type': 'VM Scale Set',
            'category': 'Compute Optimization',
            'recommendation': 'Reduce instance count during off-hours',
            'potential_savings': 120.00,
            'confidence': 'Medium',
            'environment': 'dev'
        }
    ]

    # Filter by environment
    filtered_recs = [rec for rec in recommendations if rec['environment'] in environment]

    return filtered_recs

if __name__ == "__main__":
    main()
