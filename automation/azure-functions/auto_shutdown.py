"""
Azure Function for Auto-Shutdown of Compute Resources
Automatically shuts down VMs and VM Scale Sets based on schedule and tags
"""

import azure.functions as func
import logging
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.resource import ResourceManagementClient
from datetime import datetime, timezone
import os

app = func.FunctionApp()

def get_compute_clients(subscription_id: str):
    """Initialize Azure compute and resource management clients"""
    credential = DefaultAzureCredential()
    compute_client = ComputeManagementClient(credential, subscription_id)
    resource_client = ResourceManagementClient(credential, subscription_id)
    return compute_client, resource_client

def should_shutdown_vm(vm, auto_shutdown_tag: str, current_hour: int) -> bool:
    """Determine if VM should be shut down based on tags and schedule"""
    tags = vm.tags or {}

    # Check if auto-shutdown is enabled
    if tags.get('AutoShutdown', '').lower() != 'true':
        return False

    # Check environment - don't shutdown production by default
    environment = tags.get('Environment', '').lower()
    if environment == 'prod':
        return False

    # Check schedule (assuming 6 PM shutdown)
    if auto_shutdown_tag == 'weekdays' and current_hour >= 18:
        # Check if it's a weekday (Monday=0, Sunday=6)
        current_day = datetime.now(timezone.utc).weekday()
        return current_day < 5  # Monday to Friday

    return auto_shutdown_tag == 'always'

@func.schedule(schedule="0 */1 * * * *", arg_name="myTimer", run_on_startup=True,
              use_monitor=False)
def auto_shutdown_compute(myTimer: func.TimerRequest) -> None:
    """Auto-shutdown function triggered every minute"""
    utc_timestamp = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()

    if myTimer.past_due:
        logging.info('The timer is past due!')
    logging.info('Auto-shutdown function started at %s', utc_timestamp)

    try:
        # Get environment variables
        subscription_id = os.environ.get('AZURE_SUBSCRIPTION_ID')
        resource_group_name = os.environ.get('AZURE_RESOURCE_GROUP')

        if not subscription_id or not resource_group_name:
            logging.error("Missing required environment variables")
            return

        # Initialize clients
        compute_client, resource_client = get_compute_clients(subscription_id)

        # Get current time
        current_time = datetime.now(timezone.utc)
        current_hour = current_time.hour

        shutdown_count = 0

        # Process VM Scale Sets
        vmss_list = compute_client.virtual_machine_scale_sets.list(resource_group_name)
        for vmss in vmss_list:
            if should_shutdown_vm(vmss, 'weekdays', current_hour):
                try:
                    # Power off VM Scale Set instances
                    compute_client.virtual_machine_scale_sets.power_off(
                        resource_group_name,
                        vmss.name
                    )
                    logging.info(f"Shut down VM Scale Set: {vmss.name}")
                    shutdown_count += 1
                except Exception as e:
                    logging.error(f"Failed to shutdown VMSS {vmss.name}: {str(e)}")

        # Process individual VMs
        vm_list = compute_client.virtual_machines.list(resource_group_name)
        for vm in vm_list:
            if should_shutdown_vm(vm, 'weekdays', current_hour):
                try:
                    # Check if VM is already deallocated
                    vm_status = compute_client.virtual_machines.get(
                        resource_group_name, vm.name, expand='instanceView'
                    )

                    # Only shutdown if running
                    if any(status.code == 'PowerState/running' for status in vm_status.instance_view.statuses):
                        async_shutdown = compute_client.virtual_machines.power_off(
                            resource_group_name, vm.name
                        )
                        async_shutdown.wait()
                        logging.info(f"Shut down VM: {vm.name}")
                        shutdown_count += 1
                except Exception as e:
                    logging.error(f"Failed to shutdown VM {vm.name}: {str(e)}")

        logging.info(f"Auto-shutdown completed. Shut down {shutdown_count} resources.")

    except Exception as e:
        logging.error(f"Auto-shutdown function failed: {str(e)}")
        raise

@app.function_name(name="HttpTriggerShutdown")
@app.route(route="shutdown", auth_level=func.AuthLevel.ANONYMOUS)
def http_trigger_shutdown(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger for manual shutdown operations"""
    logging.info('HTTP trigger for manual shutdown called.')

    try:
        # Parse request parameters
        resource_type = req.params.get('type', 'vm')  # vm or vmss
        resource_name = req.params.get('name')
        resource_group = req.params.get('resource_group') or os.environ.get('AZURE_RESOURCE_GROUP')

        if not resource_name or not resource_group:
            return func.HttpResponse(
                "Missing required parameters: name and resource_group",
                status_code=400
            )

        subscription_id = os.environ.get('AZURE_SUBSCRIPTION_ID')
        if not subscription_id:
            return func.HttpResponse(
                "AZURE_SUBSCRIPTION_ID environment variable not set",
                status_code=500
            )

        # Initialize client
        compute_client, _ = get_compute_clients(subscription_id)

        # Perform shutdown based on type
        if resource_type.lower() == 'vmss':
            compute_client.virtual_machine_scale_sets.power_off(
                resource_group, resource_name
            )
            message = f"VM Scale Set {resource_name} shutdown initiated"
        else:
            async_shutdown = compute_client.virtual_machines.power_off(
                resource_group, resource_name
            )
            async_shutdown.wait()
            message = f"VM {resource_name} shutdown completed"

        logging.info(message)
        return func.HttpResponse(message, status_code=200)

    except Exception as e:
        error_msg = f"Shutdown failed: {str(e)}"
        logging.error(error_msg)
        return func.HttpResponse(error_msg, status_code=500)
