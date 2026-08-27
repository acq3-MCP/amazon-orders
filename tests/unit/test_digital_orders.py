__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import datetime
import os

import responses

from amazonorders.digital_orders import AmazonDigitalOrders
from amazonorders.exception import AmazonOrdersError
from amazonorders.orders import AmazonOrders
from amazonorders.session import AmazonSession
from tests.unittestcase import UnitTestCase


class TestDigitalOrders(UnitTestCase):
    def setUp(self):
        super().setUp()

        self.amazon_session = AmazonSession("some-username@gmail.com",
                                            "some-password",
                                            config=self.test_config)

        self.amazon_digital_orders = AmazonDigitalOrders(self.amazon_session)

    def _given_digital_history_page_exists(self, html_file):
        with open(os.path.join(self.RESOURCES_DIR, "digitalorders", html_file), "r",
                  encoding="utf-8") as f:
            return responses.add(
                responses.GET,
                f"{self.test_config.constants.ORDER_HISTORY_URL}",
                body=f.read(),
                status=200,
            )

    def test_get_digital_orders_unauthenticated(self):
        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_digital_orders.get_digital_orders()

        self.assertEqual("Call AmazonSession.login() to authenticate first.", str(cm.exception))

    def test_get_all_digital_orders_unauthenticated(self):
        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_digital_orders.get_all_digital_orders()

        self.assertEqual("Call AmazonSession.login() to authenticate first.", str(cm.exception))

    @responses.activate
    def test_get_digital_orders(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        resp = self._given_digital_history_page_exists("digital-order-history-2026-0.html")

        # WHEN
        orders = self.amazon_digital_orders.get_digital_orders(year=2026)

        # THEN
        self.assertEqual(1, len(orders))
        order = orders[0]
        self.assertEqual("D01-1000111-2000222", order.order_number)
        self.assertEqual(datetime.date(2026, 4, 9), order.order_placed_date)
        self.assertEqual(2.90, order.grand_total)
        self.assertEqual(1, len(order.items))
        self.assertEqual("Digital Item 01", order.items[0].title)
        self.assertIn("orderID=D01-1000111-2000222", order.order_details_link)
        self.assertEqual(1, resp.call_count)
        self.assertIn("orderFilter=digital", resp.calls[0].request.url)
        self.assertIn("timeFilter=year-2026", resp.calls[0].request.url)
        pull = self.amazon_digital_orders.last_digital_pull
        self.assertEqual(1, len(pull.windows))
        self.assertEqual("year-2026", pull.windows[0].window)
        self.assertEqual(1, pull.windows[0].pages_walked)
        self.assertEqual(1, pull.windows[0].rows_parsed)
        self.assertEqual(1, pull.windows[0].header_count)
        self.assertEqual("no_more_pages", pull.stop_reason)

    @responses.activate
    def test_get_digital_orders_multi_page(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        resp1 = self._given_digital_history_page_exists("digital-order-history-2024-0.html")
        resp2 = self._given_digital_history_page_exists("digital-order-history-2024-10.html")
        resp3 = self._given_digital_history_page_exists("digital-order-history-2024-20.html")

        # WHEN
        orders = self.amazon_digital_orders.get_digital_orders(time_filter="year-2024")

        # THEN
        self.assertEqual(29, len(orders))
        self.assertEqual(1, resp1.call_count)
        self.assertEqual(1, resp2.call_count)
        self.assertEqual(1, resp3.call_count)
        pull = self.amazon_digital_orders.last_digital_pull
        self.assertEqual("year-2024", pull.windows[0].window)
        self.assertEqual(3, pull.windows[0].pages_walked)
        self.assertEqual(29, pull.windows[0].rows_parsed)
        # The page's own header count matching rows parsed is the parse-completeness invariant
        self.assertEqual(29, pull.windows[0].header_count)
        self.assertEqual("no_more_pages", pull.stop_reason)

    @responses.activate
    def test_get_digital_orders_empty_year(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        resp = self._given_digital_history_page_exists("digital-order-history-2005-0.html")

        # WHEN
        orders = self.amazon_digital_orders.get_digital_orders(year=2005)

        # THEN
        self.assertEqual(0, len(orders))
        self.assertEqual(1, resp.call_count)
        pull = self.amazon_digital_orders.last_digital_pull
        self.assertEqual(1, pull.windows[0].pages_walked)
        self.assertEqual(0, pull.windows[0].rows_parsed)
        self.assertEqual(0, pull.windows[0].header_count)
        self.assertEqual("empty_history", pull.stop_reason)

    @responses.activate
    def test_get_all_digital_orders(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        self._given_digital_history_page_exists("digital-order-history-default-window.html")
        self._given_digital_history_page_exists("digital-order-history-2026-0.html")
        # year-2025 serves an empty year, then 2024's three pages, then 19 more empty years
        self._given_digital_history_page_exists("digital-order-history-2005-0.html")
        self._given_digital_history_page_exists("digital-order-history-2024-0.html")
        self._given_digital_history_page_exists("digital-order-history-2024-10.html")
        self._given_digital_history_page_exists("digital-order-history-2024-20.html")
        for _ in range(19):
            self._given_digital_history_page_exists("digital-order-history-2005-0.html")

        # WHEN
        orders = self.amazon_digital_orders.get_all_digital_orders()

        # THEN the dropdown's 22 year windows are walked, newest first
        self.assertEqual(30, len(orders))
        self.assertEqual("D01-1000111-2000222", orders[0].order_number)
        pull = self.amazon_digital_orders.last_digital_pull
        self.assertEqual(22, len(pull.windows))
        self.assertEqual("year-2026", pull.windows[0].window)
        self.assertEqual("year-2005", pull.windows[-1].window)
        window_2024 = next(w for w in pull.windows if w.window == "year-2024")
        self.assertEqual(3, window_2024.pages_walked)
        self.assertEqual(29, window_2024.rows_parsed)
        self.assertEqual(29, window_2024.header_count)
        self.assertEqual("all_windows_walked", pull.stop_reason)

    @responses.activate
    def test_get_all_digital_orders_mid_walk_failure_partial_results(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        self._given_digital_history_page_exists("digital-order-history-default-window.html")
        self._given_digital_history_page_exists("digital-order-history-2026-0.html")
        responses.add(
            responses.GET,
            f"{self.test_config.constants.ORDER_HISTORY_URL}",
            status=503,
        )

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_digital_orders.get_all_digital_orders()

        # THEN the completed windows' Orders are recoverable, and the failed window is named
        self.assertEqual(1, len(cm.exception.meta["partial_orders"]))
        self.assertEqual("year-2025", cm.exception.meta["window"])
        self.assertIsNone(self.amazon_digital_orders.last_digital_pull)

    @responses.activate
    def test_get_digital_orders_full_details(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        history_resp = self._given_digital_history_page_exists("digital-order-history-2026-0.html")
        with open(os.path.join(self.RESOURCES_DIR, "digitalorders",
                               "digital-order-details-D01-1000111-2000222.html"), "r",
                  encoding="utf-8") as f:
            details_resp = responses.add(
                responses.GET,
                f"{self.test_config.constants.ORDER_DETAILS_URL}",
                body=f.read(),
                status=200,
            )

        # WHEN
        orders = self.amazon_digital_orders.get_digital_orders(year=2026, full_details=True)

        # THEN the details page populates the payment breakdown, including the gift card amount
        self.assertEqual(1, len(orders))
        order = orders[0]
        self.assertEqual("D01-1000111-2000222", order.order_number)
        self.assertEqual(datetime.date(2026, 4, 9), order.order_placed_date)
        # Clone semantics: the history card's grand_total (the pre-gift-card order total) wins;
        # the details page's post-gift-card "Total for this Order" is what get_order() alone returns
        self.assertEqual(2.90, order.grand_total)
        self.assertEqual(2.73, order.subtotal)
        self.assertEqual(2.73, order.total_before_tax)
        self.assertEqual(0.18, order.estimated_tax)
        self.assertEqual(-2.90, order.gift_card)
        self.assertEqual("Amazon Visa", order.payment_method)
        self.assertEqual(1111, order.payment_method_last_4)
        self.assertEqual("Digital Item 01", order.items[0].title)
        self.assertEqual(1, history_resp.call_count)
        self.assertEqual(1, details_resp.call_count)

    @responses.activate
    def test_get_order_digital_details(self):
        # GIVEN a free/promotional digital order rendered with no payment section
        self.amazon_session.is_authenticated = True
        amazon_orders = AmazonOrders(self.amazon_session)
        with open(os.path.join(self.RESOURCES_DIR, "digitalorders",
                               "digital-order-details-D01-1003552-2007104.html"), "r",
                  encoding="utf-8") as f:
            resp = responses.add(
                responses.GET,
                f"{self.test_config.constants.ORDER_DETAILS_URL}",
                body=f.read(),
                status=200,
            )

        # WHEN
        order = amazon_orders.get_order("D01-1003552-2007104")

        # THEN
        self.assertEqual("D01-1003552-2007104", order.order_number)
        self.assertEqual(0.0, order.grand_total)
        self.assertEqual("Digital Item 27", order.items[0].title)
        self.assertIsNone(order.payment_method)
        self.assertIsNone(order.gift_card)
        self.assertEqual(1, resp.call_count)

    @responses.activate
    def test_get_all_digital_orders_no_time_filters(self):
        # GIVEN a page that renders without the time filter dropdown
        self.amazon_session.is_authenticated = True
        with open(os.path.join(self.RESOURCES_DIR, "500.html"), "r", encoding="utf-8") as f:
            resp = responses.add(
                responses.GET,
                f"{self.test_config.constants.ORDER_HISTORY_URL}",
                body=f.read(),
                status=200,
            )

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_digital_orders.get_all_digital_orders()

        # THEN
        self.assertEqual(1, resp.call_count)
        self.assertIn("Could not parse the Digital Orders time filters.", str(cm.exception))
