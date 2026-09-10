__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import json
import os

from bs4 import BeautifulSoup

from amazonorders.entity.parsable import Parsable
from amazonorders.exception import AmazonOrdersError
from amazonorders.orders import AmazonOrders
from amazonorders.transactions import AmazonTransactions
from tests.unittestcase import UnitTestCase


class TestItem(UnitTestCase):
    def test_to_currency(self):
        # GIVEN
        html = "<html />"
        parsed = BeautifulSoup(html, self.test_config.bs4_parser)

        # WHEN
        parsable = Parsable(parsed, self.test_config)

        # THEN
        self.assertIsNone(parsable.to_currency(None))
        self.assertIsNone(parsable.to_currency(""))
        self.assertEqual(parsable.to_currency(1234.99), 1234.99)
        self.assertEqual(parsable.to_currency(1234), 1234)
        self.assertEqual(parsable.to_currency("1,234.99"), 1234.99)
        self.assertEqual(parsable.to_currency("$1,234.99"), 1234.99)
        self.assertIsNone(parsable.to_currency("not currency"))

    def test_safe_parse_degrades_json_shaped_failures(self):
        # GIVEN a Parsable whose parse functions fail the way page-embedded JSON does
        parsed = BeautifulSoup("<html />", self.test_config.bs4_parser)
        parsable = Parsable(parsed, self.test_config)

        def _parse_deep():
            return json.loads("[" * 100000 + "]" * 100000)

        def _parse_wrong_shape():
            return BeautifulSoup(json.loads("[[]]"), self.test_config.bs4_parser)

        # WHEN / THEN both degrade to None with a warning, like any other parse failure
        with self.assertLogs("amazonorders.entity.parsable", level="WARNING") as logs:
            self.assertIsNone(parsable.safe_parse(_parse_deep))
            self.assertIsNone(parsable.safe_parse(_parse_wrong_shape))
        self.assertEqual(2, len(logs.records))
        self.assertIn("`deep` could not be parsed", logs.output[0])
        self.assertIn("`wrong_shape` could not be parsed", logs.output[1])

    def test_safe_parse_propagates_library_errors(self):
        # GIVEN a required-field parse function that raises the library's own error
        parsed = BeautifulSoup("<html />", self.test_config.bs4_parser)
        parsable = Parsable(parsed, self.test_config)

        def _parse_required():
            raise AmazonOrdersError("required field did not populate")

        # WHEN / THEN safe_parse must not swallow it
        with self.assertRaises(AmazonOrdersError):
            parsable.safe_parse(_parse_required)
    def test_to_dict_excludes_unserializable_fields(self):
        # GIVEN
        with open(os.path.join(self.RESOURCES_DIR, "orders", "order-history-2018-0.html"), "r",
                  encoding="utf-8") as f:
            order = AmazonOrders.parse_order_history(f.read(), self.test_config)[3]

        # WHEN
        serialized = order.to_dict()

        # THEN
        self.assertNotIn("parsed", serialized)
        self.assertNotIn("config", serialized)
        self.assertEqual("112-0399923-3070642", serialized["order_number"])
        self.assertEqual(json.loads(json.dumps(serialized)), serialized)

    def test_to_dict_converts_dates_and_nested_entities(self):
        # GIVEN
        with open(os.path.join(self.RESOURCES_DIR, "orders", "order-history-2018-0.html"), "r",
                  encoding="utf-8") as f:
            order = AmazonOrders.parse_order_history(f.read(), self.test_config)[3]

        # WHEN
        serialized = order.to_dict()

        # THEN
        self.assertEqual("2018-12-21", serialized["order_placed_date"])
        self.assertIsInstance(serialized["recipient"], dict)
        self.assertEqual("Alex Laird", serialized["recipient"]["name"])
        self.assertIsInstance(serialized["items"], list)
        self.assertIsInstance(serialized["items"][0], dict)
        self.assertIsInstance(serialized["shipments"][0]["items"][0]["title"], str)

    def test_to_dict_on_transaction(self):
        # GIVEN
        with open(os.path.join(self.RESOURCES_DIR, "transactions", "get-transactions-snippet.html"), "r",
                  encoding="utf-8") as f:
            transaction = AmazonTransactions.parse_transactions(f.read(), self.test_config)[0]

        # WHEN
        serialized = transaction.to_dict()

        # THEN
        self.assertNotIn("parsed", serialized)
        self.assertNotIn("config", serialized)
        self.assertEqual(json.loads(json.dumps(serialized)), serialized)
        self.assertIsInstance(serialized["completed_date"], str)
