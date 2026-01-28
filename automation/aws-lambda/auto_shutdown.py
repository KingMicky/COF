import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

import boto3

ec2 = boto3.client("ec2")
cloudwatch = boto3.client("cloudwatch")
sns = boto3.client("sns")


IDLE_THRESHOLD_HOURS = int(os.environ.get("IDLE_THRESHOLD_HOURS", "168"))
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN")
EXCLUDED_TAGS = os.environ.get("EXCLUDED_TAGS", "AutoShutdown=false").split(",")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        print("Starting auto-shutdown process...")

        idle_instances = get_idle_instances()

        shutdown_results = shutdown_instances(idle_instances)

        if SNS_TOPIC_ARN and shutdown_results["shutdown_count"] > 0:
            send_notification(shutdown_results)

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Auto-shutdown completed successfully",
                    "shutdown_count": shutdown_results["shutdown_count"],
                    "total_savings": shutdown_results["estimated_savings"],
                }
            ),
        }

    except Exception as e:
        print(f"Error in auto-shutdown: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def get_idle_instances() -> List[Dict[str, Any]]:
    idle_instances = []
    cutoff_time = datetime.utcnow() - timedelta(hours=IDLE_THRESHOLD_HOURS)

    paginator = ec2.get_paginator("describe_instances")
    pages = paginator.paginate(
        Filters=[
            {"Name": "instance-state-name", "Values": ["running"]},
            {"Name": "tag:ManagedBy", "Values": ["cost-optimization-framework"]},
        ]
    )

    for page in pages:
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                instance_id = instance["InstanceId"]

                if should_exclude_instance(instance):
                    continue

                if is_instance_idle(instance_id, cutoff_time):
                    idle_instances.append(
                        {
                            "instance_id": instance_id,
                            "instance_type": instance["InstanceType"],
                            "launch_time": instance["LaunchTime"].isoformat(),
                            "tags": {
                                tag["Key"]: tag["Value"]
                                for tag in instance.get("Tags", [])
                            },
                        }
                    )

    return idle_instances


def should_exclude_instance(instance: Dict[str, Any]) -> bool:
    tags = {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])}

    for excluded_tag in EXCLUDED_TAGS:
        if "=" in excluded_tag:
            key, value = excluded_tag.split("=")
            if tags.get(key) == value:
                return True

    if tags.get("Environment") == "prod":
        return True

    return False


def is_instance_idle(instance_id: str, cutoff_time: datetime) -> bool:
    try:
        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName="CPUUtilization",
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
            StartTime=cutoff_time,
            EndTime=datetime.utcnow(),
            Period=3600,
            Statistics=["Average"],
        )

        if not response["Datapoints"]:
            return True

        low_cpu_datapoints = [
            dp for dp in response["Datapoints"] if dp["Average"] < 5.0
        ]
        return len(low_cpu_datapoints) / len(response["Datapoints"]) > 0.8

    except Exception as e:
        print(f"Error checking CPU utilization for {instance_id}: {str(e)}")
        return False


def shutdown_instances(instances: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Shutdown the identified idle instances
    """
    shutdown_count = 0
    estimated_savings = 0.0

    for instance in instances:
        try:
            ec2.stop_instances(InstanceIds=[instance["instance_id"]])

            hourly_rate = get_instance_hourly_rate(instance["instance_type"])
            estimated_savings += hourly_rate * 24 * 30

            shutdown_count += 1
            print(f"Shutdown instance: {instance['instance_id']}")

        except Exception as e:
            print(f"Error shutting down {instance['instance_id']}: {str(e)}")

    return {
        "shutdown_count": shutdown_count,
        "estimated_savings": round(estimated_savings, 2),
        "instances": [inst["instance_id"] for inst in instances[:shutdown_count]],
    }


def get_instance_hourly_rate(instance_type: str) -> float:
    rates = {
        "t3.micro": 0.0104,
        "t3.small": 0.0208,
        "t3.medium": 0.0416,
        "m5.large": 0.096,
        "m5.xlarge": 0.192,
    }
    return rates.get(instance_type, 0.05)


def send_notification(results: Dict[str, Any]) -> None:
    try:
        message = f"""
Cost Optimization Alert - Auto Shutdown Completed

Shutdown Summary:
- Instances shutdown: {results["shutdown_count"]}
- Estimated monthly savings: ${results["estimated_savings"]}
- Instances: {", ".join(results["instances"])}

This action was performed automatically by the Cost Optimization Framework.
"""

        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="Cost Optimization - Auto Shutdown Report",
            Message=message,
        )

    except Exception as e:
        print(f"Error sending notification: {str(e)}")


if __name__ == "__main__":
    test_event = {}
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))
