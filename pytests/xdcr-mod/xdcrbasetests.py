import sys
import time
import unittest
import logger
import copy

from membase.api.rest_client import RestConnection
from couchbase.cluster import Cluster
from TestInput import TestInputSingleton
from memcached.helper.kvstore import KVStore
from membase.helper.bucket_helper import BucketOperationHelper
from membase.helper.cluster_helper import ClusterOperationHelper
from memcached.helper.data_helper import VBucketAwareMemcached
from mc_bin_client import MemcachedError

from couchbase.documentgenerator import BlobGenerator, DocumentGenerator
from basetestcase import BaseTestCase

#===============================================================================
# class: XDCRConstants
# Constants used in XDCR application testing. It includes input parameters as well
# as internal constants used in the code.
# All string literals used in the XDCR code shall be defined in this class.
#===============================================================================

class XDCRConstants:
    INPUT_PARAM_REPLICATION_DIRECTION = "rdirection"
    INPUT_PARAM_CLUSTER_TOPOLOGY = "ctopology"
    INPUT_PARAM_SEED_DATA = "sdata"
    INPUT_PARAM_SEED_DATA_MODE = "sdata_mode"

    INPUT_PARAM_SEED_DATA_OPERATION = "sdata_op"


    INPUT_PARAM_POLL_INTERVAL = "poll_interval" # in seconds
    INPUT_PARAM_POLL_TIMEOUT = "poll_timeout"# in seconds

    #CLUSTER_TOPOLOGY_TYPE_LINE = "line"
    CLUSTER_TOPOLOGY_TYPE_CHAIN = "chain"
    CLUSTER_TOPOLOGY_TYPE_STAR = "star"

    REPLICATION_TYPE_CONTINUOUS = "continuous"
    REPLICATION_DIRECTION_UNIDIRECTION = "unidirection"
    REPLICATION_DIRECTION_BIDIRECTION = "bidirection"

    SEED_DATA_OP_CREATE = "create"
    SEED_DATA_OP_UPDATE = "update"
    SEED_DATA_OP_DELETE = "delete"

    SEED_DATA_MODE_SYNC = "sync"
    SEED_DATA_MODE_ASYNC = "async"


#===============================================================================
# class: XDCRBaseTest
# This class is the base class (super class) for all the test classes written
# for XDCR. It configures the cluster as defined in the <cluster-file>.ini
# passed as an command line argument "-i" while running the test using testrunner.
# The child classes can override the following methods if required.
# - init_parameters_extended
# - setup_extendedself._input.param(XDCRConstants.INPUT_PARAM_REPLICATION_DIRECTION,
# - teardown_extended
# The reason for providing extended functions is so that inheriting classes can take advantage of
# clean_broken _setup in case an exception comes during test setUp.
# Note:B
# It assumes that the each node is physically up and running.
# In ini file , the cluster name should start with "cluster" (prefix).
#===============================================================================

class XDCRBaseTest(unittest.TestCase):
    def setUp(self):
        try:
            self._log = logger.Logger.get_logger()
            self._log.info("SetUp process started ...")
            self._input = TestInputSingleton.input
            self._cluster_helper = Cluster()

            self._init_parameters()

            if not self._input.param("skip_cleanup", False):
                self._cleanup_previous_setup()

            self._init_clusters()
            self.setup_extended()
            self._log.info("SetUp process completed...")
        except:
            self._log.error("Error while setting up clusters: %s", sys.exc_info()[0])
            self._cleanup_broken_setup()
            raise

    def tearDown(self):
        self.teardown_extended()
        self._do_cleanup()
        self._cluster_helper.shutdown()

    def _cleanup_previous_setup(self):
        self.teardown_extended()
        self._do_cleanup()

        # def test_setUp(self):
    #    pass


    def _init_parameters(self):
        self._log.info("Initializing input parameters started...")
        self._clusters_dic = self._input.clusters # clusters is declared as dic in TestInput which is unordered.
        self._clusters_keys_olst = range(len(self._clusters_dic)) #clusters are populated in the dic in testrunner such that ordinal is the key.
        #orderedDic cannot be used in order to maintain the compability with python 2.6
        self._cluster_counter_temp_int = 0
        self._cluster_names_dic = self._get_cluster_names()
        self._servers = self._input.servers
        self._floating_servers_set = self._get_floating_servers() # These are the servers defined in .ini file but not linked to any cluster.
        self._cluster_counter_temp_int = 0 #TODO: fix the testrunner code to pass cluster name in params.
        self._buckets = {}
        self._default_bucket = self._input.param("default_bucket", True)
        if self._default_bucket:
            self.default_bucket_name = "default"
        self._num_replicas = self._input.param("replicas", 1)
        self._num_items = self._input.param("items", 1000)
        self._value_size = self._input.param("value_size", 128)
        self._dgm_run_bool = self._input.param("dgm_run", False)
        self._mem_quota_int = 0 # will be set in subsequent methods

        self._poll_interval = self._input.param(XDCRConstants.INPUT_PARAM_POLL_INTERVAL, 5)
        self._poll_timeout = self._input.param(XDCRConstants.INPUT_PARAM_POLL_TIMEOUT, 120)

        self.init_parameters_extended()

        self._doc_ops = self._input.param("doc-ops", None)
        if self._doc_ops is not None:
            self._doc_ops = self._doc_ops.split("-")
        self._doc_ops_dest = self._input.param("doc-ops-dest", None)
        # semi-colon separator is not accepted for some reason here
        if self._doc_ops_dest is not None:
            self._doc_ops_dest = self._doc_ops_dest.split("-")

        self._expires = self._input.param("expires", 0)
        self._timeout = self._input.param("timeout", 60)
        self._percent_update = self._input.param("upd", 50)
        self._percent_delete = self._input.param("del", 50)
        self._warmup = self._input.param("warm", "all")
        self._failover = self._input.param("failover", None)
        if self._failover is not None:
            self._failover = self._failover.split("-")
        self._log.info("Initializing input parameters completed.")


    def _get_floating_servers(self):
        cluster_nodes = []
        for key, nodes in self._clusters_dic.items():
            cluster_nodes.extend(nodes)
            #return set(self._servers[:]).difference(cluster_nodes)
        temp_list_cluster = []
        for i in cluster_nodes:
            temp_list_cluster.append(i.ip)
        floating_servers = []
        for i in self._servers:
            if not i.ip in temp_list_cluster:
                floating_servers.append(i)
        return floating_servers


    def _init_clusters(self):
        for key in self._clusters_keys_olst:
            self._setup_cluster(self._clusters_dic[key])

    # This method shall be overridden in case there are parameters that need to be initialized.
    def init_parameters_extended(self):
        pass

    # This method shall be overridden in case there are custom steps involved during setup.
    def setup_extended(self):
        pass

    # This method shall be overridden in case there are custom steps involved during teardown.
    def teardown_extended(self):
        pass

    def _do_cleanup(self):
        for key in self._clusters_keys_olst:
            nodes = self._clusters_dic[key]
            BucketOperationHelper.delete_all_buckets_or_assert(nodes, self)
            ClusterOperationHelper.cleanup_cluster(nodes)
            ClusterOperationHelper.wait_for_ns_servers_or_assert(nodes, self)

    def _cleanup_broken_setup(self):
        try:
            self.tearDown()
        except:
            self._log.info("Error while cleaning broken setup.")

    def _get_cluster_names(self):
        cs_names = {}
        for key in self._clusters_keys_olst:
            cs_names[key] = "cluster{0}".format(self._cluster_counter_temp_int)
            self._cluster_counter_temp_int += 1
        return cs_names

    def _setup_cluster(self, nodes):
        self._init_nodes(nodes)
        self._create_buckets(nodes)
        self._config_cluster(nodes)

    def _init_nodes(self, nodes):
        _tasks = []
        for node in nodes:
            _tasks.append(self._cluster_helper.async_init_node(node))
        for task in _tasks:
            mem_quota_node = task.result()
            if mem_quota_node < self._mem_quota_int or self._mem_quota_int == 0:
                self._mem_quota_int = mem_quota_node

    def _create_buckets(self, nodes):
        if self._dgm_run_bool:
            self._mem_quota_int = 256
        master_node = nodes[0]
        bucket_size = self._get_bucket_size(master_node, nodes, self._mem_quota_int, self._default_bucket)

        if self._default_bucket:
            self._cluster_helper.create_default_bucket(master_node, bucket_size, self._num_replicas)
            self._buckets[self.default_bucket_name] = {1: KVStore()}

    def _config_cluster(self, nodes):
        task = self._cluster_helper.async_rebalance(nodes, nodes[1:], [])
        task.result()

    def _get_bucket_size(self, master_node, nodes, mem_quota, num_buckets, ratio=2.0 / 3.0):
        for node in nodes:
            if node.ip == master_node.ip:
                return int(ratio / float(len(nodes)) / float(num_buckets) * float(mem_quota))
        return int(ratio / float(num_buckets) * float(mem_quota))


    def _poll_for_condition(self, condition):
        timeout = self._poll_timeout
        interval = self._poll_interval
        num_itr = timeout / interval
        return self._poll_for_condition_rec(condition, interval, num_itr)

    def _poll_for_condition_rec(self, condition, sleep, num_itr):
        if num_itr == 0:
            return False
        else:
            if condition():
                return True
            else:
                time.sleep(sleep)
                return self._poll_for_condition_rec(condition, sleep, (num_itr - 1))



#===============================================================================
# class: XDCRReplicationBaseTest
# This class links the different clusters defined in ".ini" file and starts the
# replication. It supports different topologies for cluster which can be defined
# by input parameter "ctopology". The various values supported are as follows
# - chain
# - star (Not Implemented yet)
# - tree (Not Implemented yet)
# The direction of replication can be defined using parameter "rdirection".
# It supports following values
# - unidirection
# - bidirection
# Note:
# The first node is consideredn as master node in the respective cluster section
# of .ini file.
# Cluster/Node ordinals are determined by the sequence of entry of node in .ini file.
#===============================================================================

class XDCRReplicationBaseTest(XDCRBaseTest):


    def setup_extended(self):
        self._setup_topology()
        self._load_data()


    def teardown_extended(self):
        for (rest_conn, cluster_ref, rep_database, rep_id) in self._cluster_state_arr:
            rest_conn.stop_replication(rep_database, rep_id)
            rest_conn.remove_remote_cluster(cluster_ref)


    def init_parameters_extended(self):
        self._cluster_state_arr = []
        self._cluster_topology_str = self._input.param(XDCRConstants.INPUT_PARAM_CLUSTER_TOPOLOGY,
            XDCRConstants.CLUSTER_TOPOLOGY_TYPE_CHAIN)
        self._replication_direction_str = self._input.param(XDCRConstants.INPUT_PARAM_REPLICATION_DIRECTION,
            XDCRConstants.REPLICATION_DIRECTION_BIDIRECTION)
        self._seed_data = self._input.param(XDCRConstants.INPUT_PARAM_SEED_DATA, False)

        self._seed_data_ops_lst = self._input.param(XDCRConstants.INPUT_PARAM_SEED_DATA_OPERATION,
            XDCRConstants.SEED_DATA_OP_CREATE).split('|')
        self._seed_data_mode_str = self._input.param(XDCRConstants.INPUT_PARAM_SEED_DATA_MODE,
            XDCRConstants.SEED_DATA_MODE_SYNC)


    def _setup_topology(self):
        if self._cluster_topology_str == XDCRConstants.CLUSTER_TOPOLOGY_TYPE_CHAIN:
            self._setup_topology_chain()
        elif self._cluster_topology_str == XDCRConstants.CLUSTER_TOPOLOGY_TYPE_STAR:
            self._set_toplogy_star()
        else:
            raise "Not supported cluster topology : %s", self._cluster_topolog_str


    def _load_data(self):
        if not self._seed_data:
            return
        if self._cluster_topology_str == XDCRConstants.CLUSTER_TOPOLOGY_TYPE_CHAIN:
            self._load_data_chain()
        elif self._cluster_topology_str == XDCRConstants.CLUSTER_TOPOLOGY_TYPE_STAR:
            self._load_data_star()
        else:
            raise "Seed data not supported cluster topology : %s", self._cluster_topology_str


    def _setup_topology_chain(self):
        ord_keys = self._clusters_keys_olst
        ord_keys_len = len(ord_keys)
        dest_key_index = 1
        for src_key in ord_keys:
            if dest_key_index == ord_keys_len:
                break
            dest_key = ord_keys[dest_key_index]
            dest_nodes = self._clusters_dic[dest_key]
            src_nodes = self._clusters_dic[src_key]
            src_master = src_nodes[0]
            dest_master = dest_nodes[0]
            src_cluster_name = self._cluster_names_dic[src_key]
            dest_cluster_name = self._cluster_names_dic[dest_key]
            self._join_clusters(src_cluster_name, src_master, dest_cluster_name, dest_master)
            dest_key_index += 1


    def _set_toplogy_star(self):
        src_master_identified = False
        for key in self._clusters_keys_olst:
            nodes = self._clusters_dic[key]
            if not src_master_identified:
                src_master = nodes[0]
                src_cluster_name = self._cluster_names_dic[key]
                print src_cluster_name
                src_master_identified = True
                continue
            dest_cluster_name = self._cluster_names_dic[key]
            dest_master = nodes[0]
            self._join_clusters(src_cluster_name, src_master, dest_cluster_name, dest_master)
            time.sleep(30)


    def _load_data_chain(self):
        for key in self._clusters_keys_olst:
            cluster_node = self._clusters_dic[key][0]
            cluster_name = self._cluster_names_dic[key]
            self._log.info("Starting Load # items {0} node {1} , cluster {2}....".format(self._num_items, cluster_node, cluster_name))
            self._load_gen_data(cluster_name, cluster_node)
            if self._replication_direction_str == XDCRConstants.REPLICATION_DIRECTION_UNIDIRECTION :
                break
            self._log.info("Completed Load")


    def _join_clusters(self, src_cluster_name, src_master, dest_cluster_name, dest_master):
        self._link_clusters(src_cluster_name, src_master, dest_cluster_name, dest_master)
        self._replicate_clusters(src_master, dest_cluster_name)
        if self._replication_direction_str == XDCRConstants.REPLICATION_DIRECTION_BIDIRECTION:
            self._link_clusters(dest_cluster_name, dest_master, src_cluster_name, src_master)
            self._replicate_clusters(dest_master, src_cluster_name)



    def _link_clusters(self, src_cluster_name, src_master, dest_cluster_name, dest_master):
        rest_conn_src = RestConnection(src_master)
        rest_conn_src.add_remote_cluster(dest_master.ip, dest_master.port,
            dest_master.rest_username,
            dest_master.rest_password, dest_cluster_name)


    def _replicate_clusters(self, src_master, dest_cluster_name):
        rest_conn_src = RestConnection(src_master)
        (rep_database, rep_id) = rest_conn_src.start_replication(XDCRConstants.REPLICATION_TYPE_CONTINUOUS,
            "default",
            dest_cluster_name)
        self._cluster_state_arr.append((rest_conn_src, dest_cluster_name, rep_database, rep_id))


    def _load_gen_data(self, cname, node):
        for op_type in self._seed_data_ops_lst:
            num_items_ratio = self._get_num_items_ratio(op_type)
            load_gen = BlobGenerator(cname, cname, self._value_size, end=num_items_ratio)
            self._log.info("Starting Load operation '{0}' for items (ratio) '{1}' on node '{2}'....".format(op_type, num_items_ratio, cname))
            if self._seed_data_mode_str == XDCRConstants.SEED_DATA_MODE_SYNC:
                self._load_all_buckets(node, load_gen, op_type, 0)
                self._log.info("Completed Load of {0}".format(op_type))
            else:
                self._async_load_all_buckets(node, load_gen, op_type, 0)
                self._log.info("Started async Load of {0}".format(op_type))

    def _get_num_items_ratio(self, op_type):
        if len(self._seed_data_ops_lst) <= 1:
            return self._num_items
        if op_type == XDCRConstants.SEED_DATA_OP_UPDATE:
            return self._num_items / 2
        elif op_type == XDCRConstants.SEED_DATA_OP_DELETE:
            return self._num_items / 3
        else:
            return self._num_items

    def _async_load_all_buckets(self, server, kv_gen, op_type, exp, kv_store=1):
        tasks = []
        for bucket, kv_stores in self._buckets.items():
            gen = copy.deepcopy(kv_gen)
            tasks.append(self._cluster_helper.async_load_gen_docs(server, bucket, gen,
                kv_stores[kv_store],
                op_type, exp))
        return tasks


    def _load_all_buckets(self, server, kv_gen, op_type, exp, kv_store=1):
        tasks = self._async_load_all_buckets(server, kv_gen, op_type, exp, kv_store)
        for task in tasks:
            task.result()

    def _verify_revIds(self, src_server, dest_server, ops_perf, kv_store=1):
        tasks = []
        for bucket, kv_stores in self._buckets.items():
            tasks.append(self._cluster_helper.async_verify_revid(src_server, dest_server, bucket, kv_stores[kv_store], ops_perf))
        for task in tasks:
            task.result()

    def _expiry_pager(self, master):
        for bucket in self._buckets:
            ClusterOperationHelper.flushctl_set(master, "exp_pager_stime", 30, bucket)
            self._log.info("wait for expiry pager to run on all these nodes")
            time.sleep(30)

    def _wait_for_stats_all_buckets(self, servers):
        def verify():
            try:
                tasks = []
                for server in servers:
                    for bucket in self._buckets:
                        tasks.append(self._cluster_helper.async_wait_for_stats([server], bucket, '',
                            'ep_queue_size', '==', 0))
                        tasks.append(self._cluster_helper.async_wait_for_stats([server], bucket, '',
                            'ep_flusher_todo', '==', 0))
                for task in tasks:
                    task.result()
                return True
            except MemcachedError as e:
                self._log.info("verifying ...")
                self._log.debug("Not able to fetch data. Error is %s" , (e.message))
                return False
        is_verified = self._poll_for_condition(verify)
        if not is_verified:
            raise ValueError("Verification process not completed after waiting for {0} seconds.".format(self._poll_timeout))

    def _verify_all_buckets(self, server, kv_store=1):
        def verify():
            try:
                tasks = []
                for bucket, kv_stores in self._buckets.items():
                    tasks.append(self._cluster_helper.async_verify_data(server, bucket, kv_stores[kv_store]))
                for task in tasks:
                    task.result()
                return True
            except  MemcachedError as e:
                self._log.info("verifying ...")
                self._log.info("Not able to fetch data. Error is %s" , (e.message))
                return False
        is_verified = self._poll_for_condition(verify)
        if not is_verified:
            raise ValueError("Verification process not completed after waiting for {0} seconds. Please check logs".format(self._poll_timeout))


    def _verify_stats_all_buckets(self, servers):
        def verify():
            try:
                stats_tasks = []
                for bucket, kv_stores in self._buckets.items():
                    items = sum([len(kv_store) for kv_store in kv_stores.values()])
                    stats_tasks.append(self._cluster_helper.async_wait_for_stats(servers, bucket, '',
                        'curr_items', '==', items))
                    stats_tasks.append(self._cluster_helper.async_wait_for_stats(servers, bucket, '',
                        'vb_active_curr_items', '==', items))

                    available_replicas = self._num_replicas
                    if len(servers) == self._num_replicas:
                        available_replicas = len(servers) - 1
                    elif len(servers) <= self._num_replicas:
                        available_replicas = len(servers) - 1

                    stats_tasks.append(self._cluster_helper.async_wait_for_stats(servers, bucket, '',
                        'vb_replica_curr_items', '==', items * available_replicas))
                    stats_tasks.append(self._cluster_helper.async_wait_for_stats(servers, bucket, '',
                        'curr_items_tot', '==', items * (available_replicas + 1)))

                for task in stats_tasks:
                    task.result(120)
                return True
            except  MemcachedError as e:
                self._log.info("verifying ...")
                self._log.debug("Not able to fetch data. Error is %s" , (e.message))
                return False
        is_verified = self._poll_for_condition(verify)
        if not is_verified:
            raise ValueError("Verification process not completed after waiting for {0} seconds.".format(self._poll_timeout))

    def _find_cluster_nodes_by_name(self, cluster_name):
        return self._clusters_dic[[k for k, v in self._cluster_names_dic.iteritems() if v == cluster_name][0]]

    def _find_key_from_cluster_name(self, cluster_name):
        for k, v in self._cluster_names_dic.iteritems():
            if v == cluster_name:
                return k
        return -1
