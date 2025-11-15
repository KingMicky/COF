"""
Azure Function for Right-Sizing Recommendations
Analyzes VM and VMSS utilization and provides right-sizing recommendations
"""

import azure.functions as func
import logging
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.resource import ResourceManagementClient
from datetime import datetime, timedelta, timezone
import os
import json

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

    # CPU utilization
    cpu_metrics = monitor_client.metrics.list(
        resource_id,
        timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
        interval="PT1H",
        metricnames="Percentage CPU",
        aggregation="Average,Maximum"
    )

    # Memory utilization (if available)
    memory_metrics = monitor_client.metrics.list(
        resource_id,
        timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
        interval="PT1H",
        metricnames="Available Memory Bytes",
        aggregation="Average"
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
        'cpu_avg': sum(cpu_data) / len(cpu_data) if cpu_data else 0,
        'cpu_max': max(cpu_data) if cpu_data else 0,
        'memory_avg': sum(memory_data) / len(memory_data) if memory_data else 0,
        'cpu_samples': len(cpu_data),
        'memory_samples': len(memory_data)
    }

def get_right_sizing_recommendation(current_sku: str, utilization: dict) -> dict:
    """Generate right-sizing recommendation based on utilization"""
    cpu_avg = utilization.get('cpu_avg', 0)
    cpu_max = utilization.get('cpu_max', 0)

    # Simple right-sizing logic
    recommendations = {
        'Standard_B1s': {'cpu': 20, 'next': 'Standard_B1ms', 'prev': None},
        'Standard_B1ms': {'cpu': 40, 'next': 'Standard_B2s', 'prev': 'Standard_B1s'},
        'Standard_B2s': {'cpu': 60, 'next': 'Standard_B2ms', 'prev': 'Standard_B1ms'},
        'Standard_B2ms': {'cpu': 80, 'next': 'Standard_B4ms', 'prev': 'Standard_B2s'},
        'Standard_B4ms': {'cpu': 120, 'next': 'Standard_B8ms', 'prev': 'Standard_B2ms'},
        'Standard_B8ms': {'cpu': 240, 'next': 'Standard_B12ms', 'prev': 'Standard_B4ms'},
        'Standard_B12ms': {'cpu': 360, 'next': 'Standard_B16ms', 'prev': 'Standard_B8ms'},
        'Standard_B16ms': {'cpu': 480, 'next': 'Standard_B20ms', 'prev': 'Standard_B12ms'},
        'Standard_B20ms': {'cpu': 640, 'next': None, 'prev': 'Standard_B16ms'}
    }

    if current_sku not in recommendations:
        return {'action': 'unknown', 'reason': 'SKU not in recommendation matrix'}

    sku_info = recommendations[current_sku]

    # Right-size down if consistently underutilized
    if cpu_avg < 20 and cpu_max < 40 and sku_info['prev']:
        return {
            'action': 'downsize',
            'recommended_sku': sku_info['prev'],
            'reason': f'Low utilization (CPU avg: {cpu_avg:.1f}%, max: {cpu_max:.1f}%)',
            'potential_savings': '20-30%'
        }

    # Right-size up if consistently overutilized
    if cpu_avg > 80 or cpu_max > 90:
        if sku_info['next']:
            return {
                'action': 'upsize',
                'recommended_sku': sku_info['next'],
                'reason': f'High utilization (CPU avg: {cpu_avg:.1f}%, max: {cpu_max:.1f}%)',
                'potential_savings': 'N/A - performance improvement'
            }
        else:
            return {
                'action': 'monitor',
                'reason': f'High utilization but already at largest SKU'
            }

    return {
        'action': 'optimal',
        'reason': f'Current utilization is optimal (CPU avg: {cpu_avg:.1f}%, max: {cpu_max:.1f}%)'
    }

@func.schedule(schedule="0 0 */1 * * *", arg_name="myTimer", run_on_startup=False,
              use_monitor=False)
def right_sizing_analysis(myTimer: func.TimerRequest) -> None:
    """Right-sizing analysis function triggered daily"""
    utc_timestamp = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()

    if myTimer.past_due:
        logging.info('The timer is past due!')
    logging.info('Right-sizing analysis started at %s', utc_timestamp)

    try:
        # Get environment variables
        subscription_id = os.environ.get('AZURE_SUBSCRIPTION_ID')
        resource_group_name = os.environ.get('AZURE_RESOURCE_GROUP')

        if not subscription_id or not resource_group_name:
            logging.error("Missing required environment variables")
            return

        # Initialize clients
        compute_client, monitor_client, resource_client = get_clients(subscription_id)

        recommendations = []

        # Analyze VM Scale Sets
        vmss_list = compute_client.virtual_machine_scale_sets.list(resource_group_name)
        for vmss in vmss_list:
            try:
                # Get resource ID for monitoring
                resource_id = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.Compute/virtualMachineScaleSets/{vmss.name}"

                # Get utilization data
                utilization = get_vm_utilization(monitor_client, resource_id)

                if utilization['cpu_samples'] > 0:
                    recommendation = get_right_sizing_recommendation(vmss.sku.name, utilization)

                    if recommendation['action'] != 'optimal':
                        recommendations.append({
                            'resource_type': 'VM Scale Set',
                            'resource_name': vmss.name,
                            'current_sku': vmss.sku.name,
                            'utilization': utilization,
                            'recommendation': recommendation,
                            'timestamp': utc_timestamp
                        })

            except Exception as e:
                logging.error(f"Failed to analyze VMSS {vmss.name}: {str(e)}")

        # Analyze individual VMs
        vm_list = compute_client.virtual_machines.list(resource_group_name)
        for vm in vm_list:
            try:
                # Get resource ID for monitoring
                resource_id = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.Compute/virtualMachines/{vm.name}"

                # Get utilization data
                utilization = get_vm_utilization(monitor_client, resource_id)

                if utilization['cpu_samples'] > 0:
                    recommendation = get_right_sizing_recommendation(vm.hardware_profile.vm_size, utilization)

                    if recommendation['action'] != 'optimal':
                        recommendations.append({
                            'resource_type': 'Virtual Machine',
                            'resource_name': vm.name,
                            'current_sku': vm.hardware_profile.vm_size,
                            'utilization': utilization,
                            'recommendation': recommendation,
                            'timestamp': utc_timestamp
                        })

            except Exception as e:
                logging.error(f"Failed to analyze VM {vm.name}: {str(e)}")

        # Store recommendations (in a real implementation, this would go to a database or storage account)
        if recommendations:
            logging.info(f"Generated {len(recommendations)} right-sizing recommendations")
            for rec in recommendations:
                logging.info(f"Recommendation: {rec['resource_name']} - {rec['recommendation']['action']} to {rec['recommendation'].get('recommended_sku', 'N/A')}")
        else:
            logging.info("No right-sizing recommendations generated")

    except Exception as e:
        logging.error(f"Right-sizing analysis failed: {str(e)}")
        raise

@app.function_name(name="HttpTriggerRightsizing")
@app.route(route="rightsizing", auth_level=func.AuthLevel.ANONYMOUS)
def http_trigger_rightsizing(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger for manual right-sizing analysis"""
    logging.info('HTTP trigger for right-sizing analysis called.')

    try:
        # Get environment variables
        subscription_id = os.environ.get('AZURE_SUBSCRIPTION_ID')
        resource_group_name = os.environ.get('AZURE_RESOURCE_GROUP')

        if not subscription_id or not resource_group_name:
            return func.HttpResponse(
                "Missing required environment variables",
                status_code=500
            )

        # Initialize clients
        compute_client, monitor_client, resource_client = get_clients(subscription_id)

        recommendations = []

        # Analyze VMs (simplified for HTTP trigger)
        vm_list = compute_client.virtual_machines.list(resource_group_name)
        for vm in vm_list:
            try:
                resource_id = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.Compute/virtualMachines/{vm.name}"
                utilization = get_vm_utilization(monitor_client, resource_id, days=1)  # Last 24 hours

                if utilization['cpu_samples'] > 0:
                    recommendation = get_right_sizing_recommendation(vm.hardware_profile.vm_size, utilization)
                    recommendations.append({
                        'vm_name': vm.name,
                        'current_sku': vm.hardware_profile.vm_size,
                        'cpu_avg': utilization['cpu_avg'],
                        'cpu_max': utilization['cpu_max'],
                        'recommendation': recommendation
                    })

            except Exception as e:
                logging.error(f"Failed to analyze VM {vm.name}: {str(e)}")

        return func.HttpResponse(
            json.dumps({'recommendations': recommendations}, indent=2),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        error_msg = f"Right-sizing analysis failed: {str(e)}"
        logging.error(error_msg)
        return func.HttpResponse(error_msg, status_code=500)
