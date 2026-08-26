__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import datetime
import os
from unittest.mock import patch

import responses
from bs4 import BeautifulSoup

from amazonorders.entity.gift_card_activity import GiftCardActivity
from amazonorders.exception import AmazonOrdersError, AmazonOrdersAuthRedirectError
from amazonorders.gift_cards import AmazonGiftCards, _parse_gift_card_activity_page
from amazonorders.session import AmazonSession
from tests.unittestcase import UnitTestCase


class TestGiftCards(UnitTestCase):
    def setUp(self):
        super().setUp()

        self.amazon_session = AmazonSession("some-username@gmail.com",
                                            "some-password",
                                            config=self.test_config)

        self.amazon_gift_cards = AmazonGiftCards(self.amazon_session)

    def _given_gift_card_page_exists(self, html_file):
        with open(os.path.join(self.RESOURCES_DIR, "giftcards", html_file), "r",
                  encoding="utf-8") as f:
            return responses.add(
                responses.GET,
                f"{self.test_config.constants.GIFT_CARD_BALANCE_URL}",
                body=f.read(),
                status=200,
            )

    def test_get_balance_unauthenticated(self):
        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_gift_cards.get_balance()

        self.assertEqual("Call AmazonSession.login() to authenticate first.", str(cm.exception))

    def test_get_gift_card_activity_unauthenticated(self):
        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_gift_cards.get_gift_card_activity()

        self.assertEqual("Call AmazonSession.login() to authenticate first.", str(cm.exception))

    @responses.activate
    def test_get_balance_session_expires(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        auth_redirect_response = self.given_authenticated_url_renders_login()
        signout_response = self.given_logout_response_success()

        # WHEN
        with self.assertRaises(AmazonOrdersAuthRedirectError) as cm:
            self.amazon_gift_cards.get_balance()

        self.assertIn("Amazon redirected to login.", str(cm.exception))
        self.assertFalse(self.amazon_session.is_authenticated)
        self.assertEqual(1, auth_redirect_response.call_count)
        self.assertEqual(1, signout_response.call_count)

    @responses.activate
    def test_get_balance(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        resp = self._given_gift_card_page_exists("gift-card-balance-activity.html")

        # WHEN
        balance = self.amazon_gift_cards.get_balance()

        # THEN
        self.assertEqual(0.00, balance)
        self.assertEqual(1, resp.call_count)

    @responses.activate
    def test_get_balance_invalid_page(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        with open(os.path.join(self.RESOURCES_DIR, "500.html"), "r", encoding="utf-8") as f:
            resp = responses.add(
                responses.GET,
                f"{self.test_config.constants.GIFT_CARD_BALANCE_URL}",
                body=f.read(),
                status=200,
            )

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_gift_cards.get_balance()

        # THEN
        self.assertEqual(1, resp.call_count)
        self.assertIn("Could not parse Gift Card balance.", str(cm.exception))

    @responses.activate
    @patch("amazonorders.gift_cards.datetime", wraps=datetime)
    def test_get_gift_card_activity(self, mock_today):
        # GIVEN
        mock_today.date.today.return_value = datetime.date(2026, 5, 15)
        self.amazon_session.is_authenticated = True
        resp = self._given_gift_card_page_exists("gift-card-balance-activity.html")

        # WHEN
        activity = self.amazon_gift_cards.get_gift_card_activity(keep_paging=False)

        # THEN
        self.assertEqual(15, len(activity))
        pull = self.amazon_gift_cards.last_activity_pull
        self.assertEqual(1, pull.pages_walked)
        self.assertEqual(15, pull.rows_parsed)
        self.assertEqual("single_page_requested", pull.stop_reason)
        entry = activity[0]
        self.assertEqual(entry.activity_date, datetime.date(2026, 5, 12))
        self.assertEqual(entry.description, "Gift Card applied to Amazon.com order")
        self.assertEqual(entry.amount, -19.48)
        self.assertFalse(entry.is_credit)
        self.assertEqual(entry.closing_balance, 0.00)
        self.assertEqual(entry.order_number, "111-5500901-2478601")
        self.assertEqual(entry.order_details_link,
                         "https://www.amazon.com/gp/your-account/order-details/ref=gcf_b_bp_lpo_c_d_b_x"
                         "?ie=UTF8&orderID=111-5500901-2478601")
        entry = activity[1]
        self.assertEqual(entry.activity_date, datetime.date(2026, 5, 11))
        self.assertEqual(entry.description, "Gift Card Balance added from Reload")
        self.assertEqual(entry.amount, 19.48)
        self.assertTrue(entry.is_credit)
        self.assertEqual(entry.closing_balance, 19.48)
        self.assertEqual(entry.order_number, "111-5500902-2478602")
        entry = activity[3]
        self.assertEqual(entry.description, "Refund from Amazon.com order")
        self.assertEqual(entry.amount, 14.55)
        self.assertTrue(entry.is_credit)
        self.assertEqual(1, resp.call_count)

    @responses.activate
    @patch("amazonorders.gift_cards.datetime", wraps=datetime)
    def test_get_gift_card_activity_paginated(self, mock_today):
        # GIVEN
        mock_today.date.today.return_value = datetime.date(2026, 5, 15)
        self.amazon_session.is_authenticated = True
        resp1 = self._given_gift_card_page_exists("gift-card-balance-activity.html")
        resp2 = self._given_gift_card_page_exists("gift-card-balance-activity-page-2.html")
        resp3 = self._given_gift_card_page_exists("gift-card-balance-activity-last-page.html")

        # WHEN
        activity = self.amazon_gift_cards.get_gift_card_activity(days=4000)

        # THEN
        self.assertEqual(41, len(activity))
        self.assertEqual(1, resp1.call_count)
        self.assertEqual(1, resp2.call_count)
        self.assertEqual(1, resp3.call_count)
        self.assertIn("next=", resp2.calls[0].request.url)
        self.assertIn("next=", resp3.calls[0].request.url)
        pull = self.amazon_gift_cards.last_activity_pull
        self.assertEqual(3, pull.pages_walked)
        self.assertEqual(41, pull.rows_parsed)
        self.assertEqual("no_more_pages", pull.stop_reason)

    @responses.activate
    @patch("amazonorders.gift_cards.datetime", wraps=datetime)
    def test_get_gift_card_activity_redemption_and_linkless_rows(self, mock_today):
        # GIVEN
        mock_today.date.today.return_value = datetime.date(2026, 5, 15)
        self.amazon_session.is_authenticated = True
        resp = self._given_gift_card_page_exists("gift-card-balance-activity-page-2.html")

        # WHEN
        activity = self.amazon_gift_cards.get_gift_card_activity(days=600, keep_paging=False)

        # THEN a claim code redemption row has no Order reference
        self.assertEqual(15, len(activity))
        entry = activity[0]
        self.assertEqual(entry.activity_date, datetime.date(2025, 7, 14))
        self.assertEqual(entry.description, "Gift Card added")
        self.assertEqual(entry.amount, 13.70)
        self.assertTrue(entry.is_credit)
        self.assertEqual(entry.closing_balance, 212.53)
        self.assertIsNone(entry.order_number)
        self.assertIsNone(entry.order_details_link)
        # THEN a refund row rendered without an Order link also has no Order reference
        entry = activity[8]
        self.assertEqual(entry.description, "Refund from Amazon.com order")
        self.assertTrue(entry.is_credit)
        self.assertIsNone(entry.order_number)
        self.assertIsNone(entry.order_details_link)
        self.assertEqual(1, resp.call_count)

    @responses.activate
    @patch("amazonorders.gift_cards.datetime", wraps=datetime)
    def test_get_gift_card_activity_days_filter(self, mock_today):
        # GIVEN
        mock_today.date.today.return_value = datetime.date(2026, 5, 12)
        self.amazon_session.is_authenticated = True
        resp = self._given_gift_card_page_exists("gift-card-balance-activity.html")

        # WHEN
        activity = self.amazon_gift_cards.get_gift_card_activity(days=5)

        # THEN entries older than the window stop paging, even with a next page present
        self.assertEqual(2, len(activity))
        self.assertEqual(activity[0].activity_date, datetime.date(2026, 5, 12))
        self.assertEqual(activity[1].activity_date, datetime.date(2026, 5, 11))
        self.assertEqual(1, resp.call_count)
        pull = self.amazon_gift_cards.last_activity_pull
        self.assertEqual(1, pull.pages_walked)
        self.assertEqual(2, pull.rows_parsed)
        self.assertEqual("window_exceeded", pull.stop_reason)

    @responses.activate
    def test_get_gift_card_activity_zero_activity(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        resp = self._given_gift_card_page_exists("gift-card-balance-zero-activity.html")

        # WHEN
        activity = self.amazon_gift_cards.get_gift_card_activity(keep_paging=False)

        # THEN
        self.assertEqual(0, len(activity))
        self.assertEqual(1, resp.call_count)
        pull = self.amazon_gift_cards.last_activity_pull
        self.assertEqual(1, pull.pages_walked)
        self.assertEqual(0, pull.rows_parsed)
        self.assertEqual("no_activity_table", pull.stop_reason)

    @responses.activate
    def test_get_gift_card_activity_invalid_page(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        with open(os.path.join(self.RESOURCES_DIR, "500.html"), "r", encoding="utf-8") as f:
            resp = responses.add(
                responses.GET,
                f"{self.test_config.constants.GIFT_CARD_BALANCE_URL}",
                body=f.read(),
                status=200,
            )

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_gift_cards.get_gift_card_activity(keep_paging=False)

        # THEN
        self.assertEqual(1, resp.call_count)
        self.assertIn("Could not parse Gift Card activity.", str(cm.exception))

    @responses.activate
    def test_get_gift_card_activity_errors_with_meta(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        resp = responses.add(
            responses.GET,
            f"{self.test_config.constants.GIFT_CARD_BALANCE_URL}",
            status=503,
        )

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_gift_cards.get_gift_card_activity(keep_paging=False)

        # THEN
        self.assertEqual(1, resp.call_count)
        self.assertEqual(cm.exception.meta,
                         {"next_page_url": self.test_config.constants.GIFT_CARD_BALANCE_URL,
                          "partial_activity": []})
        self.assertIsNone(self.amazon_gift_cards.last_activity_pull)

    @responses.activate
    @patch("amazonorders.gift_cards.datetime", wraps=datetime)
    def test_get_gift_card_activity_mid_pagination_failure_partial_results(self, mock_today):
        # GIVEN
        mock_today.date.today.return_value = datetime.date(2026, 5, 15)
        self.amazon_session.is_authenticated = True
        resp1 = self._given_gift_card_page_exists("gift-card-balance-activity.html")
        resp2 = responses.add(
            responses.GET,
            f"{self.test_config.constants.GIFT_CARD_BALANCE_URL}",
            status=503,
        )

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_gift_cards.get_gift_card_activity(days=4000)

        # THEN the rows fetched before the failure are recoverable alongside the resume URL
        self.assertEqual(1, resp1.call_count)
        self.assertEqual(1, resp2.call_count)
        partial = cm.exception.meta["partial_activity"]
        self.assertEqual(15, len(partial))
        self.assertEqual(partial[0].activity_date, datetime.date(2026, 5, 12))
        self.assertIn("next=", cm.exception.meta["next_page_url"])
        self.assertIsNone(self.amazon_gift_cards.last_activity_pull)

    def test_gift_card_activity_anchorless_debit_row(self):
        # GIVEN a debit row rendered with no Order anchor, as observed in production on
        # small-amount (likely digital) orders
        row_html = """
        <tr>
            <td> April 9, 2026 </td>
            <td>
                <span>Gift Card applied to Amazon.com order</span>
            </td>
            <td>
-$2.12
            </td>
            <td>
$85.46
            </td>
        </tr>
        """
        parsed = BeautifulSoup(row_html, self.test_config.bs4_parser)
        row_tag = parsed.select_one("tr")

        # WHEN
        entry = GiftCardActivity(row_tag, self.test_config)

        # THEN the missing anchor yields no Order reference, not a parse failure
        self.assertEqual(entry.activity_date, datetime.date(2026, 4, 9))
        self.assertEqual(entry.description, "Gift Card applied to Amazon.com order")
        self.assertEqual(entry.amount, -2.12)
        self.assertFalse(entry.is_credit)
        self.assertEqual(entry.closing_balance, 85.46)
        self.assertIsNone(entry.order_number)
        self.assertIsNone(entry.order_details_link)

    def test_parse_gift_card_activity_page(self):
        # GIVEN
        with open(os.path.join(self.RESOURCES_DIR, "giftcards", "gift-card-balance-activity.html"), "r",
                  encoding="utf-8") as f:
            parsed = BeautifulSoup(f.read(), self.test_config.bs4_parser)

        # WHEN
        found_table, activity, next_page_url = _parse_gift_card_activity_page(
            parsed, self.test_config
        )

        # THEN
        self.assertTrue(found_table)
        self.assertEqual(len(activity), 15)
        self.assertTrue(next_page_url.startswith(
            f"{self.test_config.constants.BASE_URL}/gc/balance?ref_="))
        self.assertIn("next=", next_page_url)

    def test_parse_gift_card_activity_page_last_page(self):
        # GIVEN
        with open(os.path.join(self.RESOURCES_DIR, "giftcards", "gift-card-balance-activity-last-page.html"), "r",
                  encoding="utf-8") as f:
            parsed = BeautifulSoup(f.read(), self.test_config.bs4_parser)

        # WHEN
        found_table, activity, next_page_url = _parse_gift_card_activity_page(
            parsed, self.test_config
        )

        # THEN
        self.assertTrue(found_table)
        self.assertEqual(len(activity), 11)
        self.assertIsNone(next_page_url)
