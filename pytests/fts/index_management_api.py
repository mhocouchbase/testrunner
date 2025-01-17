# coding=utf-8

import json

from lib import global_vars
from lib.SystemEventLogLib.fts_service_events import SearchServiceEvents
from .fts_base import FTSBaseTest
from .fts_base import NodeHelper
from lib.membase.api.rest_client import RestConnection


class IndexManagementAPI(FTSBaseTest):

    def setUp(self):
        super(IndexManagementAPI, self).setUp()
        self.rest = RestConnection(self._cb_cluster.get_master_node())
        self.fts_rest = RestConnection(self._cb_cluster.get_random_fts_node())
        self.sample_bucket_name = "travel-sample"
        self.sample_index_name = "idx_travel_sample_fts"
        self.sample_index_name_1 = "idx_travel_sample_fts1"
        self.second_index = self._input.param("second_index", None)
        self.run_in_parallel = self._input.param("run_in_parallel", None)
        #self.sample_query = {"match": "United States", "field": "country"}

    def tearDown(self):
        super(IndexManagementAPI, self).tearDown()

    def test_config_settings_reflection(self):
        rest = RestConnection(self._cb_cluster.get_fts_nodes()[0])
        initial_bleve_max_result_window = int(rest.get_node_settings("bleveMaxResultWindow"))
        initial_feed_allotment = rest.get_node_settings("feedAllotment")
        initial_fts_memory_quota = int(rest.get_node_settings("ftsMemoryQuota"))
        initial_slow_query_timeout = rest.get_node_settings("slowQueryLogTimeout")

        new_bleve_max_result_window = initial_bleve_max_result_window + 1000
        new_feed_allotment = "twoFeedsPerPIndex"
        new_fts_memory_quota = initial_fts_memory_quota + 100
        new_slow_query_timeout = "30s"

        rest.set_node_setting("bleveMaxResultWindow", new_bleve_max_result_window)
        rest.set_node_setting("feedAllotment", new_feed_allotment)
        rest.set_node_setting("ftsMemoryQuota", new_fts_memory_quota)
        rest.set_node_setting("slowQueryLogTimeout", new_slow_query_timeout)

        self.sleep(5)

        verification_rest = RestConnection(self._cb_cluster.get_fts_nodes()[1])
        verification_bleve_max_result_window = int(verification_rest.get_node_settings("bleveMaxResultWindow"))
        verification_feed_allotment = verification_rest.get_node_settings("feedAllotment")
        verification_fts_memory_quota = int(verification_rest.get_node_settings("ftsMemoryQuota"))
        verification_slow_query_timeout = verification_rest.get_node_settings("slowQueryLogTimeout")

        rest.set_node_setting("feedAllotment", initial_feed_allotment)
        rest.set_node_setting("slowQueryLogTimeout", initial_slow_query_timeout)
        rest.set_node_setting("ftsMemoryQuota", initial_fts_memory_quota)
        rest.set_node_setting("bleveMaxResultWindow", initial_bleve_max_result_window)


        error = ""
        if new_bleve_max_result_window != verification_bleve_max_result_window:
            error = f'{error}\n bleve_max_result_window new setting: {new_bleve_max_result_window} ' \
                f'but actual bleve_max_result_window set {verification_bleve_max_result_window}'
        if new_feed_allotment != verification_feed_allotment:
            error = f'{error}\n feed_allotment new setting: {new_feed_allotment} ' \
                f'but actual feed_allotment set {verification_feed_allotment}'
        if new_fts_memory_quota != verification_fts_memory_quota:
            error = f'{error}\n fts_memory_quota new setting: {new_fts_memory_quota} ' \
                f'but actual fts_memory_quota set {verification_fts_memory_quota}'
        if new_slow_query_timeout != verification_slow_query_timeout:
            error = f'{error}\n slow_query_timeout new setting: {new_slow_query_timeout} ' \
                f'but actual slow_query_timeout set {verification_slow_query_timeout}'

        self.assertEqual(error, "", error)

    def test_config_settings_after_reboot(self):
        rest = RestConnection(self._cb_cluster.get_fts_nodes()[0])

        initial_bleve_max_result_window = int(rest.get_node_settings("bleveMaxResultWindow"))
        initial_feed_allotment = rest.get_node_settings("feedAllotment")
        initial_fts_memory_quota = int(rest.get_node_settings("ftsMemoryQuota"))
        initial_slow_query_timeout = rest.get_node_settings("slowQueryLogTimeout")

        new_bleve_max_result_window = initial_bleve_max_result_window + 1000
        new_feed_allotment = "twoFeedsPerPIndex"
        new_fts_memory_quota = initial_fts_memory_quota + 100
        new_slow_query_timeout = "30s"

        rest.set_node_setting("bleveMaxResultWindow", new_bleve_max_result_window)
        rest.set_node_setting("feedAllotment", new_feed_allotment)
        rest.set_node_setting("ftsMemoryQuota", new_fts_memory_quota)
        rest.set_node_setting("slowQueryLogTimeout", new_slow_query_timeout)

        self.log.info(f"Getting updated settings before reboot using node {rest.ip}")
        self.log.info("#"*80)
        self.log.info(f"bleveMaxResultWindow: {rest.get_node_settings('bleveMaxResultWindow')}")
        self.log.info(f"feedAllotment: {rest.get_node_settings('feedAllotment')}")
        self.log.info(f"ftsMemoryQuota: {rest.get_node_settings('ftsMemoryQuota')}")
        self.log.info(f"slowQueryLogTimeout: {rest.get_node_settings('slowQueryLogTimeout')}")
        self.log.info("#"*80)

        self.sleep(5)

        NodeHelper.reboot_server(self._cb_cluster.get_fts_nodes()[0], test_case=self)

        self.sleep(10)

        verification_bleve_max_result_window = int(rest.get_node_settings("bleveMaxResultWindow"))
        verification_feed_allotment = rest.get_node_settings("feedAllotment")
        verification_fts_memory_quota = int(rest.get_node_settings("ftsMemoryQuota"))
        verification_slow_query_timeout = rest.get_node_settings("slowQueryLogTimeout")

        self.log.info(f"Getting updated settings after reboot using node {rest.ip}")
        self.log.info("#"*80)
        self.log.info(f"bleveMaxResultWindow: {verification_bleve_max_result_window}")
        self.log.info(f"feedAllotment: {verification_feed_allotment}")
        self.log.info(f"ftsMemoryQuota: {verification_fts_memory_quota}")
        self.log.info(f"slowQueryLogTimeout: {verification_slow_query_timeout}")
        self.log.info("#"*80)

        error = ""
        if new_bleve_max_result_window != verification_bleve_max_result_window:
            error = f'{error}\n bleve_max_result_window new setting: {new_bleve_max_result_window} ' \
                f'but actual bleve_max_result_window set {verification_bleve_max_result_window} after reboot'
        if new_feed_allotment != verification_feed_allotment:
            error = f'{error}\n feed_allotment new setting: {new_feed_allotment} ' \
                f'but actual feed_allotment set {verification_feed_allotment} after reboot'
        if new_fts_memory_quota != verification_fts_memory_quota:
            error = f'{error}\n fts_memory_quota new setting: {new_fts_memory_quota} ' \
                f'but actual fts_memory_quota set {verification_fts_memory_quota} after reboot'
        if new_slow_query_timeout != verification_slow_query_timeout:
            error = f'{error}\n slow_query_timeout new setting: {new_slow_query_timeout} ' \
                f'but actual slow_query_timeout set {verification_slow_query_timeout} after reboot'

        rest.set_node_setting("feedAllotment", initial_feed_allotment)
        rest.set_node_setting("slowQueryLogTimeout", initial_slow_query_timeout)
        rest.set_node_setting("ftsMemoryQuota", initial_fts_memory_quota)
        rest.set_node_setting("bleveMaxResultWindow", initial_bleve_max_result_window)

        self.assertEqual(error, "", error)

    def test_config_settings_new_node(self):
        rest = RestConnection(self._cb_cluster.get_fts_nodes()[0])
        initial_bleve_max_result_window = int(rest.get_node_settings("bleveMaxResultWindow"))
        initial_feed_allotment = rest.get_node_settings("feedAllotment")
        initial_fts_memory_quota = int(rest.get_node_settings("ftsMemoryQuota"))
        initial_slow_query_timeout = rest.get_node_settings("slowQueryLogTimeout")

        self.log.info(f"Getting initial settings using node {rest.ip}")
        self.log.info("#"*80)
        self.log.info(f"bleveMaxResultWindow: {initial_bleve_max_result_window}")
        self.log.info(f"feedAllotment: {initial_feed_allotment}")
        self.log.info(f"ftsMemoryQuota: {initial_fts_memory_quota}")
        self.log.info(f"slowQueryLogTimeout: {initial_slow_query_timeout}")
        self.log.info("#"*80)

        new_bleve_max_result_window = initial_bleve_max_result_window + 1000
        new_feed_allotment = "twoFeedsPerPIndex"
        new_fts_memory_quota = initial_fts_memory_quota + 100
        new_slow_query_timeout = "30s"

        rest.set_node_setting("bleveMaxResultWindow", new_bleve_max_result_window)
        rest.set_node_setting("feedAllotment", new_feed_allotment)
        rest.set_node_setting("ftsMemoryQuota", new_fts_memory_quota)
        rest.set_node_setting("slowQueryLogTimeout", new_slow_query_timeout)

        self.log.info(f"Getting updated settings using node {rest.ip}")
        self.log.info("#"*80)
        self.log.info(f"bleveMaxResultWindow: {new_bleve_max_result_window}")
        self.log.info(f"feedAllotment: {new_feed_allotment}")
        self.log.info(f"ftsMemoryQuota: {new_fts_memory_quota}")
        self.log.info(f"slowQueryLogTimeout: {new_slow_query_timeout}")
        self.log.info("#"*80)

        self._cb_cluster.rebalance_in(num_nodes=1, services=["kv,fts"])
        self.log.info("Rebalanced in new node.")
        self.sleep(30)

        verification_rest = RestConnection(self._cb_cluster.get_fts_nodes()[1])
        verification_bleve_max_result_window = int(verification_rest.get_node_settings("bleveMaxResultWindow"))
        verification_feed_allotment = verification_rest.get_node_settings("feedAllotment")
        verification_fts_memory_quota = int(verification_rest.get_node_settings("ftsMemoryQuota"))
        verification_slow_query_timeout = verification_rest.get_node_settings("slowQueryLogTimeout")

        self.log.info(f"Getting new node settings using node {verification_rest.ip}")
        self.log.info("#"*80)
        self.log.info(f"bleveMaxResultWindow: {verification_bleve_max_result_window}")
        self.log.info(f"feedAllotment: {verification_feed_allotment}")
        self.log.info(f"ftsMemoryQuota: {verification_fts_memory_quota}")
        self.log.info(f"slowQueryLogTimeout: {verification_slow_query_timeout}")
        self.log.info("#"*80)


        rest.set_node_setting("feedAllotment", initial_feed_allotment)
        rest.set_node_setting("slowQueryLogTimeout", initial_slow_query_timeout)
        rest.set_node_setting("ftsMemoryQuota", initial_fts_memory_quota)
        rest.set_node_setting("bleveMaxResultWindow", initial_bleve_max_result_window)


        error = ""
        if new_bleve_max_result_window != verification_bleve_max_result_window:
            error = error + "\nbleveMaxResultWindow is not propagated on new node."
        if new_feed_allotment != verification_feed_allotment:
            error = error + "\nfeedAllotment is not propagated on new node."
        if new_fts_memory_quota != verification_fts_memory_quota:
            error = error + "\nftsMemoryQuota is not propagated on new node."
        if new_slow_query_timeout != verification_slow_query_timeout:
            error = error + "\nslowQueryLogTimeout is not propagated on new node."

        self.assertEqual(error, "", error)

    def test_config_settings(self):
        config = self._input.param("config", "bleveMaxResultWindow")
        value = self._input.param("value", 100000)
        rest = RestConnection(self._cb_cluster.get_fts_nodes()[0])

        rest.set_node_setting(config, value)
        global_vars.system_event_logs.add_event(SearchServiceEvents.fts_settings_updated())

        verification_config_setting = rest.get_node_settings(config)

        if str(verification_config_setting) != str(value):
            self.fail(f'{verification_config_setting} is not equal to expected {value} for config:{config}')

    def test_ingest_control(self):
        self.load_data()
        collection_index, _type, index_scope, index_collections = self.define_index_parameters_collection_related()
        fts_index = self._cb_cluster.create_fts_index(name=self.sample_index_name, source_name="default",
                                                      collection_index=collection_index, _type=_type, scope=index_scope, collections=index_collections)
        self.sleep(5)
        self.fts_rest.stop_fts_index_update(fts_index.name)

        self.sleep(10)
        index_count_after_pause = fts_index.get_indexed_doc_count()
        self.log.info("index paused and number of docs at present : {0}".format(index_count_after_pause))
        self.sleep(30)

        if self.second_index:
            if self.run_in_parallel:
                self._cb_cluster.create_fts_index(name=self.sample_index_name_1, source_name="default",
                                                  collection_index=collection_index, _type=_type)
            else:
                self._cb_cluster.create_fts_index_wait_for_completion(self.sample_index_name_1, "default",
                                                                      collection_index=collection_index, _type=_type)

        current_index_count = fts_index.get_indexed_doc_count()

        if index_count_after_pause != current_index_count:
            self.fail("Index not paused and number of docs at present : {0}".format(current_index_count))
        else:
            self.log.info("index still paused and number of docs at present : {0}. Now resuming".format(index_count_after_pause))

        self.fts_rest.resume_fts_index_update(fts_index.name)
        self.sleep(10)
        self.wait_for_indexing_complete()
        self.validate_index_count(equal_bucket_doc_count=True)

    def test_planfreeze_control(self):
        self.load_data()
        collection_index, _type, index_scope, index_collections = self.define_index_parameters_collection_related()
        fts_index = self._cb_cluster.create_fts_index(name=self.sample_index_name, source_name="default",
                                                      collection_index=collection_index, _type=_type, scope=index_scope, collections=index_collections)
        self.sleep(20)
        self.fts_rest.freeze_fts_index_partitions(fts_index.name)
        self.wait_for_indexing_complete()
        index_count_after_freeze = fts_index.get_indexed_doc_count()

        try:
            fts_index.update_index_partitions(1)
            self.sleep(5)
        except Exception as e:
            if "cannot update partition or replica count for a planFrozen index" in str(e):
                self.log.info("Error expected :   {0}".format(e))
            else:
                self.fail("An unexpected error occured:   {0}".format(e))

        current_index_count = fts_index.get_indexed_doc_count()

        if index_count_after_freeze != current_index_count:
            self.fail("Index changed after freeze and update")
        else:
            self.log.info("index still not changed  number of docs at present : {0}. Now unfreezing".format(current_index_count))

        self.fts_rest.unfreeze_fts_index_partitions(fts_index.name)
        fts_index.update_index_partitions(1)
        self.sleep(5)
        self.wait_for_indexing_complete()
        self.validate_index_count(equal_bucket_doc_count=True)

    def test_planfreeze_control_with_2indexes(self):
        self.load_sample_buckets(self._cb_cluster.get_master_node(), self.sample_bucket_name)
        fts_index = self._cb_cluster.create_fts_index(name=self.sample_index_name, source_name=self.sample_bucket_name)
        fts_index2 = self._cb_cluster.create_fts_index(name=self.sample_index_name_1, source_name=self.sample_bucket_name)
        self.wait_for_indexing_complete()
        self.fts_rest.freeze_fts_index_partitions(fts_index.name)
        self.sleep(5)
        fts_index2.update_index_partitions(1)
        self.wait_for_indexing_complete()
        self.validate_index_count(equal_bucket_doc_count=True)

    def test_query_control(self):
        self.load_data()
        collection_index, _type, index_scope, index_collections = self.define_index_parameters_collection_related()
        fts_index = self._cb_cluster.create_fts_index(name=self.sample_index_name, source_name="default",
                                                      collection_index=collection_index, _type=_type, scope=index_scope, collections=index_collections)
        self.wait_for_indexing_complete()
        self.fts_rest.disable_querying_on_fts_index(fts_index.name)
        self.sleep(5)
        query = eval(self._input.param("query", str(self.sample_query)))
        if isinstance(query, str):
            query = json.loads(query)
        hits, matches, _, status= fts_index.execute_query(query,
                                                  zero_results_ok=True,
                                                  expected_hits=None,
                                                  expected_no_of_results=None)
        self.log.info("Hits: %s" % hits)
        self.log.info("Matches: %s" % matches)
        if "pindex not available" in str(status["errors"]):
            self.log.info("Expected error \"pindex not available\" exits in errors of query : {0}"
                          .format(status["errors"]))
        else:
            self.fail("Expected error \"pindex not available\" not found")

        self.log.info("now allowing to run query on this index")

        self.fts_rest.enable_querying_on_fts_index(fts_index.name)
        self.sleep(5)
        hits, matches, _, status= fts_index.execute_query(query,
                                                          zero_results_ok=False,
                                                          expected_hits=None,
                                                          expected_no_of_results=None)
        self.log.info("Hits: %s" % hits)
        if "errors" in status.keys():
            self.fail("Errors found while running query : {0}".format(status["errors"]))

    def test_query_control_n1fty(self):
        self.load_data()
        collection_index, _type, index_scope, index_collections = self.define_index_parameters_collection_related()
        fts_index_1 = self.create_index(
            bucket=self._cb_cluster.get_bucket_by_name('default'),
            index_name="default_index_1",
            collection_index=collection_index, _type=_type,
            scope=index_scope,
            collections=index_collections)
        fts_index_2 = self.create_index(
            bucket=self._cb_cluster.get_bucket_by_name('default'),
            index_name="default_index_2",
            collection_index=collection_index, _type=_type,
            scope=index_scope, collections=index_collections)
        self.wait_for_indexing_complete()
        self.fts_rest.disable_querying_on_fts_index(fts_index_1.name)
        self.sleep(5)
        self.generate_random_queries(fts_index_2, self.num_queries, self.query_types)
        self.run_query_and_compare(fts_index_2, n1ql_executor=self._cb_cluster, use_collections=collection_index)

    def test_index_plan_update_disallow_query(self):
        self.load_data()
        collection_index, _type, index_scope, index_collections = self.define_index_parameters_collection_related()
        fts_index = self._cb_cluster.create_fts_index(name=self.sample_index_name, source_name="default",
                                                      collection_index=collection_index, _type=_type, scope=index_scope, collections=index_collections)
        self.sleep(3)
        self.fts_rest.disable_querying_on_fts_index(fts_index.name)
        self.wait_for_indexing_complete()
        self.validate_index_count(equal_bucket_doc_count=True)

        self.log.info("Updating the plan")

        fts_index.update_index_partitions(1)
        self.sleep(10)
        self.wait_for_indexing_complete()
        self.validate_index_count(equal_bucket_doc_count=True)