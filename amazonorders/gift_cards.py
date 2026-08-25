__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

from bs4 import Tag
from dateutil import parser

from amazonorders import util
from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.gift_card_activity import GiftCardActivity
from amazonorders.entity.parsable import Parsable
from amazonorders.exception import AmazonOrdersError
from amazonorders.session import AmazonSession

logger = logging.getLogger(__name__)


def _parse_gift_card_activity_form_tag(form_tag: Tag,
                                       config: AmazonOrdersConfig) \
        -> Tuple[List[GiftCardActivity], Optional[Dict[str, str]]]:
    activity = []
    date_container_tags = util.select(form_tag, config.selectors.GIFT_CARD_ACTIVITY_DATE_CONTAINERS_SELECTOR)
    for date_container_tag in date_container_tags:
        date_tag = util.select_one(date_container_tag, config.selectors.FIELD_GIFT_CARD_ACTIVITY_DATE_SELECTOR)
        if not date_tag:
            logger.warning("Could not find date tag in GiftCardActivity form.")
            continue

        date_str = date_tag.text
        date = parser.parse(date_str).date()

        activity_container_tag = date_container_tag.find_next_sibling(
            config.selectors.GIFT_CARD_ACTIVITY_CONTAINER_SELECTOR)
        if not isinstance(activity_container_tag, Tag):
            logger.warning("Could not find GiftCardActivity container tag in GiftCardActivity form.")
            continue

        activity_tags = util.select(activity_container_tag, config.selectors.GIFT_CARD_ACTIVITY_SELECTOR)
        for activity_tag in activity_tags:
            activity.append(GiftCardActivity(activity_tag, config, date))

    form_state_input = util.select_one(form_tag, config.selectors.GIFT_CARD_ACTIVITY_NEXT_PAGE_INPUT_STATE_SELECTOR)
    form_ie_input = util.select_one(form_tag, config.selectors.GIFT_CARD_ACTIVITY_NEXT_PAGE_INPUT_IE_SELECTOR)
    next_page_input = util.select_one(form_tag, config.selectors.GIFT_CARD_ACTIVITY_NEXT_PAGE_INPUT_SELECTOR)
    if not next_page_input or not form_state_input or not form_ie_input:
        return activity, None

    next_page_data = {
        "ppw-widgetState": str(form_state_input["value"]),
        "ie": str(form_ie_input["value"]),
        str(next_page_input["name"]): "",
    }

    return activity, next_page_data


class AmazonGiftCards:
    """
    Using an authenticated :class:`~amazonorders.session.AmazonSession`, can be used to query Amazon
    for the Gift Card balance and activity ledger.
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

    def get_balance(self) -> float:
        """
        Get the current Amazon Gift Card balance.

        :return: The current Gift Card balance.
        """
        if not self.amazon_session.is_authenticated:
            raise AmazonOrdersError("Call AmazonSession.login() to authenticate first.")

        page_response = self.amazon_session.get(self.config.constants.GIFT_CARD_BALANCE_URL)
        self.amazon_session.check_response(page_response)

        balance_tag = util.select_one(page_response.parsed, self.config.selectors.GIFT_CARD_BALANCE_SELECTOR)
        balance = None
        if balance_tag:
            balance = Parsable(page_response.parsed, self.config).to_currency(balance_tag.text)

        if balance is None:
            raise AmazonOrdersError("Could not parse Gift Card balance. Check if Amazon changed the HTML.")

        return balance

    def get_gift_card_activity(self,
                               days: int = 365,
                               next_page_data: Optional[Dict[str, Any]] = None,
                               keep_paging: bool = True) -> List[GiftCardActivity]:
        """
        Get Amazon Gift Card activity for a given number of days.

        :param days: The number of days worth of Gift Card activity to get.
        :param next_page_data: If a call to this method previously errored out, passing the exception's
            :attr:`~amazonorders.exception.AmazonOrdersError.meta` will continue paging where it left off.
        :param keep_paging: ``False`` if only one page should be fetched.
        :return: A list of the requested GiftCardActivity entries.
        """
        if not self.amazon_session.is_authenticated:
            raise AmazonOrdersError("Call AmazonSession.login() to authenticate first.")

        url = self.config.constants.GIFT_CARD_BALANCE_URL
        min_date = datetime.date.today() - datetime.timedelta(days=days)

        activity: List[GiftCardActivity] = []
        first_page = True
        while first_page or keep_paging:
            first_page = False

            # The first page of activity renders with the balance page itself; subsequent pages
            # are fetched by posting the widget's paging form state back to it
            if next_page_data:
                page_response = self.amazon_session.post(url, data=next_page_data)
            else:
                page_response = self.amazon_session.get(url)
            self.amazon_session.check_response(page_response, meta=next_page_data)

            form_tag = util.select_one(page_response.parsed,
                                       self.config.selectors.GIFT_CARD_ACTIVITY_FORM_SELECTOR)

            if not form_tag:
                raise AmazonOrdersError("Could not parse Gift Card activity. Check if Amazon changed the HTML.")

            loaded_activity, next_page_data = (
                _parse_gift_card_activity_form_tag(form_tag, self.config)
            )

            for entry in loaded_activity:
                if entry.activity_date >= min_date:
                    activity.append(entry)
                else:
                    next_page_data = None
                    break

            if not next_page_data:
                keep_paging = False

        return activity
