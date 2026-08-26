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
    An entry in the Amazon Gift Card activity ledger (for instance, an amount applied to an
    Order, a Reload, or a refund credited back to the balance).
    """

    def __init__(self,
                 parsed: Tag,
                 config: AmazonOrdersConfig) -> None:
        super().__init__(parsed, config)

        #: The GiftCardActivity date.
        self.activity_date: Optional[date] = self.safe_simple_parse(
            selector=self.config.selectors.FIELD_GIFT_CARD_ACTIVITY_DATE_SELECTOR,
            parse_date=True
        )
        #: The GiftCardActivity description.
        self.description: Optional[str] = self.safe_simple_parse(
            selector=self.config.selectors.FIELD_GIFT_CARD_ACTIVITY_DESCRIPTION_SELECTOR
        )
        #: The GiftCardActivity amount. Negative when the balance was debited (e.g. applied to
        #: an Order), positive when it was credited (e.g. a Reload or refund).
        self.amount: float = self.safe_parse(self._parse_amount)
        #: The GiftCardActivity credited the balance or not.
        self.is_credit: bool = bool(self.amount and self.amount > 0)
        #: The Gift Card balance after this activity was applied.
        self.closing_balance: Optional[float] = self.safe_parse(self._parse_closing_balance)
        #: The Order number the GiftCardActivity references. ``None`` when the row renders no
        #: Order anchor: claim code redemptions and some refund rows, but also some
        #: applied-to-order debit rows (observed in the wild on small amounts, likely digital
        #: orders) — so ``None`` on a debit is expected page behavior, not data loss.
        self.order_number: Optional[str] = self.safe_parse(self._parse_order_number)
        #: The Order details link. ``None`` whenever :attr:`order_number` is ``None``.
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

    def _parse_closing_balance(self) -> Union[float, int, None]:
        value = self.simple_parse(self.config.selectors.FIELD_GIFT_CARD_ACTIVITY_CLOSING_BALANCE_SELECTOR)

        return self.to_currency(value)

    def _parse_order_number(self) -> Optional[str]:
        value = self.simple_parse(self.config.selectors.FIELD_GIFT_CARD_ACTIVITY_ORDER_NUMBER_SELECTOR)

        if value is None:
            value = self.description

        if value is None:
            return None

        match = ORDER_NUMBER_REGEX.search(str(value))

        return match.group(1) if match else None

    def _parse_order_details_link(self) -> Optional[str]:
        if not self.order_number:
            return None

        value = self.simple_parse(self.config.selectors.FIELD_GIFT_CARD_ACTIVITY_ORDER_LINK_SELECTOR,
                                  attr_name="href")

        if not value:
            value = f"{self.config.constants.ORDER_DETAILS_URL}?orderID={self.order_number}"

        return value
