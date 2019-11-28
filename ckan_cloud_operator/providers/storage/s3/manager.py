import json

from ckan_cloud_operator import logs, kubectl
from ckan_cloud_operator.providers.cluster.aws.manager import aws_check_output, get_aws_credentials

from .constants import PROVIDER_ID


def initialize(*args, **kwargs):
    # No actions needed
    pass


def create_bucket(instance_id, region=None, exists_ok=False, dry_run=False):
    if not region:
        region = get_aws_credentials().get('region')

    assert region, 'No default region set for the cluster'

    bucket_exists = instance_id in list_s3_buckets(names_only=True)
    if not exists_ok and bucket_exists:
        raise Exception('Bucket for this instance already exists')

    if not dry_run and not bucket_exists:
        aws_check_output(f's3 mb s3://{instance_id} --region {region}')

    return f's3://{instance_id}'
    

def delete_bucket(instance_id, dry_run=False):
    if instance_id not in list_s3_buckets(names_only=True):
        logs.warning(f'No bucket found for the instance "{instance_id}". Skipping.')
        return

    cmd = f's3 rm s3://{instance_id} --recursive'
    if dry_run:
        cmd += ' --dryrun'

    # Two steps deletion. See the `aws s3 rb help`
    aws_check_output(cmd)
    if not dry_run:
        aws_check_output(f's3 rb s3://{instance_id}')


def get_bucket(instance_id):
    if instance_id not in list_s3_buckets(names_only=True):
        logs.warning(f'No bucket found for the instance "{instance_id}" on S3. Skipping.')
        return

    instance = kubectl.get(f'ckancloudckaninstance {instance_id}')
    bucket = instance['spec'].get('bucket').get(PROVIDER_ID)
    if not bucket:
        logs.warning('This instance does not have S3 bucket attached.')
        return

    return {
        'instance_id': instance_id,
        'bucket': bucket
    }


def list_buckets():
    """Returns list of buckets attached to CKAN Instances"""
    result = []
    for item in kubectl.get('ckancloudckaninstance').get('items', []):
        bucket = item['spec'].get('bucket', {}).get(PROVIDER_ID)
        if not bucket:
            continue
        result.append({
            'instance_id': item['spec']['id'],
            'bucket': bucket
        })

    return result


def list_s3_buckets(names_only=False):
    """Returns list of buckets on S3"""
    data = aws_check_output('s3 ls').decode()

    result = []
    for line in data.split('\n'):
        if not line.strip():
            continue

        timestamp, name = line.rsplit(maxsplit=1)
        if names_only:
            result.append(name)
        else:
            result.append([timestamp, name])

    return result
