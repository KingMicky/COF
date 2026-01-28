"""
Azure Cost Exporter for Prometheus
Exports Azure cost and usage metrics to Prometheus
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta

import requests
from prometheus_client import Counter, Gauge, Histogram, start_http_server

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID")
AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")
AZURE_SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID")


cost_gauge = Gauge(
    "azure_cost_total", "Total Azure cost by service", ["service", "subscription"]
)
budget_gauge = Gauge("azure_budget_limit", "Azure budget limits", ["budget_name"])
budget_spent_gauge = Gauge(
    "azure_budget_spent", "Azure budget spent amount", ["budget_name"]
)
resource_count_gauge = Gauge(
    "azure_resource_count",
    "Count of Azure resources by type",
    ["resource_type", "subscription"],
)


class AzureCostManagementClient:
    """Azure Cost Management API client"""

    def __init__(self):
        self.access_token = None
        self.token_expires = None
        self.base_url = "https://management.azure.com"

    def get_access_token(self):
        """Get Azure access token"""
        if (
            self.access_token
            and self.token_expires
            and datetime.now() < self.token_expires
        ):
            return self.access_token

        token_url = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": AZURE_CLIENT_ID,
            "client_secret": AZURE_CLIENT_SECRET,
            "resource": "https://management.core.windows.net/",
        }

        response = requests.post(token_url, data=data)
        response.raise_for_status()

        token_data = response.json()
        self.access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        self.token_expires = datetime.now() + timedelta(seconds=expires_in - 60)

        return self.access_token

    def get_with_token_refresh(self, url: str, headers: dict, **kwargs) -> dict:
        """Make a request with automatic token refresh"""
        try:
            response = requests.get(url, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.info("Access token expired, refreshing...")
                self.access_token = None
                headers["Authorization"] = f"Bearer {self.get_access_token()}"
                response = requests.get(url, headers=headers, **kwargs)
                response.raise_for_status()
                return response.json()
            else:
                raise

    def get_cost_data(self, start_date: str, end_date: str) -> dict:
        """Get cost data from Azure Cost Management API"""
        try:
            token = self.get_access_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            query_url = f"{self.base_url}/subscriptions/{AZURE_SUBSCRIPTION_ID}/providers/Microsoft.CostManagement/query?api-version=2021-10-01"

            query_payload = {
                "type": "ActualCost",
                "timeframe": "Custom",
                "timePeriod": {"from": start_date, "to": end_date},
                "dataset": {
                    "granularity": "Daily",
                    "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
                    "grouping": [{"type": "Dimension", "name": "ServiceName"}],
                },
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
        if "properties" in data and "rows" in data["properties"]:
            columns = {
                col["name"]: i for i, col in enumerate(data["properties"]["columns"])
            }
            rows = data["properties"]["rows"]

            for row in rows:
                service = row[columns["ServiceName"]]
                cost = float(row[columns["Cost"]])
                costs[service] = costs.get(service, 0) + cost
        return costs


def get_budget_info(client: AzureCostManagementClient) -> list:
    """Get Azure budget information"""
    try:
        token = client.get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{client.base_url}/subscriptions/{AZURE_SUBSCRIPTION_ID}/providers/Microsoft.Consumption/budgets?api-version=2021-10-01"
        data = client.get_with_token_refresh(url, headers)

        budgets_list = []
        if "value" in data:
            for budget in data["value"]:
                properties = budget.get("properties", {})
                budgets_list.append(
                    {
                        "name": budget.get("name"),
                        "limit": properties.get("amount"),
                        "spent": properties.get("currentSpend", {}).get("amount"),
                    }
                )
        return budgets_list
    except Exception as e:
        logger.error(f"Error getting budget info: {e}")
        return []


def get_resource_counts(client: AzureCostManagementClient) -> dict:
    """Get counts of various Azure resources"""
    try:
        token = client.get_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        vm_url = f"{client.base_url}/subscriptions/{AZURE_SUBSCRIPTION_ID}/providers/Microsoft.Compute/virtualMachines?api-version=2021-11-01"
        vms = client.get_with_token_refresh(vm_url, headers)

        storage_url = f"{client.base_url}/subscriptions/{AZURE_SUBSCRIPTION_ID}/providers/Microsoft.Storage/storageAccounts?api-version=2021-09-01"
        storage = client.get_with_token_refresh(storage_url, headers)

        sql_url = f"{client.base_url}/subscriptions/{AZURE_SUBSCRIPTION_ID}/providers/Microsoft.Sql/servers?api-version=2021-11-01"
        sql = client.get_with_token_refresh(sql_url, headers)

        return {
            "virtual_machines": len(vms.get("value", [])),
            "storage_accounts": len(storage.get("value", [])),
            "sql_databases": len(sql.get("value", [])),
        }
    except Exception as e:
        logger.error(f"Error getting resource counts: {e}")
        return {}


def update_metrics():
    """Update all Prometheus metrics"""
    try:
        client = AzureCostManagementClient()

        time_period_days = int(os.environ.get("COST_METRICS_TIME_PERIOD_DAYS", "30"))
        end_date = datetime.now()
        start_date = end_date - timedelta(days=time_period_days)

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        costs = client.get_cost_data(start_str, end_str)
        for service, cost in costs.items():
            cost_gauge.labels(service=service, subscription=AZURE_SUBSCRIPTION_ID).set(
                cost
            )

        budget_info = get_budget_info(client)
        for budget in budget_info:
            budget_gauge.labels(budget_name=budget["name"]).set(budget["limit"])
            budget_spent_gauge.labels(budget_name=budget["name"]).set(budget["spent"])

        resource_counts = get_resource_counts(client)
        for resource_type, count in resource_counts.items():
            resource_count_gauge.labels(
                resource_type=resource_type, subscription=AZURE_SUBSCRIPTION_ID
            ).set(count)

        logger.info("Azure metrics updated successfully")

    except Exception as e:
        logger.error(f"Error updating Azure metrics: {e}")


def main():
    """Main function to run the exporter"""

    port = int(os.environ.get("PORT", 8080))
    start_http_server(port)
    logger.info(f"Azure Cost Exporter started on port {port}")

    while True:
        update_metrics()
        time.sleep(300)


if __name__ == "__main__":
    main()
