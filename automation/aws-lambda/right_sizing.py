"""
AWS Lambda function for right-sizing recommendations
Cost Optimization Framework - Right-Sizing Engine
"""

import boto3
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from statistics import mean

# Initialize AWS clients
ec2 = boto3.client('ec2')
cloudwatch = boto3.client('cloudwatch')
sns = boto3.client('sns')

# Configuration
ANALYSIS_PERIOD_DAYS = int(os.environ.get('ANALYSIS_PERIOD_DAYS', '30'))
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')
CPU_THRESHOLD_HIGH = float(os.environ.get('CPU_THRESHOLD_HIGH', '80.0'))
CPU_THRESHOLD_LOW = float(os.environ.get('CPU_THRESHOLD_LOW', '10.0'))
MEMORY_THRESHOLD_HIGH = float(os.environ.get('MEMORY_THRESHOLD_HIGH', '80.0'))
MEMORY_THRESHOLD_LOW = float(os.environ.get('MEMORY_THRESHOLD_LOW', '10.0'))

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for right-sizing analysis
    """
    try:
        print("Starting right-sizing analysis...")

        # Get all running instances
        instances = get_running_instances()

        # Analyze each instance
        recommendations = []
        for instance in instances:
            recommendation = analyze_instance(instance)
            if recommendation:
                recommendations.append(recommendation)

        # Generate report
        report = generate_report(recommendations)

        # Send notification if recommendations found
        if SNS_TOPIC_ARN and recommendations:
            send_notification(report)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Right-sizing analysis completed',
                'recommendations_count': len(recommendations),
                'potential_savings': report['total_savings'],
                'report': report
            })
        }

    except Exception as e:
        print(f"Error in right-sizing analysis: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }

def get_running_instances() -> List[Dict[str, Any]]:
    """
    Get all running EC2 instances managed by cost optimization framework
    """
    instances = []

    response = ec2.describe_instances(
        Filters=[
            {'Name': 'instance-state-name', 'Values': ['running']},
            {'Name': 'tag:ManagedBy', 'Values': ['cost-optimization-framework']}
        ]
    )

    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instances.append({
                'instance_id': instance['InstanceId'],
                'instance_type': instance['InstanceType'],
                'launch_time': instance['LaunchTime'],
                'tags': {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
            })

    return instances

def analyze_instance(instance: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze single instance for right-sizing opportunities
    """
    instance_id = instance['instance_id']
    current_type = instance['instance_type']

    try:
        # Get CPU utilization metrics
        cpu_metrics = get_metric_data(instance_id, 'CPUUtilization', 'AWS/EC2')

        # Get memory utilization (if available via CloudWatch agent)
        memory_metrics = get_metric_data(instance_id, 'mem_used_percent', 'CWAgent')

        if not cpu_metrics:
            return None

        # Calculate average utilization
        avg_cpu = mean([dp['Average'] for dp in cpu_metrics])
        avg_memory = mean([dp['Average'] for dp in memory_metrics]) if memory_metrics else None

        # Determine right-sizing recommendation
        recommendation = get_right_sizing_recommendation(
            current_type, avg_cpu, avg_memory
        )

        if recommendation['recommended_type'] != current_type:
            return {
                'instance_id': instance_id,
                'current_type': current_type,
                'recommended_type': recommendation['recommended_type'],
                'avg_cpu': round(avg_cpu, 2),
                'avg_memory': round(avg_memory, 2) if avg_memory else None,
                'reason': recommendation['reason'],
                'estimated_savings': recommendation['savings'],
                'confidence': recommendation['confidence']
            }

    except Exception as e:
        print(f"Error analyzing instance {instance_id}: {str(e)}")

    return None

def get_metric_data(instance_id: str, metric_name: str, namespace: str) -> List[Dict[str, Any]]:
    """
    Get CloudWatch metric data for analysis period
    """
    try:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=ANALYSIS_PERIOD_DAYS)

        response = cloudwatch.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=[
                {'Name': 'InstanceId', 'Value': instance_id}
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,  # 1 hour
            Statistics=['Average']
        )

        return response['Datapoints']

    except Exception as e:
        print(f"Error getting metric data for {instance_id}: {str(e)}")
        return []

def get_right_sizing_recommendation(current_type: str, avg_cpu: float, avg_memory: float) -> Dict[str, Any]:
    """
    Determine right-sizing recommendation based on utilization
    """
    # Simplified right-sizing logic - in production, use more sophisticated algorithms
    instance_family = get_instance_family(current_type)
    current_size = get_instance_size(current_type)

    recommended_type = current_type
    reason = "No change recommended"
    savings = 0.0
    confidence = "Low"

    # CPU-based recommendations
    if avg_cpu > CPU_THRESHOLD_HIGH:
        # Need more CPU - scale up
        new_size = get_next_size_up(current_size)
        if new_size:
            recommended_type = f"{instance_family}.{new_size}"
            reason = f"High CPU utilization ({avg_cpu:.1f}%) - scale up"
            savings = 0  # Actually cost increase, but better performance
            confidence = "High"
    elif avg_cpu < CPU_THRESHOLD_LOW:
        # Underutilized CPU - scale down
        new_size = get_next_size_down(current_size)
        if new_size:
            recommended_type = f"{instance_family}.{new_size}"
            reason = f"Low CPU utilization ({avg_cpu:.1f}%) - scale down"
            savings = calculate_savings(current_type, recommended_type)
            confidence = "Medium"

    # Memory-based recommendations (if available)
    if avg_memory is not None:
        if avg_memory > MEMORY_THRESHOLD_HIGH:
            reason += f", High memory utilization ({avg_memory:.1f}%)"
            confidence = "High"
        elif avg_memory < MEMORY_THRESHOLD_LOW:
            reason += f", Low memory utilization ({avg_memory:.1f}%)"

    return {
        'recommended_type': recommended_type,
        'reason': reason,
        'savings': savings,
        'confidence': confidence
    }

def get_instance_family(instance_type: str) -> str:
    """Extract instance family (e.g., 't3', 'm5')"""
    return instance_type.split('.')[0]

def get_instance_size(instance_type: str) -> str:
    """Extract instance size (e.g., 'micro', 'small')"""
    return instance_type.split('.')[1]

def get_next_size_up(current_size: str) -> str:
    """Get next larger instance size"""
    sizes = ['nano', 'micro', 'small', 'medium', 'large', 'xlarge', '2xlarge', '4xlarge']
    try:
        current_index = sizes.index(current_size)
        if current_index < len(sizes) - 1:
            return sizes[current_index + 1]
    except ValueError:
        pass
    return None

def get_next_size_down(current_size: str) -> str:
    """Get next smaller instance size"""
    sizes = ['nano', 'micro', 'small', 'medium', 'large', 'xlarge', '2xlarge', '4xlarge']
    try:
        current_index = sizes.index(current_size)
        if current_index > 0:
            return sizes[current_index - 1]
    except ValueError:
        pass
    return None

def calculate_savings(current_type: str, recommended_type: str) -> float:
    """
    Calculate monthly savings from right-sizing
    """
    # Simplified pricing - in production, use AWS Pricing API
    hourly_rates = {
        't3.micro': 0.0104,
        't3.small': 0.0208,
        't3.medium': 0.0416,
        'm5.large': 0.096,
        'm5.xlarge': 0.192,
    }

    current_rate = hourly_rates.get(current_type, 0.05)
    recommended_rate = hourly_rates.get(recommended_type, 0.05)

    if recommended_rate < current_rate:
        return (current_rate - recommended_rate) * 24 * 30  # Monthly savings

    return 0.0

def generate_report(recommendations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate summary report of recommendations
    """
    total_savings = sum(rec['estimated_savings'] for rec in recommendations)

    return {
        'analysis_period_days': ANALYSIS_PERIOD_DAYS,
        'total_recommendations': len(recommendations),
        'total_savings': round(total_savings, 2),
        'recommendations': recommendations,
        'generated_at': datetime.utcnow().isoformat()
    }

def send_notification(report: Dict[str, Any]) -> None:
    """
    Send SNS notification with right-sizing recommendations
    """
    try:
        message = f"""
Cost Optimization Alert - Right-Sizing Recommendations

Analysis Summary:
- Period: {report['analysis_period_days']} days
- Recommendations: {report['total_recommendations']}
- Potential Monthly Savings: ${report['total_savings']}

Top Recommendations:
"""

        # Add top 5 recommendations
        sorted_recs = sorted(report['recommendations'],
                           key=lambda x: x['estimated_savings'], reverse=True)[:5]

        for rec in sorted_recs:
            message += f"- {rec['instance_id']}: {rec['current_type']} -> {rec['recommended_type']} (${rec['estimated_savings']:.2f}/month)\n"

        message += "\nReview and apply recommendations via AWS Console or automated scripts."

        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject='Cost Optimization - Right-Sizing Report',
            Message=message
        )

    except Exception as e:
        print(f"Error sending notification: {str(e)}")

if __name__ == '__main__':
    # For local testing
    test_event = {}
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))
