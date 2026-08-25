__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import datetime
import os
from unittest.mock import patch

import responses
from bs4 import BeautifulSoup

from amazonorders.exception import AmazonOrdersError, AmazonOrdersAuthRedirectError
from amazonorders.gift_cards import AmazonGiftCards, _parse_gift_card_activity_form_tag
from amazonorders.session import AmazonSession
from tests.unittestcase import UnitTestCase

# Synthetic markup matching the provisional Gift Card selectors. Replace with sanitized
# /gc/balance captures (and update the selectors) once fixtures are available.
GIFT_CARD_BALANCE_SNIPPET = """
<div id="gc-current-balance">$42.17</div>
"""

GIFT_CARD_ACTIVITY_FORM_SNIPPET = """
<form>
    <input name="ppw-widgetState" value="the-ppw-widgetState"/>
    <input name="ie" value="UTF-8"/>
    <div class="apx-transaction-date-container">
        <span>October 11, 2024</span>
    </div>
    <div>
        <div class="apx-transactions-line-item-component-container">
            <div class="a-row">
                <span class="a-size-base">Used to pay for an Amazon order</span>
                <span class="a-size-base-plus">-$12.50</span>
            </div>
            <div class="a-row">
                <a class="a-link-normal" href="/gp/your-account/order-details?orderID=111-2266921-0923465">
                    <span class="a-span12">Order #111-2266921-0923465</span>
                </a>
            </div>
        </div>
    </div>
    <div class="apx-transaction-date-container">
        <span>October 1, 2024</span>
    </div>
    <div>
        <div class="apx-transactions-line-item-component-container">
            <div class="a-row">
                <span class="a-size-base">Gift card redeemed</span>
                <span class="a-size-base-plus">$25.00</span>
            </div>
        </div>
    </div>
</form>
"""

GIFT_CARD_ACTIVITY_FORM_WITH_NEXT_PAGE_SNIPPET = GIFT_CARD_ACTIVITY_FORM_SNIPPET.replace(
    "</form>",
    """<input type="submit"
              name='ppw-widgetEvent:DefaultNextPageNavigationEvent:{"nextPageKey":"key"}'/>
</form>""")


class TestGiftCards(UnitTestCase):
    def setUp(self):
        super().setUp()

        self.amazon_session = AmazonSession("some-username@gmail.com",
                                            "some-password",
                                            config=self.test_config)

        self.amazon_gift_cards = AmazonGiftCards(self.amazon_session)

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
        resp = responses.add(
            responses.GET,
            f"{self.test_config.constants.GIFT_CARD_BALANCE_URL}",
            body=GIFT_CARD_BALANCE_SNIPPET,
            status=200,
        )

        # WHEN
        balance = self.amazon_gift_cards.get_balance()

        # THEN
        self.assertEqual(42.17, balance)
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
        mock_today.date.today.return_value = datetime.date(2024, 10, 11)
        self.amazon_session.is_authenticated = True
        resp = responses.add(
            responses.GET,
            f"{self.test_config.constants.GIFT_CARD_BALANCE_URL}",
            body=GIFT_CARD_ACTIVITY_FORM_SNIPPET,
            status=200,
        )

        # WHEN
        activity = self.amazon_gift_cards.get_gift_card_activity(days=30, keep_paging=False)

        # THEN
        self.assertEqual(2, len(activity))
        entry = activity[0]
        self.assertEqual(entry.activity_date, datetime.date(2024, 10, 11))
        self.assertEqual(entry.description, "Used to pay for an Amazon order")
        self.assertEqual(entry.amount, -12.50)
        self.assertFalse(entry.is_credit)
        self.assertEqual(entry.order_number, "111-2266921-0923465")
        self.assertEqual(entry.order_details_link,
                         "https://www.amazon.com/gp/your-account/order-details?orderID=111-2266921-0923465")
        entry = activity[1]
        self.assertEqual(entry.activity_date, datetime.date(2024, 10, 1))
        self.assertEqual(entry.description, "Gift card redeemed")
        self.assertEqual(entry.amount, 25.00)
        self.assertTrue(entry.is_credit)
        self.assertIsNone(entry.order_number)
        self.assertIsNone(entry.order_details_link)
        self.assertEqual(1, resp.call_count)

    @responses.activate
    @patch("amazonorders.gift_cards.datetime", wraps=datetime)
    def test_get_gift_card_activity_days_filter(self, mock_today):
        # GIVEN
        mock_today.date.today.return_value = datetime.date(2024, 10, 11)
        self.amazon_session.is_authenticated = True
        resp = responses.add(
            responses.GET,
            f"{self.test_config.constants.GIFT_CARD_BALANCE_URL}",
            body=GIFT_CARD_ACTIVITY_FORM_WITH_NEXT_PAGE_SNIPPET,
            status=200,
        )

        # WHEN
        activity = self.amazon_gift_cards.get_gift_card_activity(days=5)

        # THEN entries older than the window stop paging, even with a next page present
        self.assertEqual(1, len(activity))
        self.assertEqual(activity[0].activity_date, datetime.date(2024, 10, 11))
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
            responses.POST,
            f"{self.test_config.constants.GIFT_CARD_BALANCE_URL}",
            status=503,
        )
        next_page_data = {"some": "meta"}

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_gift_cards.get_gift_card_activity(next_page_data=next_page_data, keep_paging=False)

        # THEN
        self.assertEqual(1, resp.call_count)
        self.assertEqual(cm.exception.meta, next_page_data)

    def test_parse_gift_card_activity_form_tag(self):
        # GIVEN
        parsed = BeautifulSoup(GIFT_CARD_ACTIVITY_FORM_WITH_NEXT_PAGE_SNIPPET, self.test_config.bs4_parser)
        form_tag = parsed.select_one("form")

        # WHEN
        activity, next_page_data = _parse_gift_card_activity_form_tag(
            form_tag, self.test_config
        )

        # THEN
        self.assertEqual(len(activity), 2)
        self.assertEqual(
            next_page_data,
            {
                "ppw-widgetState": "the-ppw-widgetState",
                "ie": "UTF-8",
                'ppw-widgetEvent:DefaultNextPageNavigationEvent:{"nextPageKey":"key"}': "",
            },
        )
