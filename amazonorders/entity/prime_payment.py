__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import logging
from datetime import date
from typing import Optional, TypeVar, Union

from bs4 import Tag

from amazonorders import util
from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.parsable import Parsable
from amazonorders.exception import AmazonOrdersError
from amazonorders.selectors import Selector
from amazonorders.util import ORDER_NUMBER_REGEX

logger = logging.getLogger(__name__)

T = TypeVar("T")


class PrimePayment(Parsable):
    """
    One charge in the Prime membership payment history: the membership fee Amazon billed on a
    sign-up or renewal date, as listed on the Prime payments page.

    Each charge is a digital Order (a ``D01-`` ID) that neither the Order history nor the Digital
    Orders tab lists, so this entity is the index to it. The Order itself, with its line item,
    payment method, subtotal, and tax, is fetched by :attr:`order_number` with
    :func:`~amazonorders.orders.AmazonOrders.get_order`, which renders the standard Order details
    layout for these IDs.
    """

    def __init__(self,
                 parsed: Tag,
                 config: AmazonOrdersConfig) -> None:
        super().__init__(parsed, config)

        #: The date the membership fee was charged. This is the charge date, not the start of the
        #: membership period it covers.
        self.payment_date: Optional[date] = self.safe_simple_parse(
            selector=self.config.selectors.FIELD_PRIME_PAYMENT_DATE_SELECTOR,
            parse_date=True
        )
        #: The amount charged, tax included, as the page lists it.
        self.total: Optional[float] = self.safe_parse(self._parse_total)
        #: The digital Order number (``D01-…``) of the charge.
        self.order_number: Optional[str] = self.safe_parse(self._parse_order_number)
        #: The Order details link. ``None`` whenever :attr:`order_number` is ``None``.
        self.order_details_link: Optional[str] = self.safe_parse(self._parse_order_details_link)
        #: The absolute URL of the card's "View Receipt" link (the digital Order summary's print
        #: view). ``None`` when the card renders no receipt link.
        self.receipt_link: Optional[str] = self.safe_parse(self._parse_receipt_link)

    def __repr__(self) -> str:
        return f"<PrimePayment {self.payment_date}: \"{self.total}, Order #: {self.order_number}\">"

    def __str__(self) -> str:  # pragma: no cover
        return f"PrimePayment {self.payment_date}: {self.total}, Order #: {self.order_number}"

    def _parse_labeled_value(self,
                             label_selector: Selector) -> Optional[str]:
        """
        Read the value of a card body row by its label: the label selector matches the label span, and
        the value is the row's (the label's parent) value tag.

        :param label_selector: The selector matching the row's label.
        :return: The row's value text, or ``None`` when the row or its value is absent.
        """
        label_tag = util.select_one(self.parsed, label_selector)
        if label_tag is None or label_tag.parent is None:
            return None

        value_tag = util.select_one(label_tag.parent, self.config.selectors.FIELD_PRIME_PAYMENT_VALUE_SELECTOR)
        if value_tag is None:
            return None

        return value_tag.text.strip()

    def _require(self,
                 value: Optional[T],
                 name: str) -> Optional[T]:
        if value is not None:
            return value

        err_msg = (f"PrimePayment.{name} did not populate, but it's required. "
                   "Check if Amazon changed the HTML.")
        if not self.config.warn_on_missing_required_field:
            raise AmazonOrdersError(err_msg)

        logger.warning(err_msg)
        return None

    def _parse_total(self) -> Union[float, int, None]:
        value = self._parse_labeled_value(self.config.selectors.FIELD_PRIME_PAYMENT_TOTAL_LABEL_SELECTOR)

        return self._require(self.to_currency(value) if value is not None else None, "total")

    def _parse_order_number(self) -> Optional[str]:
        value = self._parse_labeled_value(self.config.selectors.FIELD_PRIME_PAYMENT_ORDER_NUMBER_LABEL_SELECTOR)

        match = ORDER_NUMBER_REGEX.search(value) if value else None

        return self._require(match.group(1) if match else None, "order_number")

    def _parse_order_details_link(self) -> Optional[str]:
        if not self.order_number:
            return None

        return f"{self.config.constants.ORDER_DETAILS_URL}?orderID={self.order_number}"

    def _parse_receipt_link(self) -> Optional[str]:
        label_tag = util.select_one(self.parsed, self.config.selectors.FIELD_PRIME_PAYMENT_RECEIPTS_LABEL_SELECTOR)
        if label_tag is None or label_tag.parent is None:
            return None

        link_tag = util.select_one(label_tag.parent, self.config.selectors.FIELD_PRIME_PAYMENT_RECEIPT_LINK_SELECTOR)
        if link_tag is None or not link_tag.get("href"):
            return None

        return self.with_base_url(str(link_tag["href"]))
