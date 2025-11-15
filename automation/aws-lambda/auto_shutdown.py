"""
AWS Lambda function for automated shutdown of idle resources
Cost Optimization Framework - Auto Shutdown Engine
"""

import boto3
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Initialize AWS clients
ec2 = boto3.client('ec2')
cloudwatch = boto3.client('cloudwatch')
sns = boto3.client('sns')

# Configuration
IDLE_THRESHOLD_HOURS = int(os.environ.get('IDLE_THRESHOLD_HOURS', '168'))  # 7 days
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')
EXCLUDED_TAGS = os.environ.get('EXCLUDED_TAGS', 'AutoShutdown=false').split(',')

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for auto-shutdown functionality
    """
    try:
        print("Starting auto-shutdown process...")

        # Get idle instances
        idle_instances = get_idle_instances()

        # Shutdown idle instances
        shutdown_results = shutdown_instances(idle_instances)

        # Send notification
        if SNS_TOPIC_ARN and shutdown_results['shutdown_count'] > 0:
            send_notification(shutdown_results)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Auto-shutdown completed successfully',
                'shutdown_count': shutdown_results['shutdown_count'],
                'total_savings': shutdown_results['estimated_savings']
            })
        }

    except Exception as e:
        print(f"Error in auto-shutdown: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }

def get_idle_instances() -> List[Dict[str, Any]]:
    """
    Identify idle EC2 instances based on CPU utilization
    """
    idle_instances = []
    cutoff_time = datetime.utcnow() - timedelta(hours=IDLE_THRESHOLD_HOURS)

    # Get all running instances
    response = ec2.describe_instances(
        Filters=[
            {'Name': 'instance-state-name', 'Values': ['running']},
            {'Name': 'tag:ManagedBy', 'Values': ['cost-optimization-framework']}
        ]
    )

    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']

            # Check if instance should be excluded
            if should_exclude_instance(instance):
                continue

            # Check CPU utilization over the last week
            if is_instance_idle(instance_id, cutoff_time):
                idle_instances.append({
                    'instance_id': instance_id,
                    'instance_type': instance['InstanceType'],
                    'launch_time': instance['LaunchTime'].isoformat(),
                    'tags': {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                })

    return idle_instances

def should_exclude_instance(instance: Dict[str, Any]) -> bool:
    """
    Check if instance should be excluded from auto-shutdown
    """
    tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}

    # Check excluded tags
    for excluded_tag in EXCLUDED_TAGS:
        key, value = excluded_tag.split('=')
        if tags.get(key) == value:
            return True

    # Exclude production instances
    if tags.get('Environment') == 'prod':
        return True

    return False

def is_instance_idle(instance_id: str, cutoff_time: datetime) -> bool:
    """
    Check if instance has been idle based on CloudWatch metrics
    """
    try:
        response = cloudwatch.get_metric_statistics(
            Namespace='AWS/EC2',
            MetricName='CPUUtilization',
            Dimensions=[
                {'Name': 'InstanceId', 'Value': instance_id}
            ],
            StartTime=cutoff_time,
            EndTime=datetime.utcnow(),
            Period=3600,  # 1 hour
            Statistics=['Average']
        )

        # If no data points or all below threshold, consider idle
        if not response['Datapoints']:
            return True

        # Check if average CPU is below 5% for most of the period
        low_cpu_datapoints = [dp for dp in response['Datapoints'] if dp['Average'] < 5.0]
        return len(low_cpu_datapoints) / len(response['Datapoints']) > 0.8

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
            # Stop the instance
            ec2.stop_instances(InstanceIds=[instance['instance_id']])

            # Calculate estimated savings (rough estimate based on instance type)
            hourly_rate = get_instance_hourly_rate(instance['instance_type'])
            estimated_savings += hourly_rate * 24 * 30  # Monthly savings

            shutdown_count += 1
            print(f"Shutdown instance: {instance['instance_id']}")

        except Exception as e:
            print(f"Error shutting down {instance['instance_id']}: {str(e)}")

    return {
        'shutdown_count': shutdown_count,
        'estimated_savings': round(estimated_savings, 2),
        'instances': [inst['instance_id'] for inst in instances[:shutdown_count]]
    }

def get_instance_hourly_rate(instance_type: str) -> float:
    """
    Get approximate hourly rate for instance type (USD)
    This is a simplified mapping - in production, use AWS Pricing API
    """
    rates = {
        't3.micro': 0.0104,
        't3.small': 0.0208,
        't3.medium': 0.0416,
        'm5.large': 0.096,
        'm5.xlarge': 0.192,
    }
    return rates.get(instance_type, 0.05)  # Default rate

def send_notification(results: Dict[str, Any]) -> None:
    """
    Send SNS notification about shutdown actions
    """
    try:
        message = f"""
Cost Optimization Alert - Auto Shutdown Completed

Shutdown Summary:
- Instances shutdown: {results['shutdown_count']}
- Estimated monthly savings: ${results['estimated_savings']}
- Instances: {', '.join(results['instances'])}

This action was performed automatically by the Cost Optimization Framework.
"""

        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject='Cost Optimization - Auto Shutdown Report',
            Message=message
        )

    except Exception as e:
        print(f"Error sending notification: {str(e)}")

if __name__ == '__main__':
    # For local testing
    test_event = {}
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))
