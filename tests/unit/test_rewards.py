__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import os

import responses
from bs4 import BeautifulSoup

from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.rewards_balance import RewardsBalance
from amazonorders.exception import AmazonOrdersError, AmazonOrdersAuthRedirectError
from amazonorders.rewards import AmazonRewards
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

    def _parse_fixture(self, html_file, config=None):
        with open(os.path.join(self.RESOURCES_DIR, "rewards", html_file), "r",
                  encoding="utf-8") as f:
            parsed = BeautifulSoup(f.read(), self.test_config.bs4_parser)
        return RewardsBalance(parsed, config or self.test_config)

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
        self.assertEqual(506.66, rewards.balance)
        self.assertEqual(50666, rewards.points)
        self.assertEqual("Prime Visa", rewards.card_name)
        self.assertEqual("9790", rewards.card_last_four)
        self.assertEqual("<RewardsBalance Prime Visa 9790: \"506.66, Points: 50666\">", repr(rewards))

    @responses.activate
    def test_get_rewards_balance_no_card(self):
        # GIVEN the apply landing page renders instead of the member page
        self.amazon_session.is_authenticated = True
        resp = self._given_rewards_page_exists("rewards-card-no-card.html")

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_rewards.get_rewards_balance()

        # THEN
        self.assertEqual(1, resp.call_count)
        self.assertIn("RewardsBalance.balance did not populate", str(cm.exception))

    @responses.activate
    def test_get_rewards_balance_no_card_warn_on_missing(self):
        # GIVEN
        config = AmazonOrdersConfig(data={"output_dir": self.test_output_dir,
                                          "cookie_jar_path": self.test_cookie_jar_path,
                                          "warn_on_missing_required_field": True})
        amazon_session = AmazonSession("some-username@gmail.com", "some-password", config=config)
        amazon_session.is_authenticated = True
        amazon_rewards = AmazonRewards(amazon_session)
        resp = self._given_rewards_page_exists("rewards-card-no-card.html")

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            amazon_rewards.get_rewards_balance()

        # THEN the entity warned instead of raising, and the module raised on the None balance
        self.assertEqual(1, resp.call_count)
        self.assertIn("Could not parse Rewards balance.", str(cm.exception))

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
        self.assertIn("RewardsBalance.balance did not populate", str(cm.exception))

    def test_rewards_balance_ignores_amounts_outside_the_box(self):
        # GIVEN the referral offer ($500) and Chase placeholders ($-) render before the Rewards balance box
        rewards = self._parse_fixture("rewards-card-member.html")

        # THEN the balance is the one anchored to the "Rewards balance" label
        self.assertEqual(506.66, rewards.balance)

    def test_rewards_balance_points_optional(self):
        # GIVEN a box that renders only the dollar value
        html = """<div><h1>Prime Visa **** 1234</h1>
                  <div><h2>Rewards balance</h2><span>$1,234.50</span></div></div>"""
        parsed = BeautifulSoup(html, self.test_config.bs4_parser)

        # WHEN
        rewards = RewardsBalance(parsed, self.test_config)

        # THEN
        self.assertEqual(1234.50, rewards.balance)
        self.assertIsNone(rewards.points)
        self.assertEqual("Prime Visa", rewards.card_name)
        self.assertEqual("1234", rewards.card_last_four)

    def test_rewards_balance_label_wrapped(self):
        # GIVEN the label is wrapped in a bare div (the innermost match must win, not the wrapper)
        html = """<div><div><span>Rewards balance</span></div>
                  <span>$2.00</span><span>200 points</span></div>"""
        parsed = BeautifulSoup(html, self.test_config.bs4_parser)

        # WHEN
        rewards = RewardsBalance(parsed, self.test_config)

        # THEN
        self.assertEqual(2.00, rewards.balance)
        self.assertEqual(200, rewards.points)
        self.assertIsNone(rewards.card_name)
        self.assertIsNone(rewards.card_last_four)
