import re
import requests
from lib.Cb_constants.CBServer import CbServer
import logger

class metering(object):
    def __init__(self, server, username, password):
        self.auth = requests.auth.HTTPBasicAuth(username, password)
        url = f"https://{server}:{CbServer.ssl_port}/pools/default"
        response = requests.get(url, auth=self.auth, verify=False)
        self.nodes = response.json()['nodes']
        self.log = logger.Logger.get_logger()

    def meter_pattern(self, unit, bucket, service, unbilled='', variant=''):
        meter_service = ''
        meter_unbilled = ''
        meter_variant = ''
        if unbilled != '':
            meter_unbilled = f',unbilled="{unbilled}"'
        if variant != '':
            meter_variant = f',variant="{variant}"'
        if service != '':
            meter_service = f',for="{service}"'

        return f'meter_{unit}_total{{bucket="{bucket}"{meter_service}{meter_unbilled}{meter_variant}}} (\d+)'

    def get_query_cu(self, bucket='default', unbilled='true', variant='eval'):
        cu = 0
        qry_cu_pattern = re.compile(self.meter_pattern('cu', bucket, 'n1ql', unbilled, variant))
        for node in self.nodes:
            if 'n1ql' in node['services']:
                url = f"https://{node['hostname'][:-5]}:{CbServer.ssl_port}/metrics"
                response = requests.get(url, auth=self.auth, verify=False)
                if qry_cu_pattern.search(response.text):
                    cu += int(qry_cu_pattern.findall(response.text)[0])
        self.log.info(f'N1QL UNITS for {bucket}: {cu} CU')
        return cu

    def get_index_rwu(self, bucket='default', unbilled = '', variant = ''):
        ru, wu = 0, 0
        idx_ru_pattern = re.compile(self.meter_pattern('ru', bucket, 'index', unbilled, variant))
        idx_wu_pattern = re.compile(self.meter_pattern('wu', bucket, 'index', unbilled, variant))
        for node in self.nodes:
            if 'index' in node['services']:
                url = f"https://{node['hostname'][:-5]}:{CbServer.ssl_port}/metrics"
                response = requests.get(url, auth=self.auth, verify=False)
                if idx_ru_pattern.search(response.text):
                    ru += int(idx_ru_pattern.findall(response.text)[0])
                if idx_wu_pattern.search(response.text):
                    wu += int(idx_wu_pattern.findall(response.text)[0])
        self.log.info(f'INDEX UNITS for {bucket}: {ru} RU, {wu} WU')
        return ru, wu

    def get_fts_rwu(self, bucket='default', unbilled = '', variant = ''):
        ru, wu = 0, 0
        fts_ru_pattern = re.compile(self.meter_pattern('ru', bucket, 'fts', unbilled, variant))
        fts_wu_pattern = re.compile(self.meter_pattern('wu', bucket, 'fts', unbilled, variant))
        for node in self.nodes:
            if 'fts' in node['services']:
                url = f"https://{node['hostname'][:-5]}:{CbServer.ssl_port}/metrics"
                response = requests.get(url, auth=self.auth, verify=False)
                if fts_ru_pattern.search(response.text):
                    ru += int(fts_ru_pattern.findall(response.text)[0])
                if fts_wu_pattern.search(response.text):
                    wu += int(fts_wu_pattern.findall(response.text)[0])
        self.log.info(f'FTS UNITS for {bucket}: {ru} RU, {wu} WU')
        return ru, wu

    def get_kv_rwu(self, bucket='default', unbilled ='', variant =''):
        ru, wu = 0, 0
        kv_ru_pattern = re.compile(self.meter_pattern('ru', bucket, '', unbilled, variant))
        kv_wu_pattern = re.compile(self.meter_pattern('wu', bucket, '', unbilled, variant))
        for node in self.nodes:
            if 'kv' in node['services']:
                url = f"https://{node['hostname'][:-5]}:{CbServer.ssl_port}/metrics"
                response = requests.get(url, auth=self.auth, verify=False)
                if kv_ru_pattern.search(response.text):
                    ru += int(kv_ru_pattern.findall(response.text)[0])
                if kv_wu_pattern.search(response.text):
                    wu += int(kv_wu_pattern.findall(response.text)[0])
        self.log.info(f'KV UNITS for {bucket}: {ru} RU, {wu} WU')
        return ru, wu

    def assert_query_billing_unit(self, result, expected, unit="ru", service="kv"):
        if 'billingUnits' in result.keys():
            if unit in result['billingUnits'].keys():
                if service in result['billingUnits'][unit].keys():
                    actual = result['billingUnits'][unit][service]
                    if (actual == expected):
                        return True, ''
                    else:
                        return False, f'Expected {expected} {service} {unit} unit but got {actual}'
                else:
                    return False, f"result['billingUnits'][{unit}] does not contain {service}, result['billingUnits'][{unit}] is: {result['billingUnits'][unit]}"
            else:
                return False, f"result['billingUnits'] does not contain {unit}, result['billingUnits'] is: {result['billingUnits']}"
        else:
            return False, f'result does not contain billingUnits, result is: {result}'

# Throttling limit name for each service are:
# - dataThrottleLimit
# - indexThrottleLimit
# - searchThrottleLimit
# - queryThrottleLimit
# - sgwReadThrottleLimit
# - sgwWriteThrottleLimit
# - dataStorageLimit
# - indexStorageLimit
# - searchStorageLimit
class throttling(object):
    def __init__(self, server, username, password):
        self.auth = requests.auth.HTTPBasicAuth(username, password)
        self.url_bucket_throttle = f"https://{server}:{CbServer.ssl_port}/pools/default/buckets"
        self.url_cluster_throttle = f"https://{server}:{CbServer.ssl_port}/internalSettings"
        url = f"https://{server}:{CbServer.ssl_port}/pools/default"
        response = requests.get(url, auth=self.auth, verify=False)
        self.nodes = response.json()['nodes']
        self.log = logger.Logger.get_logger()

    def get_bucket_limit(self, bucket = 'default', service='dataThrottleLimit'):
        response = requests.get(self.url_bucket_throttle + f"/{bucket}", auth = self.auth, verify=False)
        if response.status_code not in (200,201):
            self.fail(f'Fail to get bucket throttle limit: {response.text}')
        throttle_limits = response.json()
        self.log.info(f'RETRIEVED {service} for {bucket}: {throttle_limits[service]}')
        return throttle_limits[service]

    def set_bucket_limit(self, bucket= 'default', value=5000, service='dataThrottleLimit'):
        data = {}
        data[service] = value
        self.log.info(f'SETTING {service} for {bucket} to {value}')
        response = requests.post(self.url_bucket_throttle + f"/{bucket}", data=data, auth = self.auth, verify=False)
        if response.status_code not in (200,201):
            self.fail(f'Fail to set bucket throttle limit: {response.text}')

    def get_cluster_limit(self, service='dataThrottleLimit'):
        response = requests.get(self.url_cluster_throttle, auth = self.auth, verify=False)
        if response.status_code not in (200,201):
            self.fail(f'Fail to get cluster throttle limit: {response.text}')
        throttle_limits = response.json()
        self.log.info(f'RETRIEVED {service} for CLUSTER: {throttle_limits[service]}')
        return throttle_limits[service]

    def set_cluster_limit(self, value=5000, service='dataThrottleLimit'):
        data = {}
        data[service] = value
        response = requests.post(self.url_cluster_throttle, data=data, auth = self.auth, verify=False)
        if response.status_code not in (200,201):
            self.fail(f'Fail to set cluster throttle limit: {response.text}')

    def get_metrics(self, bucket='default', service='kv'):
        throttle_count_total, throttle_seconds_total = 0, 0
        throttle_seconds_pattern = re.compile(f'throttle_seconds_total{{bucket="{bucket}",for="{service}".*}} (\d+)')
        throttle_count_pattern = re.compile(f'throttle_count_total{{bucket="{bucket}",for="{service}".*}} (\d+)')
        for node in self.nodes:
            if service in node['services']:
                url = f"https://{node['hostname'][:-5]}:{CbServer.ssl_port}/metrics"
                response = requests.get(url, auth = self.auth, verify=False)
                if response.status_code not in (200,201):
                    self.fail(f'Fail to get throttle metrics: {response.text}')
                if throttle_seconds_pattern.search(response.text):
                    throttle_seconds_total += int(throttle_seconds_pattern.findall(response.text)[0])
                if throttle_count_pattern.search(response.text):
                    throttle_count_total += int(throttle_count_pattern.findall(response.text)[0])
        self.log.info(f'{service.upper()} THROTTLE for {bucket}: {throttle_count_total} count, {throttle_seconds_total} seconds')
        return throttle_count_total, throttle_seconds_total