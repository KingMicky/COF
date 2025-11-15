"""
Azure Cost Exporter for Prometheus
Exports Azure cost and usage metrics to Prometheus
"""

import time
from datetime import datetime, timedelta
from prometheus_client import start_http_server, Gauge, Counter, Histogram
import os
import logging
import requests
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Azure Configuration
AZURE_TENANT_ID = os.environ.get('AZURE_TENANT_ID')
AZURE_CLIENT_ID = os.environ.get('AZURE_CLIENT_ID')
AZURE_CLIENT_SECRET = os.environ.get('AZURE_CLIENT_SECRET')
AZURE_SUBSCRIPTION_ID = os.environ.get('AZURE_SUBSCRIPTION_ID')

# Prometheus metrics
cost_gauge = Gauge('azure_cost_total', 'Total Azure cost by service', ['service', 'subscription'])
budget_gauge = Gauge('azure_budget_limit', 'Azure budget limits', ['budget_name'])
budget_spent_gauge = Gauge('azure_budget_spent', 'Azure budget spent amount', ['budget_name'])
resource_count_gauge = Gauge('azure_resource_count', 'Count of Azure resources by type', ['resource_type', 'subscription'])

class AzureCostManagementClient:
    """Azure Cost Management API client"""

    def __init__(self):
        self.access_token = None
        self.token_expires = None
        self.base_url = "https://management.azure.com"

    def get_access_token(self):
        """Get Azure access token"""
        if self.access_token and self.token_expires and datetime.now() < self.token_expires:
            return self.access_token

        token_url = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/token"
        data = {
            'grant_type': 'client_credentials',
            'client_id': AZURE_CLIENT_ID,
            'client_secret': AZURE_CLIENT_SECRET,
            'resource': 'https://management.core.windows.net/'
        }

        response = requests.post(token_url, data=data)
        response.raise_for_status()

        token_data = response.json()
        self.access_token = token_data['access_token']
        expires_in = token_data.get('expires_in', 3600)
        self.token_expires = datetime.now() + timedelta(seconds=expires_in - 60)  # 1 min buffer

        return self.access_token

    def get_cost_data(self, start_date: str, end_date: str) -> dict:
        """Get cost data from Azure Cost Management API"""
        try:
            token = self.get_access_token()
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            # Query for cost by resource
            query_url = f"{self.base_url}/subscriptions/{AZURE_SUBSCRIPTION_ID}/providers/Microsoft.CostManagement/query?api-version=2021-10-01"

            query_payload = {
                "type": "ActualCost",
                "timeframe": "Custom",
                "timePeriod": {
                    "from": start_date,
                    "to": end_date
                },
                "dataset": {
                    "granularity": "Daily",
                    "aggregation": {
                        "totalCost": {
                            "name": "Cost",
                            "function": "Sum"
                        }
                    },
                    "grouping": [
                        {
                            "type": "Dimension",
                            "name": "ServiceName"
                        }
                    ]
                }
            }

            response = requests.post(query_url, headers=headers, json=query_payload)
            response.raise_for_status()

            data = response.json()
            return self._parse_cost_data(data)

        except Exception as e:
            logger.error(f"Error getting Azure cost data: {e}")
            return {}

    def _parse_cost_data(self, data: dict) -> dict:
        """Parse Azure cost API response"""
        costs = {}

        if 'properties' in data and 'rows' in data['properties']:
            columns = data['properties'].get('columns', [])
            rows = data['properties']['rows']

            # Find service name and cost column indices
            service_idx = None
            cost_idx = None

            for i, col in enumerate(columns):
                if col.get('name') == 'ServiceName':
                    service_idx = i
                elif col.get('name') == 'Cost':
                    cost_idx = i

            if service_idx is not None and cost_idx is not None:
                for row in rows:
                    if len(row) > max(service_idx, cost_idx):
                        service = row[service_idx]
                        cost = float(row[cost_idx])
                        costs[service] = costs.get(service, 0) + cost

        return costs

def get_budget_info() -> list:
    """Get Azure budget information"""
    # Note: Azure budget API is more complex and may require additional setup
    # This is a placeholder for budget information
    try:
        # In a real implementation, you would query Azure Budgets API
        # For now, return mock data
        return [
            {
                'name': 'Monthly Budget',
                'limit': 1000.0,
                'spent': 750.0
            }
        ]
    except Exception as e:
        logger.error(f"Error getting budget info: {e}")
        return []

def get_resource_counts() -> dict:
    """Get counts of various Azure resources"""
    try:
        # This would require Azure Resource Graph queries
        # For now, return mock data
        return {
            'virtual_machines': 5,
            'storage_accounts': 3,
            'sql_databases': 2
        }
    except Exception as e:
        logger.error(f"Error getting resource counts: {e}")
        return {}

def update_metrics():
    """Update all Prometheus metrics"""
    try:
        client = AzureCostManagementClient()

        # Get date range (last 30 days)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')

        # Update cost metrics
        costs = client.get_cost_data(start_str, end_str)
        for service, cost in costs.items():
            cost_gauge.labels(service=service, subscription=AZURE_SUBSCRIPTION_ID).set(cost)

        # Update budget metrics
        budget_info = get_budget_info()
        for budget in budget_info:
            budget_gauge.labels(budget_name=budget['name']).set(budget['limit'])
            budget_spent_gauge.labels(budget_name=budget['name']).set(budget['spent'])

        # Update resource counts
        resource_counts = get_resource_counts()
        for resource_type, count in resource_counts.items():
            resource_count_gauge.labels(resource_type=resource_type, subscription=AZURE_SUBSCRIPTION_ID).set(count)

        logger.info("Azure metrics updated successfully")

    except Exception as e:
        logger.error(f"Error updating Azure metrics: {e}")

def main():
    """Main function to run the exporter"""
    # Start Prometheus HTTP server
    port = int(os.environ.get('PORT', 8080))
    start_http_server(port)
    logger.info(f"Azure Cost Exporter started on port {port}")

    # Update metrics every 5 minutes
    while True:
        update_metrics()
        time.sleep(300)  # 5 minutes

if __name__ == "__main__":
    main()
