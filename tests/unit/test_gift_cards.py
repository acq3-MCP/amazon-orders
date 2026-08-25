__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import datetime
import os
from unittest.mock import patch

import responses
from bs4 import BeautifulSoup

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
        resp2 = self._given_gift_card_page_exists("gift-card-balance-activity-last-page.html")

        # WHEN
        activity = self.amazon_gift_cards.get_gift_card_activity()

        # THEN
        self.assertEqual(30, len(activity))
        self.assertEqual(1, resp1.call_count)
        self.assertEqual(1, resp2.call_count)
        self.assertIn("next=", resp2.calls[0].request.url)

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
                         {"next_page_url": self.test_config.constants.GIFT_CARD_BALANCE_URL})

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
        self.assertEqual(len(activity), 15)
        self.assertIsNone(next_page_url)
