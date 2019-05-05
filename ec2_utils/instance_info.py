import json
import os
import sys
import requests
from requests.exceptions import ConnectionError
from requests.adapters import HTTPAdapter
import tempfile
import time
import boto3
from botocore.exceptions import ClientError, EndpointConnectionError
from urllib3.util.retry import Retry


EC2 = None
SESSION = None
ACCOUNT_ID = None
INSTANCE_DATA = tempfile.gettempdir() + os.sep + 'instance-data.json'
INSTANCE_IDENTITY_URL = 'http://169.254.169.254/latest/dynamic/instance-identity/document'

dthandler = lambda obj: obj.isoformat() if hasattr(obj, 'isoformat') else json.JSONEncoder().default(obj)

def get_retry(url, retries=5, backoff_factor=0.3,
              status_forcelist=(500, 502, 504), session=None, timeout=5):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session.get(url, timeout=5)

def read_if_readable(filename):
    try:
        if os.path.isfile(filename):
            with open(filename) as read_file:
                return read_file.read()
        else:
            return ""
    except:
        return ""

def wait_net_service(server, port, timeout=None):
    """ Wait for network service to appear
        @param timeout: in seconds, if None or 0 wait forever
        @return: True of False, if timeout is None may return only True or
                 throw unhandled network exception
    """
    import socket
    import errno
    s = socket.socket()
    if sys.version < "3":
        # Just make this something that will not be throwns since python 2
        # just has socket.error
        ConnectionRefusedError = EndpointConnectionError
    if timeout:
        from time import time as now
        # time module is needed to calc timeout shared between two exceptions
        end = now() + timeout
    while True:
        try:
            if timeout:
                next_timeout = end - now()
                if next_timeout < 0:
                    return False
                else:
                    s.settimeout(next_timeout)
            s.connect((server, port))
        except socket.timeout as err:
            # this exception occurs only if timeout is set
            if timeout:
                return False
        except ConnectionRefusedError:
            s.close()
            return False
        except socket.error as err:
            # catch timeout exception from underlying network library
            # this one is different from socket.timeout
            if not isinstance(err.args, tuple) or err[0] != errno.ETIMEDOUT or err[0] != errno.ECONNREFUSED:
                raise
            elif err[0] == errno.ECONNREFUSED:
                s.close()
                return False
        else:
            s.close()
            return True

def ec2():
    global EC2
    if not EC2:
        # region() has one benefit over default resolving - defaults to
        # ec2 instance region if on ec2 and otherwise unset
        EC2 = session().client("ec2", region_name=region()) 
    return EC2

def session():
    global SESSION
    if not SESSION:
        SESSION = boto3.session.Session()
    return SESSION

def resolve_account():
    global ACCOUNT_ID
    if not ACCOUNT_ID:
        try:
            sts = session().client("sts", region_name=region())
            ACCOUNT_ID = sts.get_caller_identity()['Account']
        except BaseException:
            pass
    return ACCOUNT_ID
    

def set_region():
    """ Sets the environment variable AWS_DEFAULT_REGION if not already set
        to a sensible default
    """
    if 'AWS_DEFAULT_REGION' not in os.environ:
        os.environ['AWS_DEFAULT_REGION'] = region()

def region():
    """ Get default region - the region of the instance if run in an EC2 instance
    """
    # If it is set in the environment variable, use that
    if 'AWS_DEFAULT_REGION' in os.environ:
        return os.environ['AWS_DEFAULT_REGION']
    else:
        # Otherwise it might be configured in AWS credentials
        if session().region_name:
            return session().region_name
        # If not configured and being called from an ec2 instance, use the
        # region of the instance
        elif is_ec2():
            info = InstanceInfo()
            return info.region()
        # Otherwise default to Ireland
        else:
            return 'eu-west-1'

def get_userdata(outfile):
    response = get_retry(USER_DATA_URL)
    if outfile == "-":
        print(response.text)
    else:
        with open(outfile, 'w') as outf:
            outf.write(response.text)

def is_ec2():
    if sys.platform.startswith("win"):
        import wmi
        systeminfo = wmi.WMI().Win32_ComputerSystem()[0]
        return "EC2" == systeminfo.PrimaryOwnerName
    elif sys.platform.startswith("linux"):
        if read_if_readable("/sys/hypervisor/uuid").startswith("ec2"):
            return True
        elif read_if_readable("/sys/class/dmi/id/product_uuid").startswith("EC2"):
            return True
        elif read_if_readable("/sys/devices/virtual/dmi/id/board_vendor").startswith("Amazon EC2"):
            return True
        elif read_if_readable("/sys/devices/virtual/dmi/id/sys_vendor").startswith("Amazon EC2"):
            return True
        elif read_if_readable("/sys/devices/virtual/dmi/id/sys_vendor").startswith("Amazon EC2"):
            return True
        elif read_if_readable("/sys/devices/virtual/dmi/id/bios_vendor").startswith("Amazon EC2"):
            return True
        elif read_if_readable("/sys/devices/virtual/dmi/id/chassis_vendor").startswith("Amazon EC2"):
            return True
        elif read_if_readable("/sys/devices/virtual/dmi/id/chassis_asset_tag").startswith("Amazon EC2"):
            return True
        elif "AmazonEC2" in read_if_readable("/sys/devices/virtual/dmi/id/modalias"):
            return True 
        elif "AmazonEC2" in read_if_readable("/sys/devices/virtual/dmi/id/uevent"):
            return True
        else:
            return False

class InstanceInfo(object):
    """ A class to get the relevant metadata for an instance running in EC2
        firstly from the metadata service and then from EC2 tags and then
        from the CloudFormation template that created this instance

        The info is then cached in $TMP/instance-data.json
    """
    _info = {}

    def stack_name(self):
        if 'stack_name' in self._info:
            return self._info['stack_name']
        else:
            return None

    def stack_id(self):
        if 'stack_id' in self._info:
            return self._info['stack_id']
        else:
            return None

    def instance_id(self):
        if 'instanceId' in self._info:
            return self._info['instanceId']
        else:
            return None

    def region(self):
        if 'region' in self._info:
            return self._info['region']
        else:
            return None

    def initial_status(self):
        if 'initial_status' in self._info:
            return self._info['initial_status']
        else:
            return None

    def logical_id(self):
        if 'logical_id' in self._info:
            return self._info['logical_id']
        else:
            return None

    def availability_zone(self):
        if 'availabilityZone' in self._info:
            return self._info['availabilityZone']
        else:
            return None

    def private_ip(self):
        if 'privateIp' in self._info:
            return self._info['privateIp']
        else:
            return None

    def tag(self, name):
        if 'Tags' in self._info and name in self._info['Tags']:
            return self._info['Tags'][name]
        else:
            return None

    def clear_cache(self):
        if os.path.isfile(INSTANCE_DATA):
            os.remove(INSTANCE_DATA)
        self._info = None
        self.__init__(self)

    def __init__(self):
        if os.path.isfile(INSTANCE_DATA) and \
           time.time() - os.path.getmtime(INSTANCE_DATA) < 900:
            try:
                self._info = json.load(open(INSTANCE_DATA))
            except BaseException:
                pass
        if not self._info and is_ec2():
            try:
                if not wait_net_service("169.254.169.254", 80, 120):
                    raise Exception("Failed to connect to instance identity service")
                response = get_retry(INSTANCE_IDENTITY_URL)
                self._info = json.loads(response.text)
                os.environ['AWS_DEFAULT_REGION'] = self.region()
                tags = {}
                tag_response = None
                retry = 0
                while not tag_response and retry < 20:
                    try:
                        tag_response = ec2().describe_tags(Filters=[{'Name': 'resource-id',
                                                                      'Values': [self.instance_id()]}])
                    except (ConnectionError, EndpointConnectionError):
                        retry = retry + 1
                        time.sleep(1)
                        continue
                    except ClientError:
                        tag_response = { 'Tags': [] }
                for tag in tag_response['Tags']:
                    tags[tag['Key']] = tag['Value']
                self._info['Tags'] = tags
                if 'aws:cloudformation:stack-name' in self._info['Tags']:
                    self._info['stack_name'] = tags['aws:cloudformation:stack-name']
                if 'aws:cloudformation:stack-id' in self._info['Tags']:
                    self._info['stack_id'] = tags['aws:cloudformation:stack-id']
                if self.stack_name():
                    stack_parameters, stack = stack_params_and_outputs_and_stack(region(), self.stack_name())
                    self._info['StackData'] = stack_parameters
                    self._info['FullStackData'] = stack
            except ConnectionError:
                self._info = {}
            info_file = None
            info_file_dir = tempfile.gettempdir()
            info_file_parent = os.path.dirname(info_file_dir)
            if not os.path.isdir(info_file_dir) and os.access(info_file_parent, os.W_OK):
                os.makedirs(info_file_dir)
            if not os.access(info_file_dir, os.W_OK):
                home = expanduser("~")
                info_file_dir = home + os.sep + ".ndt"
            if not os.path.isdir(info_file_dir) and os.access(info_file_parent, os.W_OK):
                os.makedirs(info_file_dir)
            if os.access(info_file_dir, os.W_OK):
                info_file = info_file_dir + os.sep + 'instance-data.json'
                with open(info_file, 'w') as outf:
                    outf.write(json.dumps(self._info, skipkeys=True, indent=2, default=dthandler))
                try:
                    os.chmod(info_file, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP |
                             stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)
                    os.chmod(info_file_dir, stat.S_IRUSR | stat.S_IWUSR |
                             stat.S_IXUSR | stat.S_IRGRP | stat.S_IWGRP |
                             stat.S_IXGRP | stat.S_IROTH | stat.S_IWOTH |
                             stat.S_IXOTH)
                except BaseException:
                    pass
        if self.region():
            os.environ['AWS_DEFAULT_REGION'] = self.region()
        if 'FullStackData' in self._info and 'StackStatus' in self._info['FullStackData']:
            self._info['initial_status'] = self._info['FullStackData']['StackStatus']
        if 'Tags' in self._info:
            tags = self._info['Tags']
            if 'aws:cloudformation:stack-name' in tags:
                self._info['stack_name'] = tags['aws:cloudformation:stack-name']
            if 'aws:cloudformation:stack-id' in tags:
                self._info['stack_id'] = tags['aws:cloudformation:stack-id']
            if 'aws:cloudformation:logical-id' in tags:
                self._info['logical_id'] = tags['aws:cloudformation:logical-id']

    def stack_data_dict(self):
        if 'StackData' in self._info:
            return self._info['StackData']

    def stack_data(self, name):
        if 'StackData' in self._info:
            if name in self._info['StackData']:
                return self._info['StackData'][name]
        return ''

    def __str__(self):
        return json.dumps(self._info, skipkeys=True)

def stack_params_and_outputs_and_stack(regn, stack_name):
    """ Get parameters and outputs from a stack as a single dict and the full stack
    """
    cloudformation = boto3.client("cloudformation", region_name=regn)
    retry = 0
    stack = {}
    resources = {}
    while not stack and retry < 10:
        try:
            stack = cloudformation.describe_stacks(StackName=stack_name)
            stack = stack['Stacks'][0]
        except (ConnectionError, EndpointConnectionError):
            retry = retry + 1
            time.sleep(1)
            continue
        except ClientError:
            break
    if not stack:
        return {}, {}
    retry = 0
    while not resources and retry < 3:
        try:
            resources = cloudformation.describe_stack_resources(StackName=stack_name)
        except ClientError:
            break
        except (ConnectionError, EndpointConnectionError):
            retry = retry + 1
            time.sleep(1)
            continue
    resp = {}
    if 'CreationTime' in stack:
        stack['CreationTime'] = time.strftime("%a, %d %b %Y %H:%M:%S +0000",
                                              stack['CreationTime'].timetuple())
    if 'LastUpdatedTime' in stack:
        stack['LastUpdatedTime'] = time.strftime("%a, %d %b %Y %H:%M:%S +0000",
                                                 stack['LastUpdatedTime'].timetuple())
    if "StackResources" in resources:
        for resource in resources["StackResources"]:
            resp[resource['LogicalResourceId']] = resource['PhysicalResourceId']
    if 'Parameters' in stack:
        for param in stack['Parameters']:
            resp[param['ParameterKey']] = param['ParameterValue']
    if 'Outputs' in stack:
        for output in stack['Outputs']:
            resp[output['OutputKey']] = output['OutputValue']
    return resp, stack
