"""
Azure Function for Right-Sizing Recommendations
Analyzes VM and VMSS utilization and provides right-sizing recommendations
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

import azure.functions as func
import numpy as np
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.resource import ResourceManagementClient

app = func.FunctionApp()


def get_clients(subscription_id: str):
    """Initialize Azure management clients"""
    credential = DefaultAzureCredential()
    compute_client = ComputeManagementClient(credential, subscription_id)
    monitor_client = MonitorManagementClient(credential, subscription_id)
    resource_client = ResourceManagementClient(credential, subscription_id)
    return compute_client, monitor_client, resource_client


def get_vm_utilization(monitor_client, resource_id: str, days: int = 7) -> dict:
    """Get CPU and memory utilization metrics for a VM"""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    cpu_metrics = monitor_client.metrics.list(
        resource_id,
        timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
        interval="PT1H",
        metricnames="Percentage CPU",
        aggregation="Average,Maximum",
    )

    memory_metrics = monitor_client.metrics.list(
        resource_id,
        timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
        interval="PT1H",
        metricnames="Available Memory Bytes",
        aggregation="Average",
    )

    cpu_data = []
    memory_data = []

    for metric in cpu_metrics.value:
        for timeseries in metric.timeseries:
            for data in timeseries.data:
                if data.average is not None:
                    cpu_data.append(data.average)

    for metric in memory_metrics.value:
        for timeseries in metric.timeseries:
            for data in timeseries.data:
                if data.average is not None:
                    memory_data.append(data.average)

    return {
        "cpu_avg": sum(cpu_data) / len(cpu_data) if cpu_data else 0,
        "cpu_max": max(cpu_data) if cpu_data else 0,
        "cpu_p95": np.percentile(cpu_data, 95) if cpu_data else 0,
        "memory_avg": sum(memory_data) / len(memory_data) if memory_data else 0,
        "cpu_samples": len(cpu_data),
        "memory_samples": len(memory_data),
    }


def get_available_skus(compute_client, location: str, vm_family: str) -> list:
    """Get available SKUs for a given VM family and location"""
    skus = []
    try:
        sku_list = compute_client.resource_skus.list(
            filter=f"location eq '{location}' and familyName eq '{vm_family}'"
        )
        for sku in sku_list:
            if sku.resource_type == "virtualMachines" and sku.capabilities:
                skus.append(sku.name)
    except Exception as e:
        logging.error(f"Error getting available SKUs: {str(e)}")
    return sorted(skus)


def get_right_sizing_recommendation(
    compute_client, location: str, current_sku: str, utilization: dict
) -> dict:
    """Generate right-sizing recommendation based on utilization"""
    cpu_avg = utilization.get("cpu_avg", 0)
    cpu_max = utilization.get("cpu_max", 0)
    cpu_p95 = utilization.get("cpu_p95", 0)

    vm_family = current_sku.split("_")[0]
    available_skus = get_available_skus(compute_client, location, vm_family)

    if not available_skus or current_sku not in available_skus:
        return {
            "action": "unknown",
            "reason": "SKU not in recommendation matrix or unable to fetch SKUs",
        }

    current_sku_index = available_skus.index(current_sku)

    if cpu_p95 < 20 and cpu_avg < 10 and current_sku_index > 0:
        return {
            "action": "downsize",
            "recommended_sku": available_skus[current_sku_index - 1],
            "reason": f"Low utilization (CPU p95: {cpu_p95:.1f}%, avg: {cpu_avg:.1f}%)",
            "potential_savings": "20-30%",
        }

    if cpu_p95 > 80 or cpu_avg > 60:
        if current_sku_index < len(available_skus) - 1:
            return {
                "action": "upsize",
                "recommended_sku": available_skus[current_sku_index + 1],
                "reason": f"High utilization (CPU p95: {cpu_p95:.1f}%, avg: {cpu_avg:.1f}%)",
                "potential_savings": "N/A - performance improvement",
            }
        else:
            return {
                "action": "monitor",
                "reason": f"High utilization but already at largest SKU",
            }

    return {
        "action": "optimal",
        "reason": f"Current utilization is optimal (CPU p95: {cpu_p95:.1f}%, avg: {cpu_avg:.1f}%)",
    }


@app.schedule(
    schedule="0 0 */1 * * *",
    arg_name="myTimer",
    run_on_startup=False,
    use_monitor=False,
)
def right_sizing_analysis(myTimer: func.TimerRequest) -> None:
    """Right-sizing analysis function triggered daily"""
    utc_timestamp = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()

    if myTimer.past_due:
        logging.info("The timer is past due!")
    logging.info("Right-sizing analysis started at %s", utc_timestamp)

    try:
        subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
        resource_group_name = os.environ.get("AZURE_RESOURCE_GROUP")

        if not subscription_id or not resource_group_name:
            logging.error("Missing required environment variables")
            return

        compute_client, monitor_client, resource_client = get_clients(subscription_id)

        recommendations = []

        vmss_list = compute_client.virtual_machine_scale_sets.list(resource_group_name)
        for vmss in vmss_list:
            try:
                resource_id = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.Compute/virtualMachineScaleSets/{vmss.name}"

                utilization = get_vm_utilization(monitor_client, resource_id)

                if utilization["cpu_samples"] > 0:
                    recommendation = get_right_sizing_recommendation(
                        compute_client, vmss.location, vmss.sku.name, utilization
                    )

                    if recommendation["action"] != "optimal":
                        recommendations.append(
                            {
                                "resource_type": "VM Scale Set",
                                "resource_name": vmss.name,
                                "current_sku": vmss.sku.name,
                                "utilization": utilization,
                                "recommendation": recommendation,
                                "timestamp": utc_timestamp,
                            }
                        )

            except Exception as e:
                logging.error(f"Failed to analyze VMSS {vmss.name}: {str(e)}")

        vm_list = compute_client.virtual_machines.list(resource_group_name)
        for vm in vm_list:
            try:
                resource_id = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.Compute/virtualMachines/{vm.name}"

                utilization = get_vm_utilization(monitor_client, resource_id)

                if utilization["cpu_samples"] > 0:
                    recommendation = get_right_sizing_recommendation(
                        compute_client,
                        vm.location,
                        vm.hardware_profile.vm_size,
                        utilization,
                    )

                    if recommendation["action"] != "optimal":
                        recommendations.append(
                            {
                                "resource_type": "Virtual Machine",
                                "resource_name": vm.name,
                                "current_sku": vm.hardware_profile.vm_size,
                                "utilization": utilization,
                                "recommendation": recommendation,
                                "timestamp": utc_timestamp,
                            }
                        )

            except Exception as e:
                logging.error(f"Failed to analyze VM {vm.name}: {str(e)}")

        if recommendations:
            logging.info(
                f"Generated {len(recommendations)} right-sizing recommendations"
            )
            for rec in recommendations:
                logging.info(
                    f"Recommendation: {rec['resource_name']} - {rec['recommendation']['action']} to {rec['recommendation'].get('recommended_sku', 'N/A')}"
                )
        else:
            logging.info("No right-sizing recommendations generated")

    except Exception as e:
        logging.error(f"Right-sizing analysis failed: {str(e)}")
        raise


@app.function_name(name="HttpTriggerRightsizing")
@app.route(route="rightsizing", auth_level=func.AuthLevel.ANONYMOUS)
def http_trigger_rightsizing(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger for manual right-sizing analysis"""
    logging.info("HTTP trigger for right-sizing analysis called.")

    try:
        subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
        resource_group_name = os.environ.get("AZURE_RESOURCE_GROUP")

        if not subscription_id or not resource_group_name:
            return func.HttpResponse(
                "Missing required environment variables", status_code=500
            )

        compute_client, monitor_client, resource_client = get_clients(subscription_id)

        recommendations = []

        vm_list = compute_client.virtual_machines.list(resource_group_name)
        for vm in vm_list:
            try:
                resource_id = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.Compute/virtualMachines/{vm.name}"
                utilization = get_vm_utilization(monitor_client, resource_id, days=1)

                if utilization["cpu_samples"] > 0:
                    recommendation = get_right_sizing_recommendation(
                        compute_client,
                        vm.location,
                        vm.hardware_profile.vm_size,
                        utilization,
                    )
                    recommendations.append(
                        {
                            "vm_name": vm.name,
                            "current_sku": vm.hardware_profile.vm_size,
                            "cpu_avg": utilization["cpu_avg"],
                            "cpu_max": utilization["cpu_max"],
                            "recommendation": recommendation,
                        }
                    )

            except Exception as e:
                logging.error(f"Failed to analyze VM {vm.name}: {str(e)}")

        return func.HttpResponse(
            json.dumps({"recommendations": recommendations}, indent=2),
            mimetype="application/json",
            status_code=200,
        )

    except Exception as e:
        error_msg = f"Right-sizing analysis failed: {str(e)}"
        logging.error(error_msg)
        return func.HttpResponse(error_msg, status_code=500)
