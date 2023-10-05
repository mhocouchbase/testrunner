import random
import time

from membase.api.rest_client import RestConnection, RestHelper
from concurrent.futures import ThreadPoolExecutor
from couchbase_helper.documentgenerator import SDKDataLoader
from lib import testconstants
from lib.remote.remote_util import RemoteMachineShellConnection
from pytests.fts.fts_base import NodeHelper
from pytests.query_tests_helper import QueryHelperTests
from .base_gsi import BaseSecondaryIndexingTests, log
from threading import Event
from deepdiff import DeepDiff


class FileBasedRebalance(BaseSecondaryIndexingTests, QueryHelperTests,  NodeHelper):
    def setUp(self):
        if self._testMethodName not in ['suite_tearDown', 'suite_setUp']:
            super().setUp()
            self.rest = RestConnection(self.servers[0])
            self.n1ql_server = self.get_nodes_from_services_map(service_type="n1ql", get_all_nodes=False)
            self.create_primary_index = False
            self.retry_time = self.input.param("retry_time", 300)
            self.sleep_time = self.input.param("sleep_time", 1)
            self.num_retries = self.input.param("num_retries", 1)
            self.build_index = self.input.param("build_index", False)
            self.rebalance_all_at_once = self.input.param("rebalance_all_at_once", False)
            self.continuous_mutations = self.input.param("continuous_mutations", False)
            self.initial_index_batches = self.input.param("initial_index_batches", 2)
            # TODO. After adding other tests, check if this can be removed
            # if not self.capella_run:
            #     shell = RemoteMachineShellConnection(self.servers[0])
            #     info = shell.extract_remote_info().type.lower()
            #     if info == 'linux':
            #         if self.nonroot:
            #             self.cli_command_location = testconstants.LINUX_NONROOT_CB_BIN_PATH
            #         else:
            #             self.cli_command_location = testconstants.LINUX_COUCHBASE_BIN_PATH
            #     elif info == 'windows':
            #         self.cmd_ext = ".exe"
            #         self.cli_command_location = testconstants.WIN_COUCHBASE_BIN_PATH_RAW
            #     elif info == 'mac':
            #         self.cli_command_location = testconstants.MAC_COUCHBASE_BIN_PATH
            #     else:
            #         raise Exception("OS not supported.")
            self.rand = random.randint(1, 1000000000)
            self.alter_index = self.input.param("alter_index", None)
            if self.ansi_join:
                self.rest.load_sample("travel-sample")
                self.sleep(10)
            indexer_nodes = self.get_nodes_from_services_map(service_type="index", get_all_nodes=True)
            for indexer_node in indexer_nodes:
                rest = RestConnection(indexer_node)
                rest.set_index_settings({"indexer.settings.enableShardAffinity": True})
            self.NUM_DOCS_POST_REBALANCE = 10 ** 5

    def tearDown(self):
        if self._testMethodName not in ['suite_tearDown', 'suite_setUp']:
            super(FileBasedRebalance, self).tearDown()

    def suite_setUp(self):
        pass

    def suite_tearDown(self):
        pass

    def test_gsi_rebalance_out_indexer_node(self):
        self.bucket_params = self._create_bucket_params(server=self.master, size=self.bucket_size,
                                                        replicas=self.num_replicas, bucket_type=self.bucket_type,
                                                        enable_replica_index=self.enable_replica_index,
                                                        eviction_policy=self.eviction_policy, lww=self.lww)
        self.cluster.create_standard_bucket(name=self.test_bucket, port=11222,
                                            bucket_params=self.bucket_params)
        self.buckets = self.rest.get_buckets()
        self.prepare_collection_for_indexing(num_scopes=self.num_scopes, num_collections=self.num_collections,
                                             num_of_docs_per_collection=self.num_of_docs_per_collection,
                                             json_template=self.json_template,
                                             load_default_coll=True)
        time.sleep(10)
        skip_array_index_item_count, scan_results_check = False, True
        with ThreadPoolExecutor() as executor_main:
            try:
                event = Event()
                if self.continuous_mutations:
                    future = executor_main.submit(self.perform_continuous_kv_mutations, event)
                    skip_array_index_item_count = True
                    scan_results_check = False
                select_queries = set()
                query_node = self.get_nodes_from_services_map(service_type="n1ql")
                for _ in range(self.initial_index_batches):
                    replica_count = random.randint(0, 2)
                    query_definitions = self.gsi_util_obj.generate_hotel_data_index_definition()
                    for namespace in self.namespaces:
                        select_queries.update(self.gsi_util_obj.get_select_queries(definition_list=query_definitions,
                                                                                   namespace=namespace))
                        queries = self.gsi_util_obj.get_create_index_list(definition_list=query_definitions,
                                                                          namespace=namespace,
                                                                          num_replica=replica_count,
                                                                          randomise_replica_count=True)
                        self.gsi_util_obj.create_gsi_indexes(create_queries=queries, database=namespace, query_node=query_node)
                self.wait_until_indexes_online()
                self.validate_shard_affinity()
                nodes_out = self.get_nodes_from_services_map(service_type="index", get_all_nodes=True)
                nodes_out_list = nodes_out[:2]
                if self.rebalance_all_at_once:
                    # rebalance out all nodes at once
                    self.rebalance_and_validate(nodes_out_list=nodes_out_list,
                                                swap_rebalance=False,
                                                skip_array_index_item_count=skip_array_index_item_count,
                                                select_queries=select_queries,
                                                scan_results_check=scan_results_check)
                else:
                    # rebalance out 1 node after another
                    for count, node in enumerate(nodes_out_list):
                        self.log.info(f"Running rebalance number {count}")
                        self.rebalance_and_validate(nodes_out_list=[node], swap_rebalance=False,
                                                    skip_array_index_item_count=skip_array_index_item_count,
                                                    select_queries=select_queries,
                                                    scan_results_check=scan_results_check)
                map_after_rebalance, stats_map_after_rebalance = self._return_maps()
                self.run_post_rebalance_operations(map_after_rebalance=map_after_rebalance,
                                                   stats_map_after_rebalance=stats_map_after_rebalance)
            finally:
                event.set()
                if self.continuous_mutations:
                    future.result()

    def test_gsi_rebalance_in_indexer_node(self):
        indexer_nodes = self.get_nodes_from_services_map(service_type="index", get_all_nodes=True)
        for indexer_node in indexer_nodes:
            rest = RestConnection(indexer_node)
            rest.set_index_settings({"indexer.settings.rebalance.redistribute_indexes": True})
        self.bucket_params = self._create_bucket_params(server=self.master, size=self.bucket_size,
                                                        replicas=self.num_replicas, bucket_type=self.bucket_type,
                                                        enable_replica_index=self.enable_replica_index,
                                                        eviction_policy=self.eviction_policy, lww=self.lww)
        self.cluster.create_standard_bucket(name=self.test_bucket, port=11222,
                                            bucket_params=self.bucket_params)
        self.buckets = self.rest.get_buckets()
        self.prepare_collection_for_indexing(num_scopes=self.num_scopes, num_collections=self.num_collections,
                                             num_of_docs_per_collection=self.num_of_docs_per_collection,
                                             json_template=self.json_template, load_default_coll=True)
        time.sleep(10)
        skip_array_index_item_count, scan_results_check = False, True
        with ThreadPoolExecutor() as executor_main:
            try:
                event = Event()
                if self.continuous_mutations:
                    future = executor_main.submit(self.perform_continuous_kv_mutations, event)
                    skip_array_index_item_count = True
                    scan_results_check = False
                select_queries = set()
                query_node = self.get_nodes_from_services_map(service_type="n1ql")
                for _ in range(self.initial_index_batches):
                    replica_count = random.randint(0, 2)
                    query_definitions = self.gsi_util_obj.generate_hotel_data_index_definition()
                    for namespace in self.namespaces:
                        select_queries.update(self.gsi_util_obj.get_select_queries(definition_list=query_definitions,
                                                                                   namespace=namespace))
                        queries = self.gsi_util_obj.get_create_index_list(definition_list=query_definitions,
                                                                          namespace=namespace,
                                                                          num_replica=replica_count,
                                                                          randomise_replica_count=True)
                        self.gsi_util_obj.create_gsi_indexes(create_queries=queries, database=namespace, query_node=query_node)
                self.wait_until_indexes_online()
                self.validate_shard_affinity()
                nodes_in_list = self.servers[self.nodes_init:]
                if self.rebalance_all_at_once:
                    # rebalance all nodes at once
                    services_in = ["index"] * len(nodes_in_list)
                    self.rebalance_and_validate(nodes_out_list=[],
                                                nodes_in_list=nodes_in_list,
                                                swap_rebalance=False,
                                                skip_array_index_item_count=skip_array_index_item_count,
                                                services_in=services_in,
                                                select_queries=select_queries,
                                                scan_results_check=scan_results_check
                                                )
                else:
                    services_in = ["index"]
                    # rebalance in 1 node after another
                    for count, node in enumerate(nodes_in_list):
                        self.log.info(f"Running rebalance number {count}")
                        self.rebalance_and_validate(nodes_out_list=[], nodes_in_list=[node],
                                                    swap_rebalance=False,
                                                    skip_array_index_item_count=skip_array_index_item_count,
                                                    services_in=services_in,
                                                    select_queries=select_queries,
                                                    scan_results_check=scan_results_check
                                                    )
                map_after_rebalance, stats_map_after_rebalance = self._return_maps()
                self.run_post_rebalance_operations(map_after_rebalance=map_after_rebalance,
                                                   stats_map_after_rebalance=stats_map_after_rebalance)
            finally:
                event.set()
                if self.continuous_mutations:
                    future.result()

    def test_gsi_swap_rebalance(self):
        self.bucket_params = self._create_bucket_params(server=self.master, size=self.bucket_size,
                                                        replicas=self.num_replicas, bucket_type=self.bucket_type,
                                                        enable_replica_index=self.enable_replica_index,
                                                        eviction_policy=self.eviction_policy, lww=self.lww)
        self.cluster.create_standard_bucket(name=self.test_bucket, port=11222,
                                            bucket_params=self.bucket_params)
        self.buckets = self.rest.get_buckets()
        self.prepare_collection_for_indexing(num_scopes=self.num_scopes, num_collections=self.num_collections,
                                             num_of_docs_per_collection=self.num_of_docs_per_collection,
                                             json_template=self.json_template, load_default_coll=True)
        time.sleep(10)
        skip_array_index_item_count, scan_results_check = False, True
        with ThreadPoolExecutor() as executor_main:
            try:
                event = Event()
                if self.continuous_mutations:
                    future = executor_main.submit(self.perform_continuous_kv_mutations, event)
                    skip_array_index_item_count = True
                    scan_results_check = False
                select_queries = set()
                query_node = self.get_nodes_from_services_map(service_type="n1ql")
                for _ in range(self.initial_index_batches):
                    replica_count = random.randint(0, 2)
                    query_definitions = self.gsi_util_obj.generate_hotel_data_index_definition()
                    for namespace in self.namespaces:
                        select_queries.update(self.gsi_util_obj.get_select_queries(definition_list=query_definitions,
                                                                                   namespace=namespace))
                        queries = self.gsi_util_obj.get_create_index_list(definition_list=query_definitions,
                                                                          namespace=namespace,
                                                                          num_replica=replica_count,
                                                                          randomise_replica_count=True)
                        self.gsi_util_obj.create_gsi_indexes(create_queries=queries, database=namespace, query_node=query_node)
                self.wait_until_indexes_online()
                self.validate_shard_affinity()
                nodes_out_list = self.get_nodes_from_services_map(service_type="index", get_all_nodes=True)
                to_remove_nodes = nodes_out_list[:2]
                to_add_nodes = self.servers[self.nodes_init:]
                if self.rebalance_all_at_once:
                    # rebalance out all nodes at once
                    services_in = ["index"] * len(to_add_nodes)
                    self.rebalance_and_validate(nodes_out_list=to_remove_nodes,
                                                nodes_in_list=to_add_nodes,
                                                swap_rebalance=True,
                                                skip_array_index_item_count=skip_array_index_item_count,
                                                services_in=services_in, select_queries=select_queries,
                                                scan_results_check=scan_results_check)
                else:
                    # rebalance out 1 node after another
                    services_in = ["index"]
                    for i in range(len(to_add_nodes)):
                        self.log.info(f"Running rebalance number {i}")
                        self.rebalance_and_validate(nodes_out_list=[to_remove_nodes[i]],
                                                    nodes_in_list=[to_add_nodes[i]],
                                                    swap_rebalance=True,
                                                    skip_array_index_item_count=skip_array_index_item_count,
                                                    services_in=services_in, select_queries=select_queries,
                                                scan_results_check=scan_results_check)
                map_after_rebalance, stats_map_after_rebalance = self._return_maps()
                self.run_post_rebalance_operations(map_after_rebalance=map_after_rebalance,
                                                   stats_map_after_rebalance=stats_map_after_rebalance)
            finally:
                event.set()
                if self.continuous_mutations:
                    future.result()

    def test_gsi_failover_indexer_node(self):
        self.bucket_params = self._create_bucket_params(server=self.master, size=self.bucket_size,
                                                        replicas=self.num_replicas, bucket_type=self.bucket_type,
                                                        enable_replica_index=self.enable_replica_index,
                                                        eviction_policy=self.eviction_policy, lww=self.lww)
        self.cluster.create_standard_bucket(name=self.test_bucket, port=11222,
                                            bucket_params=self.bucket_params)
        self.buckets = self.rest.get_buckets()
        self.prepare_collection_for_indexing(num_scopes=self.num_scopes, num_collections=self.num_collections,
                                             num_of_docs_per_collection=self.num_of_docs_per_collection,
                                             json_template=self.json_template, load_default_coll=True)
        time.sleep(10)
        skip_array_index_item_count, scan_results_check = False, True
        with ThreadPoolExecutor() as executor_main:
            try:
                event = Event()
                if self.continuous_mutations:
                    future = executor_main.submit(self.perform_continuous_kv_mutations, event)
                    skip_array_index_item_count = True
                    scan_results_check = False
                select_queries = set()
                query_node = self.get_nodes_from_services_map(service_type="n1ql")
                for _ in range(self.initial_index_batches):
                    replica_count = random.randint(0, 2)
                    query_definitions = self.gsi_util_obj.generate_hotel_data_index_definition()
                    for namespace in self.namespaces:
                        select_queries.update(self.gsi_util_obj.get_select_queries(definition_list=query_definitions,
                                                                                   namespace=namespace))
                        queries = self.gsi_util_obj.get_create_index_list(definition_list=query_definitions,
                                                                          namespace=namespace,
                                                                          num_replica=replica_count,
                                                                          randomise_replica_count=True)
                        self.gsi_util_obj.create_gsi_indexes(create_queries=queries, database=namespace, query_node=query_node)
                self.wait_until_indexes_online()
                self.validate_shard_affinity()
                nodes_out = self.get_nodes_from_services_map(service_type="index", get_all_nodes=True)
                nodes_out_list = nodes_out[:2]
                if self.rebalance_all_at_once:
                    # failover all nodes at once
                    self.rebalance_and_validate(failover_nodes_list=nodes_out_list,
                                                swap_rebalance=False,
                                                skip_array_index_item_count=skip_array_index_item_count,
                                                select_queries=select_queries,
                                                scan_results_check=scan_results_check
                                                )
                else:
                    # failover 1 node after another
                    for count, node in enumerate(nodes_out_list):
                        self.log.info(f"Running rebalance number {count}")
                        self.rebalance_and_validate(failover_nodes_list=[node], swap_rebalance=False,
                                                    skip_array_index_item_count=skip_array_index_item_count,
                                                    select_queries=select_queries,
                                                    scan_results_check=scan_results_check
                                                    )
                map_after_rebalance, stats_map_after_rebalance = self._return_maps()
                self.run_post_rebalance_operations(map_after_rebalance=map_after_rebalance,
                                                   stats_map_after_rebalance=stats_map_after_rebalance)
            finally:
                event.set()
                future.result()


    def _return_maps(self):
        index_map = self.get_index_map_from_index_endpoint(return_system_query_scope=False)
        stats_map = self.get_index_stats(perNode=True, return_system_query_scope=False)
        return index_map, stats_map

    def run_operation(self, phase="before"):
        if phase == "before":
            self.run_async_index_operations(operation_type="create_index")
        elif phase == "during":
            self.run_async_index_operations(operation_type="query")
        elif phase == "after":
            n1ql_server = self.get_nodes_from_services_map(service_type="n1ql", get_all_nodes=False)
            country, address, city, email = f"test_country{random.randint(0, 100)}", f"test_add{random.randint(0, 100)}", \
                                            f"test_city{random.randint(0, 100)}", f"test_email{random.randint(0, 100)}"
            doc_body = {
              "country": country,
              "address": address,
              "free_parking": False,
              "city": city,
              "type": "Hotel",
              "url": "www.henrietta-hegmann.co",
              "reviews": [
                {
                  "date": "2023-09-15 08:57:48",
                  "author": "Ms. Selma Schaden",
                  "ratings": {
                    "Value": 1,
                    "Cleanliness": 1,
                    "Overall": 4,
                    "Check in / front desk": 2,
                    "Rooms": 2
                  }
                },
                {
                  "date": "2023-09-29 08:57:48",
                  "author": "test_author",
                  "ratings": {
                    "Value": 3,
                    "Cleanliness": 1,
                    "Overall": 1,
                    "Check in / front desk": 1,
                    "Rooms": 2
                  }
                }
              ],
              "phone": "364-389-9784",
              "price": 1134,
              "avg_rating": 3,
              "free_breakfast": True,
              "name": "Jame Cummings Hotel",
              "public_likes": [
                "Mr. Brian Grimes",
                "Linwood Hermann",
                "Micah Funk",
                "Micheal Hansen"
              ],
              "email": email
            }
            collection_namespace = self.namespaces[0]
            _, keyspace = collection_namespace.split(':')
            bucket, scope, collection = keyspace.split('.')
            insert_query = f'INSERT INTO {collection_namespace} (KEY, VALUE) VALUES ("scan_doc_1", {doc_body})'
            select_query = f'Select country, city from {collection_namespace} where meta().id = "scan_doc_1"'
            count_query = f'Select count(meta().id) from {collection_namespace} where price >= 0'
            gen_create = SDKDataLoader(num_ops=self.NUM_DOCS_POST_REBALANCE, percent_create=100,
                                       percent_update=0, percent_delete=0, scope=scope,
                                       collection=collection, start_seq_num=self.num_of_docs_per_collection + 1,
                                       json_template=self.json_template)
            try:
                with ThreadPoolExecutor() as executor:
                    executor.submit(self._load_all_buckets, self.master, gen_create)
                    executor.submit(self.run_cbq_query, query=insert_query, server=n1ql_server)
                    self.sleep(15, "Giving some time so the mutations start")
                    select_task = executor.submit(self.run_cbq_query, query=select_query,
                                                  scan_consistency='request_plus', server=n1ql_server)
                    count_task = executor.submit(self.run_cbq_query, query=count_query, scan_consistency='request_plus',
                                                 server=n1ql_server)

                    result1 = select_task.result()['results'][0]
                    result2 = count_task.result()['results'][0]['$1']
                print(f"Result1 {result1} Result2 {result2}")
                self.assertEqual(result1, {'city': city, 'country': country},
                                 "scan_doc_1 which was inserted before scan request with request_plus is not in result")
                self.assertTrue(result2 > self.num_of_docs_per_collection + 1,
                                "request plus scan is not able to wait for new inserted docs")
            except Exception as err:
                self.fail(str(err))
            self.run_async_index_operations(operation_type="query")
        else:
            self.run_async_index_operations(operation_type="drop_index")

    def perform_continuous_kv_mutations(self, event):
        collection_namespaces = self.namespaces
        while not event.is_set():
            for namespace in collection_namespaces:
                _, keyspace = namespace.split(':')
                bucket, scope, collection = keyspace.split('.')
                self.gen_create = SDKDataLoader(num_ops=self.num_of_docs_per_collection, percent_create=100,
                                                percent_update=10, percent_delete=0, scope=scope,
                                                collection=collection, json_template=self.json_template,
                                                output=True, username=self.username, password=self.password)
                if self.use_magma_loader:
                    task = self.cluster.async_load_gen_docs(self.master, bucket=bucket,
                                                            generator=self.gen_create, pause_secs=1,
                                                            timeout_secs=300, use_magma_loader=True)
                    task.result()
                else:
                    tasks = self.data_ops_javasdk_loader_in_batches(sdk_data_loader=self.gen_create,
                                                                    batch_size=10**4, dataset=self.json_template)
                    for task in tasks:
                        task.result()
                time.sleep(10)

    def rebalance_and_validate(self, nodes_out_list=None, nodes_in_list=None,
                               swap_rebalance=False, skip_array_index_item_count=False,
                               services_in=None, failover_nodes_list=None, select_queries=None,
                               scan_results_check=False):
        if not nodes_out_list:
            nodes_out_list = []
        if not nodes_in_list:
            nodes_in_list = []
        # TODO uncomment after MB fix
        # time.sleep(60)
        shard_list_before_rebalance = self.fetch_shard_id_list()
        map_before_rebalance, stats_map_before_rebalance = self._return_maps()
        self.log.info("Running scans before rebalance")
        query_result = {}
        if scan_results_check and select_queries is not None:
            n1ql_server = self.get_nodes_from_services_map(service_type="n1ql", get_all_nodes=False)
            for query in select_queries:
                query_result[query] = self.run_cbq_query(query=query, scan_consistency='request_plus',
                                                         server=n1ql_server)['results']
        if failover_nodes_list is not None:
            self.log.info(f"Running failover task for node {failover_nodes_list}")
            failover_task = self.cluster.async_failover([self.master], failover_nodes=failover_nodes_list,
                                                        graceful=False)
            failover_task.result()
        # rebalance operation
        rebalance = self.cluster.async_rebalance(self.servers[:self.nodes_init], nodes_in_list, nodes_out_list,
                                                 services=services_in, cluster_config=self.cluster_config)
        self.log.info(f"Rebalance task triggered. Wait in loop until the rebalance starts")
        time.sleep(3)
        status, _ = self.rest._rebalance_status_and_progress()
        while status != 'running':
            time.sleep(1)
            status, _ = self.rest._rebalance_status_and_progress()
        self.log.info("Rebalance has started running.")
        self.run_operation(phase="during")
        reached = RestHelper(self.rest).rebalance_reached()
        self.assertTrue(reached, "rebalance failed, stuck or did not complete")
        rebalance.result()
        # TODO uncomment after MB fix
        # time.sleep(30)
        self.log.info("Fetching list of shards after completion of rebalance")
        # TODO uncomment after MB fix
        # time.sleep(60)
        shard_list_after_rebalance = self.fetch_shard_id_list()
        self.log.info("Compare shard list before and after rebalance.")
        # uncomment after MB-58776 is fixed
        # if shard_list_after_rebalance != shard_list_before_rebalance:
        #     self.log.error(
        #         f"Shards before {shard_list_before_rebalance}. Shards after {shard_list_after_rebalance}")
        #     raise AssertionError("Shards missing after rebalance")
        self.log.info(
            f"Shard list before rebalance {shard_list_before_rebalance}. After rebalance {shard_list_after_rebalance}")
        self.log.info("Running scans after rebalance")
        if scan_results_check and select_queries is not None:
            n1ql_server = self.get_nodes_from_services_map(service_type="n1ql", get_all_nodes=False)
            for query in select_queries:
                post_rebalance_result = self.run_cbq_query(query=query, scan_consistency='request_plus',
                                                         server=n1ql_server)['results']
                diffs = DeepDiff(post_rebalance_result, query_result[query], ignore_order=True)
                if diffs:
                    self.log.error(f"Mismatch in query result before and after rebalance. Select query {query}. "
                                   f"Result before {query_result[query]}."
                                   f"Result after {post_rebalance_result}")
                    raise Exception("Mismatch in query results before and after rebalance")
        map_after_rebalance, stats_map_after_rebalance = self._return_maps()
        self.log.info("Fetch metadata after rebalance")
        self.n1ql_helper.verify_indexes_redistributed(map_before_rebalance=map_before_rebalance,
                                                      map_after_rebalance=map_after_rebalance,
                                                      stats_map_before_rebalance=stats_map_before_rebalance,
                                                      stats_map_after_rebalance=stats_map_after_rebalance,
                                                      nodes_in=nodes_in_list,
                                                      nodes_out=nodes_out_list,
                                                      swap_rebalance=swap_rebalance,
                                                      use_https=False,
                                                      item_count_increase=False,
                                                      per_node=True,
                                                      skip_array_index_item_count=skip_array_index_item_count)
        # uncomment after MB-58776 is fixed
        # self.validate_shard_affinity()
        self.sleep(30)
        self.check_gsi_logs_for_shard_transfer()

    def run_post_rebalance_operations(self, map_after_rebalance, stats_map_after_rebalance):
        self.run_operation(phase="after")
        map_after_rebalance_2, stats_map_after_rebalance_2 = self._return_maps()
        self.n1ql_helper.validate_item_count_data_size(map_before_rebalance=map_after_rebalance,
                                                       map_after_rebalance=map_after_rebalance_2,
                                                       stats_map_before_rebalance=stats_map_after_rebalance,
                                                       stats_map_after_rebalance=stats_map_after_rebalance_2,
                                                       item_count_increase=True,
                                                       per_node=True,
                                                       skip_array_index_item_count=True)