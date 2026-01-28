"""
Azure Cost Management Client for the Dashboard
"""

import logging
import os
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)

AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID")
AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")
AZURE_SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID")


class AzureClient:
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

    def get_cost_and_usage(
        self,
        start_date: str,
        end_date: str,
        granularity: str,
        group_by: list = None,
        filter: dict = None,
    ) -> dict:
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
                    "granularity": granularity,
                    "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
                    "grouping": group_by or [],
                    "filter": filter,
                },
            }

            response = requests.post(query_url, headers=headers, json=query_payload)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Error getting Azure cost data: {e}")
            return {}

    def list_resources(self, resource_type: str) -> list:
        """List resources of a specific type"""
        try:
            token = self.get_access_token()
            headers = {"Authorization": f"Bearer {token}"}

            if resource_type == "virtualMachines":
                url = f"{self.base_url}/subscriptions/{AZURE_SUBSCRIPTION_ID}/providers/Microsoft.Compute/virtualMachines?api-version=2021-11-01"
            elif resource_type == "storageAccounts":
                url = f"{self.base_url}/subscriptions/{AZURE_SUBSCRIPTION_ID}/providers/Microsoft.Storage/storageAccounts?api-version=2021-09-01"
            elif resource_type == "sqlServers":
                url = f"{self.base_url}/subscriptions/{AZURE_SUBSCRIPTION_ID}/providers/Microsoft.Sql/servers?api-version=2021-11-01"
            else:
                return []

            data = self.get_with_token_refresh(url, headers)
            return data.get("value", [])

        except Exception as e:
            logger.error(f"Error listing Azure resources: {e}")
            return []

    def get_metric_data(
        self,
        resource_uri: str,
        metric_names: str,
        start_time: str,
        end_time: str,
        interval: str = "PT1H",
        aggregation: str = "Average",
    ) -> dict:
        """Get metric data for a specific resource"""
        try:
            token = self.get_access_token()
            headers = {"Authorization": f"Bearer {token}"}

            url = f"{self.base_url}{resource_uri}/providers/Microsoft.Insights/metrics?api-version=2018-01-01&metricnames={metric_names}&timespan={start_time}/{end_time}&interval={interval}&aggregation={aggregation}"

            return self.get_with_token_refresh(url, headers)

        except Exception as e:
            logger.error(f"Error getting Azure metric data: {e}")
            return {}
