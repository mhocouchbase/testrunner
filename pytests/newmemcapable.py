import copy
from basetestcase import BaseTestCase
from couchbase.documentgenerator import DocumentGenerator
from membase.helper.cluster_helper import ClusterOperationHelper
from remote.remote_util import RemoteMachineShellConnection
from membase.api.rest_client import RestConnection
from memcached.helper.data_helper import VBucketAwareMemcached

class GetrTests(BaseTestCase):

    DURING_REBALANCE = 1
    AFTER_REBALANCE = 2
    SWAP_REBALANCE = 3

    FAILOVER_NO_REBALANCE = 1
    FAILOVER_ADD_BACK = 2
    FAILOVER_REBALANCE = 3

    def setUp(self):
        super(GetrTests, self).setUp()
        descr = self.input.param("descr", "")
        if descr:
            self.log.info("Test:{0}".format(descr))
        self.skipload = self.input.param("skipload", False)
        self.data_ops = self.input.param("data_ops", 'create')
        self.expiration = self.input.param("expiration", 0)
        self.wait_expiration = self.input.param("wait_expiration", False)
        self.flags = self.input.param("flags", 0)
        self.warmup_nodes = self.input.param("warmup", 0)
        self.rebalance = self.input.param("rebalance", 0)
        self.failover = self.input.param("failover", 0)
        self.failover_factor = self.input.param("failover-factor", 1)
        self.error = self.input.param("error", None)
        self.replica_to_read = self.input.param("replica_to_read", 0)

    def tearDown(self):
        super(GetrTests, self).tearDown()

    def getr_test(self):
        gen_1 = DocumentGenerator('test_docs', '{{"age": {0}}}', xrange(5),
                                      start=0, end=self.num_items/2)
        gen_2 = DocumentGenerator('test_docs', '{{"age": {0}}}', xrange(5),
                                      start=self.num_items/2, end=self.num_items)
        self.log.info("LOAD PHASE")
        if not self.skipload:
            self.perform_docs_ops(self.master, [gen_1, gen_2], self.data_ops)

        self.log.info("CLUSTER OPS PHASE")
        if self.rebalance == GetrTests.AFTER_REBALANCE:
            self.cluster.rebalance(self.servers[:self.nodes_init],
                                   self.servers[self.nodes_init:], [])
        if self.rebalance == GetrTests.DURING_REBALANCE:
            rebalance = self.cluster.async_rebalance(self.servers[:self.nodes_init],
                            self.servers[self.nodes_init : self.nodes_init + self.nodes_in],
                            [])
        if self.rebalance == GetrTests.SWAP_REBALANCE:
            self.cluster.rebalance(self.servers[:self.nodes_init],
                                   self.servers[self.nodes_init :
                                                self.nodes_init + self.nodes_in],
                                   self.servers[self.nodes_init - self.nodes_in : self.nodes_init])
        if self.warmup_nodes:
            self.perform_warm_up()
        if self.failover:
            self.perform_failover()
        if self.wait_expiration:
            self.sleep(self.expiration)
        try:
            self.log.info("READ REPLICA PHASE")
            servrs = self.servers[:self.nodes_init]
            if self.failover in [GetrTests.FAILOVER_NO_REBALANCE, GetrTests.FAILOVER_REBALANCE]:
                servrs = self.servers[:self.nodes_init - self.failover_factor]
            if self.rebalance == GetrTests.AFTER_REBALANCE:
                servrs = self.servers
            if self.rebalance == GetrTests.SWAP_REBALANCE:
                servrs = self.servers[:self.nodes_init - self.nodes_in]
                servrs.extend(self.servers[self.nodes_init :
                                           self.nodes_init + self.nodes_in])

            self.log.info("Checking replica read")
            if self.failover == GetrTests.FAILOVER_NO_REBALANCE:
                self._verify_all_buckets(self.master, only_store_hash=False,
                                         replica_to_read=self.replica_to_read,
                                         batch_size=1)
            else:
                self.verify_cluster_stats(servrs, only_store_hash=False,
                                          replica_to_read=self.replica_to_read, batch_size=1)
        except Exception, ex:
            if self.error and str(ex).find(self.error) != -1:
                self.log.info("Expected error %s appeared as expected" % self.error)
            else:
                raise ex
        if self.rebalance == GetrTests.DURING_REBALANCE:
            rebalance.result()

    def getr_negative_test(self):
        gen_1 = DocumentGenerator('test_docs', '{{"age": {0}}}', xrange(5),
                                      start=0, end=self.num_items/2)
        gen_2 = DocumentGenerator('test_docs', '{{"age": {0}}}', xrange(5),
                                      start=self.num_items/2, end=self.num_items)
        self.log.info("LOAD PHASE")
        if not self.skipload:
            self.perform_docs_ops(self.master, [gen_1, gen_2], self.data_ops)

        if self.wait_expiration:
            self.sleep(self.expiration)

        self.log.info("READ REPLICA PHASE")
        self.log.info("Checking replica read")
        try:
            self._load_all_buckets(self.master, gen_1, 'read_replica', self.expiration, batch_size=1)
        except Exception, ex:
            if self.error and str(ex).find(self.error) != -1:
                self.log.info("Expected error %s appeared as expected" % self.error)
            else:
                raise ex
        else:
            if self.error:
                self.fail("Expected error %s didn't appear as expected" % self.error)

    def getr_negative_corrupted_keys_test(self):
        key = self.input.param("key", '')
        gen = DocumentGenerator('test_docs', '{{"age": {0}}}', xrange(5),
                                      start=0, end=self.num_items)
        self.perform_docs_ops(self.master, [gen], 'create')
        self.log.info("Checking replica read")
        client = VBucketAwareMemcached(RestConnection(self.master), self.default_bucket_name)
        try:
            o, c, d = client.getr(key)
        except Exception, ex:
            if self.error and str(ex).find(self.error) != -1:
                self.log.info("Expected error %s appeared as expected" % self.error)
            else:
                raise ex
        else:
            if self.error:
                self.fail("Expected error %s didn't appear as expected" % self.error)

    def test_getr_bucket_ops(self):
        bucket_to_delete_same_read = self.input.param("bucket_to_delete_same_read", True)
        gen_1 = DocumentGenerator('test_docs', '{{"age": {0}}}', xrange(5),
                                      start=0, end=self.num_items)
        self.log.info("LOAD PHASE")
        self.perform_docs_ops(self.master, [gen_1], self.data_ops)

        self.log.info("Start bucket ops")
        bucket_read = self.buckets[0]
        bucket_delete = (self.buckets[1], self.buckets[0])[bucket_to_delete_same_read]
        try:
            self.log.info("READ REPLICA PHASE")
            self.log.info("Checking replica read")
            task_verify = self.cluster.async_verify_data(self.master, bucket_read,
                                                         bucket_read.kvs[1],
                                                         only_store_hash=False,
                                                         replica_to_read=self.replica_to_read)
            task_delete_bucket = self.cluster.async_bucket_delete(self.master, bucket_delete.name)
            task_verify.result()
            task_delete_bucket.result()
        except Exception, ex:
            task_delete_bucket.result()
            if self.error and str(ex).find(self.error) != -1:
                self.log.info("Expected error %s appeared as expected" % self.error)
            else:
                raise ex
        else:
            if self.error:
                self.fail("Expected error %s didn't appear as expected" % self.error)

    def getr_rebalance_test(self):
        gen = DocumentGenerator('test_docs', '{{"age": {0}}}', xrange(5),
                                      start=0, end=self.num_items)
        self.perform_docs_ops(self.master, [gen], 'create')
        self.log.info("Checking replica read")
        client = VBucketAwareMemcached(RestConnection(self.master), self.default_bucket_name)
        rebalance = self.cluster.async_rebalance(self.servers[:self.nodes_init],
                            self.servers[self.nodes_init : self.nodes_init + self.nodes_in],
                            [])
        try:
            while gen.has_next():
                key, _ = gen.next()
                o, c, d = client.getr(key)
        finally:
            rebalance.result()

    def perform_docs_ops(self, server, gens, op_type, kv_store=1, only_store_hash=False,
                         batch_size=1):
        for gen in gens:
            gen_ops = copy.deepcopy(gen)
            self._load_all_buckets(server, gen_ops, 'create', self.expiration, kv_store=kv_store,
                                  flag=self.flags, only_store_hash=only_store_hash, batch_size=batch_size)
        gen_ops = copy.deepcopy(gens[0])
        if self.data_ops == 'update':
            self._load_all_buckets(server, gen_ops, 'update', self.expiration, kv_store=kv_store,
                              flag=self.flags, only_store_hash=only_store_hash, batch_size=batch_size)
        if self.data_ops in ['delete', 'recreate']:
            self._load_all_buckets(server, gen_ops, 'delete', self.expiration, kv_store=kv_store,
                              flag=self.flags, only_store_hash=only_store_hash, batch_size=batch_size)
        if self.data_ops == 'recreate':
            self._load_all_buckets(server, gen_ops, 'create', self.expiration, kv_store=kv_store,
                              flag=self.flags, only_store_hash=only_store_hash, batch_size=batch_size)
        self.verify_cluster_stats(self.servers[:self.nodes_init], only_store_hash=only_store_hash,
                                  batch_size=batch_size)

    def perform_warm_up(self):
        warmup_nodes = self.servers[-self.warmup_nodes:]
        for warmup_node in warmup_nodes:
            shell = RemoteMachineShellConnection(warmup_node)
            shell.stop_couchbase()
            shell.disconnect()
        self.sleep(20)
        for warmup_node in warmup_nodes:
            shell = RemoteMachineShellConnection(warmup_node)
            shell.start_couchbase()
            shell.disconnect()
        ClusterOperationHelper.wait_for_ns_servers_or_assert(warmup_nodes, self)

    def perform_failover(self):
        rest = RestConnection(self.master)
        nodes = rest.node_statuses()
        failover_servers = self.servers[:self.nodes_init][-self.failover_factor:]
        failover_nodes = []
        for server in failover_servers:
            for node in nodes:
                if node.ip == server.ip and str(node.port) == server.port:
                    failover_nodes.append(node)
        for node in failover_nodes:
            rest.fail_over(node.id)
            self.sleep(5)
        if self.failover == GetrTests.FAILOVER_REBALANCE:
            self.cluster.rebalance(self.servers[:self.nodes_init],
                               [], failover_servers)
        if self.failover == GetrTests.FAILOVER_ADD_BACK:
            for node in failover_nodes:
                rest.add_back_node(node.id)
            self.cluster.rebalance(self.servers[:self.nodes_init],
                                   [], [])
