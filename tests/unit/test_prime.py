__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import datetime
import json
import os

import responses
from bs4 import BeautifulSoup

from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.prime_payment import PrimePayment
from amazonorders.exception import AmazonOrdersError, AmazonOrdersAuthRedirectError
from amazonorders.prime import AmazonPrime
from amazonorders.session import AmazonSession
from tests.unittestcase import UnitTestCase


class TestPrime(UnitTestCase):
    def setUp(self):
        super().setUp()

        self.amazon_session = AmazonSession("some-username@gmail.com",
                                            "some-password",
                                            config=self.test_config)

        self.amazon_prime = AmazonPrime(self.amazon_session)

    def _read_resource(self, html_file):
        with open(os.path.join(self.RESOURCES_DIR, "prime", html_file), "r", encoding="utf-8") as f:
            return f.read()

    def _given_prime_payments_page_exists(self, html_file):
        return responses.add(
            responses.GET,
            f"{self.test_config.constants.PRIME_PAYMENTS_URL}",
            body=self._read_resource(html_file),
            status=200,
        )

    def _first_card(self, html):
        parsed = BeautifulSoup(html, self.test_config.bs4_parser)
        return parsed.select(self.test_config.selectors.PRIME_PAYMENT_SELECTOR)[0]

    def test_get_prime_payments_unauthenticated(self):
        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_prime.get_prime_payments()

        self.assertEqual("Call AmazonSession.login() to authenticate first.", str(cm.exception))

    @responses.activate
    def test_get_prime_payments_session_expires(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        auth_redirect_response = self.given_authenticated_url_renders_login()
        signout_response = self.given_logout_response_success()

        # WHEN
        with self.assertRaises(AmazonOrdersAuthRedirectError) as cm:
            self.amazon_prime.get_prime_payments()

        self.assertIn("Amazon redirected to login.", str(cm.exception))
        self.assertFalse(self.amazon_session.is_authenticated)
        self.assertEqual(1, auth_redirect_response.call_count)
        self.assertEqual(1, signout_response.call_count)

    @responses.activate
    def test_get_prime_payments(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        resp = self._given_prime_payments_page_exists("prime-payments.html")

        # WHEN
        payments = self.amazon_prime.get_prime_payments()

        # THEN one card per membership year, newest first as the page lists them
        self.assertEqual(1, resp.call_count)
        self.assertEqual(8, len(payments))
        self.assertEqual([datetime.date(year, 11, 17) for year in range(2025, 2017, -1)],
                         [payment.payment_date for payment in payments])
        self.assertEqual([148.38, 148.38, 148.38, 148.38, 127.03, 128.82, 129.56, 127.78],
                         [payment.total for payment in payments])
        self.assertEqual([f"D01-{1000000 + i:07d}-{2000000 + i:07d}" for i in range(8, 0, -1)],
                         [payment.order_number for payment in payments])

        payment = payments[0]
        self.assertEqual("D01-1000008-2000008", payment.order_number)
        self.assertEqual("https://www.amazon.com/gp/your-account/order-details?orderID=D01-1000008-2000008",
                         payment.order_details_link)
        self.assertEqual("https://www.amazon.com/gp/digital/your-account/order-summary.html/ref=primecentral"
                         "?ie=UTF8&orderID=D01-1000008-2000008&print=1",
                         payment.receipt_link)
        self.assertEqual("<PrimePayment 2025-11-17: \"148.38, Order #: D01-1000008-2000008\">", repr(payment))

    @responses.activate
    def test_get_prime_payments_empty(self):
        # GIVEN the widget renders with no cards
        self.amazon_session.is_authenticated = True
        resp = self._given_prime_payments_page_exists("prime-payments-empty.html")

        # WHEN
        payments = self.amazon_prime.get_prime_payments()

        # THEN
        self.assertEqual(1, resp.call_count)
        self.assertEqual([], payments)

    @responses.activate
    def test_get_prime_payments_challenge_page(self):
        # GIVEN a challenge page served with a 200 (a login redirect is handled by the session instead)
        self.amazon_session.is_authenticated = True
        with open(os.path.join(self.RESOURCES_DIR, "auth", "post-signin-captcha-1.html"), "r", encoding="utf-8") as f:
            resp = responses.add(
                responses.GET,
                f"{self.test_config.constants.PRIME_PAYMENTS_URL}",
                body=f.read(),
                status=200,
            )

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_prime.get_prime_payments()

        # THEN
        self.assertEqual(1, resp.call_count)
        self.assertIn("sign-in or challenge page", str(cm.exception))

    @responses.activate
    def test_get_prime_payments_invalid_page(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        with open(os.path.join(self.RESOURCES_DIR, "500.html"), "r", encoding="utf-8") as f:
            resp = responses.add(
                responses.GET,
                f"{self.test_config.constants.PRIME_PAYMENTS_URL}",
                body=f.read(),
                status=200,
            )

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_prime.get_prime_payments()

        # THEN
        self.assertEqual(1, resp.call_count)
        self.assertIn("Could not parse Prime payments.", str(cm.exception))

    def test_parse_prime_payments_page(self):
        # WHEN
        result = AmazonPrime.parse_prime_payments_page(self._read_resource("prime-payments.html"),
                                                       self.test_config)

        # THEN
        self.assertEqual("payments", result.page_type)
        self.assertEqual(8, len(result.payments))
        self.assertEqual(datetime.date(2018, 11, 17), result.payments[-1].payment_date)
        self.assertEqual(127.78, result.payments[-1].total)
        self.assertEqual("D01-1000001-2000001", result.payments[-1].order_number)
        self.assertEqual("<PrimePaymentsPageResult: \"payments\", 8 payments>", repr(result))

    def test_parse_prime_payments_page_empty(self):
        # WHEN
        result = AmazonPrime.parse_prime_payments_page(self._read_resource("prime-payments-empty.html"),
                                                       self.test_config)

        # THEN the widget with no cards is a member with no payments, not a failure
        self.assertEqual("empty", result.page_type)
        self.assertEqual([], result.payments)

    def test_parse_prime_payments_page_not_prime_payments(self):
        # GIVEN the pages a session-expired or challenged browser fetch supplies instead
        for html_file in ["signin.html", "post-signin-captcha-1.html", "acic-challenge.html", "waf-challenge.html"]:
            with self.subTest(html_file=html_file):
                with open(os.path.join(self.RESOURCES_DIR, "auth", html_file), "r",
                          encoding="utf-8") as f:
                    html = f.read()

                # WHEN
                result = AmazonPrime.parse_prime_payments_page(html, self.test_config)

                # THEN
                self.assertEqual("not_prime_payments", result.page_type)
                self.assertEqual([], result.payments)

    def test_parse_prime_payments_page_unrecognized_page(self):
        # GIVEN a page with neither the widget nor a recognizable challenge: a failed render, which
        # must not report as an empty history
        with open(os.path.join(self.RESOURCES_DIR, "500.html"), "r", encoding="utf-8") as f:
            html = f.read()

        # WHEN / THEN
        with self.assertRaises(AmazonOrdersError) as cm:
            AmazonPrime.parse_prime_payments_page(html, self.test_config)
        self.assertIn("Could not parse Prime payments.", str(cm.exception))

    def test_parse_prime_payments_page_partial_payments_meta(self):
        # GIVEN the third card's total is missing
        html = self._read_resource("prime-payments.html")
        html = html.replace("<p class=\"a-nowrap\">$148.38</p>", "<p class=\"a-nowrap\"></p>", 3) \
            .replace("<p class=\"a-nowrap\"></p>", "<p class=\"a-nowrap\">$148.38</p>", 2)

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            AmazonPrime.parse_prime_payments_page(html, self.test_config)

        # THEN the payments parsed before the failure ride the exception
        self.assertIn("PrimePayment.total did not populate", str(cm.exception))
        self.assertEqual(2, len(cm.exception.meta["partial_payments"]))
        self.assertEqual(["D01-1000008-2000008", "D01-1000007-2000007"],
                         [payment.order_number for payment in cm.exception.meta["partial_payments"]])

    def test_prime_payment_missing_receipt_link(self):
        # GIVEN a card without the "View Receipt" button
        html = self._read_resource("prime-payments.html")
        card_tag = self._first_card(html)
        for link_tag in card_tag.select(self.test_config.selectors.FIELD_PRIME_PAYMENT_RECEIPT_LINK_SELECTOR):
            link_tag.decompose()

        # WHEN
        payment = PrimePayment(card_tag, self.test_config)

        # THEN the card still parses
        self.assertIsNone(payment.receipt_link)
        self.assertEqual("D01-1000008-2000008", payment.order_number)
        self.assertEqual(148.38, payment.total)

    def test_prime_payment_missing_required_fields(self):
        # GIVEN a card whose Order number is not an Order number
        html = self._read_resource("prime-payments.html").replace("D01-1000008-2000008", "pending")
        card_tag = self._first_card(html)

        # WHEN / THEN the Order number is required
        with self.assertRaises(AmazonOrdersError) as cm:
            PrimePayment(card_tag, self.test_config)
        self.assertIn("PrimePayment.order_number did not populate", str(cm.exception))

        # WHEN warn_on_missing_required_field is set it degrades to None
        config = AmazonOrdersConfig(data={"output_dir": self.test_output_dir,
                                          "cookie_jar_path": self.test_cookie_jar_path,
                                          "warn_on_missing_required_field": True})
        payment = PrimePayment(card_tag, config)

        # THEN
        self.assertIsNone(payment.order_number)
        self.assertIsNone(payment.order_details_link)
        self.assertEqual(148.38, payment.total)
        self.assertEqual(datetime.date(2025, 11, 17), payment.payment_date)

    def test_prime_payment_labels_not_positional(self):
        # GIVEN the card's rows in a different order, with an extra row
        card_html = """
        <div class="a-cardui" data-a-card-type="basic">
          <div class="a-cardui-header"><h3 class="a-size-base">March 3, 2026</h3></div>
          <div class="a-cardui-body"><ul class="a-unordered-list a-nostyle a-vertical">
            <li><span class="a-list-item"><div class="a-section">
              <span class="a-color-tertiary">Order Number</span>
              <p class="a-nowrap">D01-1234567-7654321</p></div></span></li>
            <li><span class="a-list-item"><div class="a-section">
              <span class="a-color-tertiary">Subtotal</span><p class="a-nowrap">$14.99</p></div></span></li>
            <li><span class="a-list-item"><div class="a-section">
              <span class="a-color-tertiary">Total</span><p class="a-nowrap">$15.94</p></div></span></li>
          </ul></div>
        </div>
        """
        card_tag = BeautifulSoup(card_html, self.test_config.bs4_parser).select("div.a-cardui")[0]

        # WHEN
        payment = PrimePayment(card_tag, self.test_config)

        # THEN each field is read by its label
        self.assertEqual(datetime.date(2026, 3, 3), payment.payment_date)
        self.assertEqual(15.94, payment.total)
        self.assertEqual("D01-1234567-7654321", payment.order_number)
        self.assertIsNone(payment.receipt_link)

    def test_prime_payment_to_dict(self):
        # GIVEN
        payment = PrimePayment(self._first_card(self._read_resource("prime-payments.html")), self.test_config)

        # WHEN
        serialized = payment.to_dict()

        # THEN the card tag and config are omitted and the rest are primitives
        self.assertNotIn("parsed", serialized)
        self.assertNotIn("config", serialized)
        self.assertEqual("2025-11-17", serialized["payment_date"])
        self.assertEqual(148.38, serialized["total"])
        self.assertEqual("D01-1000008-2000008", serialized["order_number"])
        self.assertEqual(json.loads(json.dumps(serialized)), serialized)
