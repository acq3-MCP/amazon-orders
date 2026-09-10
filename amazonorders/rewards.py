__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from bs4 import Tag

from amazonorders import util
from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.rewards_balance import RewardsBalance
from amazonorders.exception import AmazonOrdersError, AmazonOrdersNotFoundError
from amazonorders.session import AmazonSession

logger = logging.getLogger(__name__)

#: Where the card list lives inside the page's ``__NEXT_DATA__`` JSON.
_CARD_INFOS_PATH = ("props", "pageProps", "initialPageData", "usCbccCardInfos")


def _parse_card_infos(parsed: Tag,
                      config: AmazonOrdersConfig) -> Tuple[Tag, List[Dict[str, Any]]]:
    """
    Extract the card list from the rewards card member page. The page is a Next.js app whose widgets
    render client-side into an empty skeleton, so the visible DOM is useless to a plain fetch; the
    server-embedded ``__NEXT_DATA__`` JSON is where the data is.

    :param parsed: The parsed page.
    :param config: The config to use.
    :return: The page data script tag, and the raw card entries in page order (possibly empty).
    """
    script_tag = util.select_one(parsed, config.selectors.REWARDS_NEXT_DATA_SELECTOR)
    if script_tag is None:
        raise AmazonOrdersError("Could not find the Rewards page data. Check if Amazon changed the HTML.")

    try:
        data: Any = json.loads(script_tag.get_text())
    except (ValueError, RecursionError) as e:
        # RecursionError (deeply nested JSON) is a RuntimeError, not a ValueError, so it needs naming
        raise AmazonOrdersError(f"Could not parse the Rewards page data: {e}. "
                                "Check if Amazon changed the HTML.")

    for key in _CARD_INFOS_PATH:
        if not isinstance(data, dict) or key not in data:
            raise AmazonOrdersError(f"Rewards page data has no \"{'.'.join(_CARD_INFOS_PATH)}\". "
                                    "Check if Amazon changed the page data.")
        data = data[key]

    if data is None:
        return script_tag, []
    if not isinstance(data, list):
        raise AmazonOrdersError("Rewards page data card list is not a list. Check if Amazon changed the page data.")

    return script_tag, data


class AmazonRewards:
    """
    Using an authenticated :class:`~amazonorders.session.AmazonSession`, can be used to query Amazon
    for the rewards balance of the Amazon co-branded credit card (for instance, the Prime Visa).

    Only what Amazon embeds in the page is available: each card's rewards balance in currency and
    points, and the card's name, network, and last four digits. The card balance, payment due, and
    minimum due are hosted by the issuing bank (Chase) behind a separate login and are not present.
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

    def get_rewards_balances(self) -> List[RewardsBalance]:
        """
        Get the rewards balance of every Amazon co-branded credit card on the account, in page order.

        :return: The rewards balances (empty when the account holds no card).
        """
        if not self.amazon_session.is_authenticated:
            raise AmazonOrdersError("Call AmazonSession.login() to authenticate first.")

        page_response = self.amazon_session.get(self.config.constants.REWARDS_CARD_URL)
        self.amazon_session.check_response(page_response)

        script_tag, card_infos = _parse_card_infos(page_response.parsed, self.config)

        return [RewardsBalance(script_tag, self.config, card_info) for card_info in card_infos]

    def get_rewards_balance(self,
                            card_last_four: Optional[str] = None) -> RewardsBalance:
        """
        Get the current rewards balance of the Amazon co-branded credit card. When the account holds
        several cards, the first is returned unless ``card_last_four`` selects one.

        :param card_last_four: The last four digits of the card to select.
        :return: The current rewards balance.
        """
        balances = self.get_rewards_balances()

        if card_last_four is not None:
            balances = [b for b in balances if b.card_last_four == card_last_four]

        if not balances:
            if card_last_four is not None:
                raise AmazonOrdersNotFoundError(f"No Amazon rewards card ending in {card_last_four} on this account.")
            raise AmazonOrdersNotFoundError("No Amazon rewards card on this account.")

        return balances[0]
