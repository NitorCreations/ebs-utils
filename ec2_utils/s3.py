from ec2_utils.clients import s3_resource
from ec2_utils.utils import prune_array, delete_selected

def prune_s3_object_versions(bucket=None, prefix="", ten_minutely=288, hourly=168,
                             daily=30, weekly=13, monthly=6, yearly=3, dry_run=False):
    bucket_res = s3_resource().Bucket(bucket)
    versions = bucket_res.object_versions.filter(Prefix=prefix)
    #def prune_array(prunable, time_func, group_by_func, ten_minutely=None,
    #                hourly=None, daily=None, weekly=None, monthly=None, yearly=None,
    #                dry_run=False):
    time_func = lambda version: version.last_modified
    keep, delete = prune_array(versions, time_func,
                               lambda version: version.key,
                               ten_minutely=ten_minutely, hourly=hourly,
                               daily=daily, weekly=weekly, monthly=monthly,
                               yearly=yearly)
    delete_selected(versions, delete, lambda v: v.key,
                    time_func, dry_run=dry_run)
