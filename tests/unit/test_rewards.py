__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import json
import os

import responses
from bs4 import BeautifulSoup

from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.rewards_balance import RewardsBalance
from amazonorders.exception import AmazonOrdersError, AmazonOrdersAuthRedirectError, AmazonOrdersNotFoundError
from amazonorders.rewards import AmazonRewards, _parse_card_infos
from amazonorders.session import AmazonSession
from tests.unittestcase import UnitTestCase


class TestRewards(UnitTestCase):
    def setUp(self):
        super().setUp()

        self.amazon_session = AmazonSession("some-username@gmail.com",
                                            "some-password",
                                            config=self.test_config)

        self.amazon_rewards = AmazonRewards(self.amazon_session)

    def _given_rewards_page_exists(self, html_file):
        with open(os.path.join(self.RESOURCES_DIR, "rewards", html_file), "r",
                  encoding="utf-8") as f:
            return responses.add(
                responses.GET,
                f"{self.test_config.constants.REWARDS_CARD_URL}",
                body=f.read(),
                status=200,
            )

    def test_get_rewards_balance_unauthenticated(self):
        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_rewards.get_rewards_balance()

        self.assertEqual("Call AmazonSession.login() to authenticate first.", str(cm.exception))

    @responses.activate
    def test_get_rewards_balance_session_expires(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        auth_redirect_response = self.given_authenticated_url_renders_login()
        signout_response = self.given_logout_response_success()

        # WHEN
        with self.assertRaises(AmazonOrdersAuthRedirectError) as cm:
            self.amazon_rewards.get_rewards_balance()

        self.assertIn("Amazon redirected to login.", str(cm.exception))
        self.assertFalse(self.amazon_session.is_authenticated)
        self.assertEqual(1, auth_redirect_response.call_count)
        self.assertEqual(1, signout_response.call_count)

    @responses.activate
    def test_get_rewards_balance(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        resp = self._given_rewards_page_exists("rewards-card-member.html")

        # WHEN
        rewards = self.amazon_rewards.get_rewards_balance()

        # THEN
        self.assertEqual(1, resp.call_count)
        self.assertEqual(123.45, rewards.balance)
        self.assertEqual("USD", rewards.currency)
        self.assertEqual(12345, rewards.points)
        self.assertEqual("WPTS", rewards.points_unit)
        self.assertEqual(0.01, rewards.conversion_rate)
        self.assertIsNone(rewards.last_update_time)
        self.assertEqual("Prime Visa", rewards.card_name)
        self.assertEqual("1234", rewards.card_last_four)
        self.assertEqual("Visa", rewards.brand)
        self.assertEqual("AmazonVisaSignature", rewards.cobrand)
        self.assertEqual("prime", rewards.card_variant)
        self.assertTrue(rewards.enrolled_with_shop_with_points)
        self.assertEqual("<RewardsBalance Prime Visa 1234: \"123.45, Points: 12345\">", repr(rewards))
        # Identifiers from the page data are not carried on the entity
        self.assertFalse(any("token" in k or "cardId" in k or "cpid" in k for k in vars(rewards)))

    @responses.activate
    def test_get_rewards_balances_two_cards(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        resp = self._given_rewards_page_exists("rewards-card-member-two-cards.html")

        # WHEN
        balances = self.amazon_rewards.get_rewards_balances()

        # THEN page order is preserved
        self.assertEqual(1, resp.call_count)
        self.assertEqual(["1234", "5678"], [b.card_last_four for b in balances])
        self.assertEqual("Amazon Visa", balances[1].card_name)
        self.assertEqual(8.0, balances[1].balance)
        self.assertEqual(800, balances[1].points)
        self.assertEqual("2026-09-06T14:03:11Z", balances[1].last_update_time)
        self.assertFalse(balances[1].enrolled_with_shop_with_points)

    @responses.activate
    def test_get_rewards_balance_selects_card(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        self._given_rewards_page_exists("rewards-card-member-two-cards.html")
        self._given_rewards_page_exists("rewards-card-member-two-cards.html")
        self._given_rewards_page_exists("rewards-card-member-two-cards.html")

        # WHEN / THEN the first card is the default, and card_last_four selects
        self.assertEqual("1234", self.amazon_rewards.get_rewards_balance().card_last_four)
        self.assertEqual("5678", self.amazon_rewards.get_rewards_balance(card_last_four="5678").card_last_four)
        with self.assertRaises(AmazonOrdersNotFoundError) as cm:
            self.amazon_rewards.get_rewards_balance(card_last_four="0000")
        self.assertIn("ending in 0000", str(cm.exception))

    @responses.activate
    def test_get_rewards_balance_no_card(self):
        # GIVEN the page data carries an empty card list
        self.amazon_session.is_authenticated = True
        resp = self._given_rewards_page_exists("rewards-card-member-no-card.html")

        # WHEN
        self.assertEqual([], self.amazon_rewards.get_rewards_balances())
        with self.assertRaises(AmazonOrdersNotFoundError) as cm:
            self.amazon_rewards.get_rewards_balance()

        # THEN
        self.assertEqual(2, resp.call_count)
        self.assertEqual("No Amazon rewards card on this account.", str(cm.exception))

    @responses.activate
    def test_get_rewards_balance_invalid_page(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        with open(os.path.join(self.RESOURCES_DIR, "500.html"), "r", encoding="utf-8") as f:
            resp = responses.add(
                responses.GET,
                f"{self.test_config.constants.REWARDS_CARD_URL}",
                body=f.read(),
                status=200,
            )

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_rewards.get_rewards_balance()

        # THEN
        self.assertEqual(1, resp.call_count)
        self.assertIn("Could not find the Rewards page data.", str(cm.exception))

    def test_parse_card_infos_malformed(self):
        # GIVEN
        cases = {
            "<script id=\"__NEXT_DATA__\">not json</script>": "Could not parse the Rewards page data",
            "<script id=\"__NEXT_DATA__\">{\"props\": {\"pageProps\": {}}}</script>": "has no",
            "<script id=\"__NEXT_DATA__\">{\"props\": {\"pageProps\": {\"initialPageData\": "
            "{\"usCbccCardInfos\": \"x\"}}}}</script>": "is not a list",
        }

        for html, message in cases.items():
            with self.subTest(html=html):
                parsed = BeautifulSoup(html, self.test_config.bs4_parser)

                # WHEN
                with self.assertRaises(AmazonOrdersError) as cm:
                    _parse_card_infos(parsed, self.test_config)

                # THEN
                self.assertIn(message, str(cm.exception))

    def test_parse_card_infos_deeply_nested(self):
        # GIVEN page data nested deeply enough to exhaust the interpreter's stack
        html = "<script id=\"__NEXT_DATA__\">" + "[" * 100000 + "]" * 100000 + "</script>"
        parsed = BeautifulSoup(html, self.test_config.bs4_parser)

        # WHEN / THEN it surfaces as the library's own error, not a RecursionError
        with self.assertRaises(AmazonOrdersError) as cm:
            _parse_card_infos(parsed, self.test_config)
        self.assertIn("Could not parse the Rewards page data", str(cm.exception))

    def test_parse_card_infos_null_list(self):
        # GIVEN
        html = ("<script id=\"__NEXT_DATA__\">{\"props\": {\"pageProps\": {\"initialPageData\": "
                "{\"usCbccCardInfos\": null}}}}</script>")
        parsed = BeautifulSoup(html, self.test_config.bs4_parser)

        # WHEN / THEN a null list is the no-card state, not a parse failure
        script_tag, card_infos = _parse_card_infos(parsed, self.test_config)
        self.assertEqual("script", script_tag.name)
        self.assertEqual([], card_infos)

    def test_rewards_balance_missing_amount(self):
        # GIVEN
        card_info = {"tail": "1234", "cardDisplayName": "Prime Visa", "pointsBalance": {"points": {"value": 100}}}

        # WHEN / THEN the balance is required
        parsed = BeautifulSoup("<script id=\"__NEXT_DATA__\">{}</script>", self.test_config.bs4_parser)
        with self.assertRaises(AmazonOrdersError) as cm:
            RewardsBalance(parsed, self.test_config, card_info)
        self.assertIn("RewardsBalance.balance did not populate", str(cm.exception))

        # WHEN warn_on_missing_required_field is set it degrades to None
        config = AmazonOrdersConfig(data={"output_dir": self.test_output_dir,
                                          "cookie_jar_path": self.test_cookie_jar_path,
                                          "warn_on_missing_required_field": True})
        rewards = RewardsBalance(parsed, config, card_info)

        # THEN
        self.assertIsNone(rewards.balance)
        self.assertEqual(100, rewards.points)
        self.assertIsNone(rewards.currency)

    def test_rewards_balance_to_dict(self):
        # GIVEN
        parsed = BeautifulSoup("<script id=\"__NEXT_DATA__\">{}</script>", self.test_config.bs4_parser)
        rewards = RewardsBalance(parsed, self.test_config,
                                 {"tail": "1234", "cardDisplayName": "Prime Visa",
                                  "pointsBalance": {"amount": {"value": 12.34, "unit": "USD"},
                                                    "points": {"value": 1234, "conversionRate": 0.01}}})

        # WHEN
        serialized = rewards.to_dict()

        # THEN the page tag and config are omitted and the rest are primitives
        self.assertNotIn("parsed", serialized)
        self.assertNotIn("config", serialized)
        self.assertEqual(12.34, serialized["balance"])
        self.assertEqual(1234, serialized["points"])
        self.assertEqual("1234", serialized["card_last_four"])
        self.assertEqual(json.loads(json.dumps(serialized)), serialized)

    def test_rewards_balance_sparse_card(self):
        # GIVEN a card entry with only a balance
        parsed = BeautifulSoup("<script id=\"__NEXT_DATA__\">{}</script>", self.test_config.bs4_parser)
        rewards = RewardsBalance(parsed, self.test_config, {"pointsBalance": {"amount": {"value": 5}}})

        # THEN
        self.assertEqual(5, rewards.balance)
        self.assertIsNone(rewards.points)
        self.assertIsNone(rewards.card_name)
        self.assertIsNone(rewards.card_last_four)
        self.assertIsNone(rewards.enrolled_with_shop_with_points)
