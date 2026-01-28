"""
AWS Lambda function for Resource Cleanup
Cost Optimization Framework - Cleanup Engine
Cleans up unattached EBS volumes, unused snapshots, and orphaned resources
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import boto3

ec2 = boto3.client("ec2")
sns = boto3.client("sns")


SNAPSHOT_AGE_DAYS = int(os.environ.get("SNAPSHOT_AGE_DAYS", "30"))
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        print("Starting resource cleanup process...")

        unattached_volumes = get_unattached_volumes()
        unused_snapshots = get_unused_snapshots()

        cleanup_results = {
            "volumes_deleted": 0,
            "snapshots_deleted": 0,
            "estimated_savings": 0.0,
        }

        if not DRY_RUN:
            cleanup_results = perform_cleanup(unattached_volumes, unused_snapshots)
        else:
            print("DRY RUN: No resources will be deleted")
            # Calculate potential savings anyway
            for vol in unattached_volumes:
                cleanup_results["estimated_savings"] += vol["size"] * 0.1  # Rough estimate

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Cleanup completed successfully",
                    "dry_run": DRY_RUN,
                    "volumes_found": len(unattached_volumes),
                    "snapshots_found": len(unused_snapshots),
                    "savings": cleanup_results["estimated_savings"],
                }
            ),
        }

    except Exception as e:
        print(f"Error in cleanup: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def get_unattached_volumes() -> List[Dict[str, Any]]:
    volumes = []
    response = ec2.describe_volumes(
        Filters=[{"Name": "status", "Values": ["available"]}]
    )

    for vol in response["Volumes"]:
        volumes.append(
            {
                "id": vol["VolumeId"],
                "size": vol["Size"],
                "type": vol["VolumeType"],
            }
        )
    return volumes


def get_unused_snapshots() -> List[Dict[str, Any]]:
    snapshots = []
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=SNAPSHOT_AGE_DAYS)

    # Get snapshots owned by the account
    response = ec2.describe_snapshots(OwnerIds=["self"])

    for snap in response["Snapshots"]:
        if snap["StartTime"] < cutoff_time:
            snapshots.append({"id": snap["SnapshotId"], "size": snap.get("VolumeSize", 0)})
    return snapshots


def perform_cleanup(volumes: List[Dict], snapshots: List[Dict]) -> Dict:
    volumes_deleted = 0
    snapshots_deleted = 0
    savings = 0.0

    for vol in volumes:
        try:
            ec2.delete_volume(VolumeId=vol["id"])
            volumes_deleted += 1
            savings += vol["size"] * 0.1  # Est $0.1 per GB/month
        except Exception as e:
            print(f"Failed to delete volume {vol['id']}: {e}")

    for snap in snapshots:
        try:
            ec2.delete_snapshot(SnapshotId=snap["id"])
            snapshots_deleted += 1
            # Snapshot savings are smaller
        except Exception as e:
            print(f"Failed to delete snapshot {snap['id']}: {e}")

    return {
        "volumes_deleted": volumes_deleted,
        "snapshots_deleted": snapshots_deleted,
        "estimated_savings": round(savings, 2),
    }


if __name__ == "__main__":
    print(lambda_handler({}, None))
