__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import logging
import re
from datetime import date
from typing import Optional, Union

from bs4 import Tag

from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.parsable import Parsable
from amazonorders.exception import AmazonOrdersError

logger = logging.getLogger(__name__)

ORDER_NUMBER_REGEX = re.compile(r"(\d{3}-\d{7}-\d{7})")


class GiftCardActivity(Parsable):
    """
    An entry in the Amazon Gift Card activity ledger (for instance, a claim code redemption,
    an amount applied to an Order, or a refund credited back to the balance).
    """

    def __init__(self,
                 parsed: Tag,
                 config: AmazonOrdersConfig,
                 activity_date: date) -> None:
        super().__init__(parsed, config)

        #: The GiftCardActivity date.
        self.activity_date: date = activity_date
        #: The GiftCardActivity description.
        self.description: Optional[str] = self.safe_simple_parse(
            selector=self.config.selectors.FIELD_GIFT_CARD_ACTIVITY_DESCRIPTION_SELECTOR
        )
        #: The GiftCardActivity amount. Negative when the balance was debited (e.g. applied to
        #: an Order), positive when it was credited (e.g. a redemption or refund).
        self.amount: float = self.safe_parse(self._parse_amount)
        #: The GiftCardActivity credited the balance or not.
        self.is_credit: bool = self.amount > 0
        #: The Order number the GiftCardActivity references. ``None`` if the activity is not
        #: associated with an Order (e.g. a claim code redemption).
        self.order_number: Optional[str] = self.safe_parse(self._parse_order_number)
        #: The Order details link. ``None`` if the activity is not associated with an Order.
        self.order_details_link: Optional[str] = self.safe_parse(self._parse_order_details_link)

    def __repr__(self) -> str:
        return f"<GiftCardActivity {self.activity_date}: \"{self.description}, Amount: {self.amount}\">"

    def __str__(self) -> str:  # pragma: no cover
        return f"GiftCardActivity {self.activity_date}: {self.description}, Amount: {self.amount}"

    def _parse_amount(self) -> Union[float, int, None]:
        value = self.simple_parse(self.config.selectors.FIELD_GIFT_CARD_ACTIVITY_AMOUNT_SELECTOR)

        value = self.to_currency(value)

        if value is None:  # pragma: no cover
            err_msg = ("GiftCardActivity.amount did not populate, but it's required. "
                       "Check if Amazon changed the HTML.")
            if not self.config.warn_on_missing_required_field:
                raise AmazonOrdersError(err_msg)
            else:
                logger.warning(err_msg)

        return value

    def _parse_order_number(self) -> Optional[str]:
        value = self.simple_parse(self.config.selectors.FIELD_GIFT_CARD_ACTIVITY_ORDER_NUMBER_SELECTOR)

        if value is None:
            value = self.description

        if value is None:
            return None

        match = ORDER_NUMBER_REGEX.search(str(value))

        return match.group(1) if match else None

    def _parse_order_details_link(self) -> Optional[str]:
        value = self.simple_parse(self.config.selectors.FIELD_GIFT_CARD_ACTIVITY_ORDER_LINK_SELECTOR,
                                  attr_name="href")

        if not value and self.order_number:
            value = f"{self.config.constants.ORDER_DETAILS_URL}?orderID={self.order_number}"

        return value
