"""
Azure Function for Resource Cleanup
Cleans up unattached disks, unused snapshots, and orphaned resources
"""

import azure.functions as func
import logging
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.resource import ResourceManagementClient
from datetime import datetime, timedelta, timezone
import os

app = func.FunctionApp()

def get_clients(subscription_id: str):
    """Initialize Azure management clients"""
    credential = DefaultAzureCredential()
    compute_client = ComputeManagementClient(credential, subscription_id)
    resource_client = ResourceManagementClient(credential, subscription_id)
    return compute_client, resource_client

def find_unattached_disks(compute_client, resource_group_name: str) -> list:
    """Find disks that are not attached to any VM"""
    unattached_disks = []

    try:
        disks = compute_client.disks.list_by_resource_group(resource_group_name)

        for disk in disks:
            # Check if disk is unattached
            if not hasattr(disk, 'disk_state') or disk.disk_state != 'Attached':
                # Additional check: verify no VM is using this disk
                vms = compute_client.virtual_machines.list(resource_group_name)
                is_attached = False

                for vm in vms:
                    if vm.storage_profile:
                        # Check OS disk
                        if (vm.storage_profile.os_disk and
                            vm.storage_profile.os_disk.managed_disk and
                            vm.storage_profile.os_disk.managed_disk.id == disk.id):
                            is_attached = True
                            break

                        # Check data disks
                        if vm.storage_profile.data_disks:
                            for data_disk in vm.storage_profile.data_disks:
                                if (data_disk.managed_disk and
                                    data_disk.managed_disk.id == disk.id):
                                    is_attached = True
                                    break

                    if is_attached:
                        break

                if not is_attached:
                    unattached_disks.append({
                        'name': disk.name,
                        'id': disk.id,
                        'size_gb': disk.disk_size_gb,
                        'sku': disk.sku.name if disk.sku else 'Unknown',
                        'created': disk.time_created.isoformat() if disk.time_created else 'Unknown'
                    })

    except Exception as e:
        logging.error(f"Error finding unattached disks: {str(e)}")

    return unattached_disks

def find_unused_snapshots(compute_client, resource_group_name: str) -> list:
    """Find snapshots that are not being used"""
    unused_snapshots = []

    try:
        snapshots = compute_client.snapshots.list_by_resource_group(resource_group_name)

        for snapshot in snapshots:
            # Check if snapshot is older than 30 days and not tagged as permanent
            age_days = (datetime.now(timezone.utc) - snapshot.time_created).days if snapshot.time_created else 0
            tags = snapshot.tags or {}

            if age_days > 30 and tags.get('Retention', '').lower() != 'permanent':
                unused_snapshots.append({
                    'name': snapshot.name,
                    'id': snapshot.id,
                    'size_gb': snapshot.disk_size_gb,
                    'created': snapshot.time_created.isoformat() if snapshot.time_created else 'Unknown',
                    'age_days': age_days
                })

    except Exception as e:
        logging.error(f"Error finding unused snapshots: {str(e)}")

    return unused_snapshots

def find_idle_vms(compute_client, resource_group_name: str) -> list:
    """Find VMs that have been stopped for extended periods"""
    idle_vms = []

    try:
        vms = compute_client.virtual_machines.list(resource_group_name)

        for vm in vms:
            # Get VM status
            vm_status = compute_client.virtual_machines.get(
                resource_group_name, vm.name, expand='instanceView'
            )

            # Check if VM is deallocated/stopped
            is_stopped = any(status.code in ['PowerState/deallocated', 'PowerState/stopped']
                           for status in vm_status.instance_view.statuses)

            if is_stopped:
                # Check tags for auto-shutdown exemption
                tags = vm.tags or {}
                if tags.get('AutoShutdown', '').lower() != 'false':
                    # In a real implementation, you'd check last start time
                    # For now, we'll flag VMs that are stopped
                    idle_vms.append({
                        'name': vm.name,
                        'id': vm.id,
                        'size': vm.hardware_profile.vm_size,
                        'power_state': 'stopped'
                    })

    except Exception as e:
        logging.error(f"Error finding idle VMs: {str(e)}")

    return idle_vms

@func.schedule(schedule="0 0 2 * * *", arg_name="myTimer", run_on_startup=False,
              use_monitor=False)
def cleanup_resources(myTimer: func.TimerRequest) -> None:
    """Cleanup function triggered bi-weekly (2nd day of month)"""
    utc_timestamp = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()

    if myTimer.past_due:
        logging.info('The timer is past due!')
    logging.info('Resource cleanup started at %s', utc_timestamp)

    try:
        # Get environment variables
        subscription_id = os.environ.get('AZURE_SUBSCRIPTION_ID')
        resource_group_name = os.environ.get('AZURE_RESOURCE_GROUP')
        dry_run = os.environ.get('DRY_RUN', 'true').lower() == 'true'

        if not subscription_id or not resource_group_name:
            logging.error("Missing required environment variables")
            return

        # Initialize clients
        compute_client, resource_client = get_clients(subscription_id)

        cleanup_summary = {
            'unattached_disks': [],
            'unused_snapshots': [],
            'idle_vms': [],
            'dry_run': dry_run,
            'timestamp': utc_timestamp
        }

        # Find unattached disks
        unattached_disks = find_unattached_disks(compute_client, resource_group_name)
        cleanup_summary['unattached_disks'] = unattached_disks

        # Find unused snapshots
        unused_snapshots = find_unused_snapshots(compute_client, resource_group_name)
        cleanup_summary['unused_snapshots'] = unused_snapshots

        # Find idle VMs
        idle_vms = find_idle_vms(compute_client, resource_group_name)
        cleanup_summary['idle_vms'] = idle_vms

        # Perform cleanup if not dry run
        if not dry_run:
            # Delete unattached disks
            for disk in unattached_disks:
                try:
                    compute_client.disks.delete(resource_group_name, disk['name'])
                    logging.info(f"Deleted unattached disk: {disk['name']}")
                except Exception as e:
                    logging.error(f"Failed to delete disk {disk['name']}: {str(e)}")

            # Delete unused snapshots
            for snapshot in unused_snapshots:
                try:
                    compute_client.snapshots.delete(resource_group_name, snapshot['name'])
                    logging.info(f"Deleted unused snapshot: {snapshot['name']}")
                except Exception as e:
                    logging.error(f"Failed to delete snapshot {snapshot['name']}: {str(e)}")

            # Note: VMs are not automatically deleted - just flagged for review
        else:
            logging.info("DRY RUN: No resources were actually deleted")

        # Log summary
        logging.info(f"Cleanup completed. Found {len(unattached_disks)} unattached disks, "
                    f"{len(unused_snapshots)} unused snapshots, {len(idle_vms)} idle VMs")

    except Exception as e:
        logging.error(f"Resource cleanup failed: {str(e)}")
        raise

@app.function_name(name="HttpTriggerCleanup")
@app.route(route="cleanup", auth_level=func.AuthLevel.ANONYMOUS)
def http_trigger_cleanup(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger for manual cleanup analysis"""
    logging.info('HTTP trigger for cleanup analysis called.')

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
        compute_client, resource_client = get_clients(subscription_id)

        # Perform analysis
        unattached_disks = find_unattached_disks(compute_client, resource_group_name)
        unused_snapshots = find_unused_snapshots(compute_client, resource_group_name)
        idle_vms = find_idle_vms(compute_client, resource_group_name)

        result = {
            'unattached_disks': unattached_disks,
            'unused_snapshots': unused_snapshots,
            'idle_vms': idle_vms,
            'timestamp': datetime.utcnow().isoformat()
        }

        return func.HttpResponse(
            f"Cleanup analysis completed.\n"
            f"Unattached disks: {len(unattached_disks)}\n"
            f"Unused snapshots: {len(unused_snapshots)}\n"
            f"Idle VMs: {len(idle_vms)}\n\n"
            f"Details: {result}",
            status_code=200
        )

    except Exception as e:
        error_msg = f"Cleanup analysis failed: {str(e)}"
        logging.error(error_msg)
        return func.HttpResponse(error_msg, status_code=500)
