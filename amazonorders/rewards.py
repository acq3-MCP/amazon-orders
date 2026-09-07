__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import logging
from typing import Optional

from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.rewards_balance import RewardsBalance
from amazonorders.exception import AmazonOrdersError
from amazonorders.session import AmazonSession

logger = logging.getLogger(__name__)


class AmazonRewards:
    """
    Using an authenticated :class:`~amazonorders.session.AmazonSession`, can be used to query Amazon
    for the rewards balance of the Amazon co-branded credit card (for instance, the Prime Visa).

    Only what Amazon renders itself is available: the rewards balance in dollars and points, and the
    masked card label. The card balance, payment due, and minimum due are hosted by the issuing bank
    (Chase) behind a separate login and render as placeholders on the Amazon page, so they are not parsed.
    """

    def __init__(self,
                 amazon_session: AmazonSession,
                 debug: Optional[bool] = None,
                 config: Optional[AmazonOrdersConfig] = None) -> None:
        if not debug:
            debug = amazon_session.debug
        if not config:
            config = amazon_session.config

        #: The session to use for requests.
        self.amazon_session: AmazonSession = amazon_session
        #: The config to use.
        self.config: AmazonOrdersConfig = config

        #: Setting logger to ``DEBUG`` will send output to ``stderr``.
        self.debug: bool = debug
        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_rewards_balance(self) -> RewardsBalance:
        """
        Get the current rewards balance of the Amazon co-branded credit card.

        :return: The current rewards balance.
        """
        if not self.amazon_session.is_authenticated:
            raise AmazonOrdersError("Call AmazonSession.login() to authenticate first.")

        page_response = self.amazon_session.get(self.config.constants.REWARDS_CARD_URL)
        self.amazon_session.check_response(page_response)

        rewards_balance = RewardsBalance(page_response.parsed, self.config)

        if rewards_balance.balance is None:
            raise AmazonOrdersError("Could not parse Rewards balance. Check that the account has an Amazon "
                                    "rewards card, and if Amazon changed the HTML.")

        return rewards_balance
