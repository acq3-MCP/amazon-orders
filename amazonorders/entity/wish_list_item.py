__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import logging
import re
from datetime import date
from typing import Optional, TypeVar

from bs4 import Tag

from amazonorders import util
from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.parsable import Parsable
from amazonorders.exception import AmazonOrdersError

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: The ASIN inside the item's external ID (``ASIN:B0C1G62PNP|ATVPDKIKX0DER``, the marketplace after the bar).
EXTERNAL_ID_ASIN_REGEX = re.compile(r"ASIN:([A-Z0-9]{10})")
#: The ASIN inside a product link (``/dp/B0C1G62PNP/``).
LINK_ASIN_REGEX = re.compile(r"/dp/([A-Z0-9]{10})")
#: The rating inside its accessible text (``4.7 out of 5 stars``).
RATING_REGEX = re.compile(r"([\d.]+)\s+out of")


class WishListItem(Parsable):
    """
    One item on an Amazon List (wish list), as the list page renders it.

    The page tells what the item is (:attr:`asin`, :attr:`title`, :attr:`link`, :attr:`variation`), what the
    person who added it asked for (:attr:`quantity_requested`, :attr:`priority`, :attr:`note`), and what
    Amazon has recorded against it (:attr:`quantity_purchased`, :attr:`purchased_date`). It does not say who
    added the item: a collaborative list's items carry no per-item attribution, so the list an item sits on
    is the only signal of whose request it is.

    :attr:`link` carries the ``coliid`` and ``colid`` query parameters, so a purchase made through it is
    attributed to the list and marks the item purchased.
    """

    def __init__(self,
                 parsed: Tag,
                 config: AmazonOrdersConfig) -> None:
        super().__init__(parsed, config)

        #: The item's ID on the list (the ``coliid``), unique to the list entry rather than the product.
        self.item_id: str = self.safe_parse(self._parse_item_id)
        #: The ID of the list the item is on.
        self.list_id: Optional[str] = self.safe_parse(self._parse_list_id)
        #: The product's ASIN.
        self.asin: Optional[str] = self.safe_parse(self._parse_asin)
        #: The product title.
        self.title: str = self.safe_parse(self._parse_title)
        #: The product link, carrying the list and item IDs so a purchase through it marks the item purchased.
        self.link: Optional[str] = self.safe_simple_parse(
            selector=self.config.selectors.FIELD_WISH_LIST_ITEM_NAME_SELECTOR,
            attr_name="href"
        )
        #: The product image link.
        self.image_link: Optional[str] = self.safe_simple_parse(
            selector=self.config.selectors.FIELD_WISH_LIST_ITEM_IMAGE_SELECTOR,
            attr_name="src"
        )
        #: The byline under the title (brand, and the category in parentheses), without the leading "by".
        self.byline: Optional[str] = self.safe_parse(self._parse_byline)
        #: The item's price, the figure the page sorts by. ``None`` when the item has no price (the page
        #: renders none and sorts it as ``-Infinity``), as happens for an unavailable product.
        self.price: Optional[float] = self.safe_parse(self._parse_price)
        #: The low end of the price range, when the page renders a range (a product whose offers vary).
        #: ``None`` when it renders a single price.
        self.price_min: Optional[float] = self.safe_parse(self._parse_price_min)
        #: The high end of the price range, when the page renders a range. ``None`` when it renders a single price.
        self.price_max: Optional[float] = self.safe_parse(self._parse_price_max)
        #: The variation chosen when the item was added (e.g. ``Size: Medium``). ``None`` when the product has none.
        self.variation: Optional[str] = self.safe_parse(self._parse_variation)
        #: The note (comment) on the item. ``None`` when there is none.
        self.note: Optional[str] = self.safe_parse(self._parse_note)
        #: The quantity wanted ("Needs").
        self.quantity_requested: Optional[int] = self.safe_parse(self._parse_quantity_requested)
        #: The quantity Amazon has recorded as bought ("Has").
        self.quantity_purchased: Optional[int] = self.safe_parse(self._parse_quantity_purchased)
        #: The priority as the page encodes it, ``0`` being medium; see :attr:`priority_label` for the word.
        self.priority: Optional[int] = self.safe_parse(self._parse_priority)
        #: The priority as the page labels it (e.g. ``medium``, ``high``).
        self.priority_label: Optional[str] = self.safe_parse(self._parse_priority_label)
        #: The date the item was added. The page renders it only for an item not yet purchased, which shows
        #: :attr:`purchased_date` instead.
        self.added_date: Optional[date] = self.safe_simple_parse(
            selector=self.config.selectors.FIELD_WISH_LIST_ITEM_ADDED_DATE_SELECTOR,
            parse_date=True
        )
        #: The date the item was last purchased. ``None`` for an item not yet purchased.
        self.purchased_date: Optional[date] = self.safe_simple_parse(
            selector=self.config.selectors.FIELD_WISH_LIST_ITEM_PURCHASED_DATE_SELECTOR,
            parse_date=True
        )
        #: Whether Amazon considers the item purchased: it has a :attr:`purchased_date`, or
        #: :attr:`quantity_purchased` has reached :attr:`quantity_requested`.
        self.purchased: bool = self.safe_parse(self._parse_purchased)
        #: The product's average rating out of 5. ``None`` when the page renders none.
        self.rating: Optional[float] = self.safe_parse(self._parse_rating)
        #: The product's review count. ``None`` when the page renders none.
        self.review_count: Optional[int] = self.safe_parse(self._parse_review_count)
        #: Whether the page shows the Prime badge on the item.
        self.prime_eligible: bool = self.safe_parse(self._parse_prime_eligible)
        #: The label of the item's primary button as the page renders it (``Add to Cart`` when a buyable
        #: offer exists, ``See all buying options`` when none is selected or the product is unavailable).
        self.action_label: Optional[str] = self.safe_parse(self._parse_action_label)

    def __repr__(self) -> str:
        return f"<WishListItem {self.item_id}: \"{self.title}\">"

    def __str__(self) -> str:  # pragma: no cover
        return f"WishListItem {self.item_id}: {self.title}"

    def _require(self,
                 value: Optional[T],
                 name: str) -> Optional[T]:
        if value is not None:
            return value

        err_msg = (f"WishListItem.{name} did not populate, but it's required. "
                   "Check if Amazon changed the HTML.")
        if not self.config.warn_on_missing_required_field:
            raise AmazonOrdersError(err_msg)

        logger.warning(err_msg)
        return None

    def _text(self,
              selector: str) -> Optional[str]:
        tag = util.select_one(self.parsed, selector)
        if tag is None:
            return None

        text = re.sub(r"\s+", " ", tag.text).strip()

        return text or None

    def _parse_item_id(self) -> Optional[str]:
        item_id = str(self.parsed.get("data-itemid") or "").strip()

        return self._require(item_id or None, "item_id")

    def _parse_list_id(self) -> Optional[str]:
        return str(self.parsed.get("data-id") or "").strip() or None

    def _parse_asin(self) -> Optional[str]:
        external_id_tag = util.select_one(self.parsed, self.config.selectors.FIELD_WISH_LIST_ITEM_EXTERNAL_ID_SELECTOR)
        if external_id_tag is not None:
            match = EXTERNAL_ID_ASIN_REGEX.search(str(external_id_tag.get("value") or ""))
            if match:
                return match.group(1)

        link_tag = util.select_one(self.parsed, self.config.selectors.FIELD_WISH_LIST_ITEM_NAME_SELECTOR)
        if link_tag is not None:
            match = LINK_ASIN_REGEX.search(str(link_tag.get("href") or ""))
            if match:
                return match.group(1)

        return None

    def _parse_title(self) -> Optional[str]:
        name_tag = util.select_one(self.parsed, self.config.selectors.FIELD_WISH_LIST_ITEM_NAME_SELECTOR)
        title = None
        if name_tag is not None:
            title = str(name_tag.get("title") or "").strip() or re.sub(r"\s+", " ", name_tag.text).strip()

        return self._require(title or None, "title")

    def _parse_byline(self) -> Optional[str]:
        byline = self._text(self.config.selectors.FIELD_WISH_LIST_ITEM_BYLINE_SELECTOR)
        if byline is None:
            return None

        return re.sub(r"^by\s+", "", byline) or None

    def _parse_price(self) -> Optional[float]:
        value = self.parsed.get("data-price")
        if value is None:
            return self._parse_offscreen_price(self.config.selectors.FIELD_WISH_LIST_ITEM_PRICE_SELECTOR)

        try:
            price = float(str(value))
        except ValueError:
            return None

        if price != price or price in (float("inf"), float("-inf")):
            return None

        return price

    def _parse_offscreen_price(self,
                               selector: str) -> Optional[float]:
        value = self._text(selector)
        if value is None:
            return None

        currency = self.to_currency(value)

        return float(currency) if currency is not None else None

    def _parse_price_min(self) -> Optional[float]:
        return self._parse_offscreen_price(self.config.selectors.FIELD_WISH_LIST_ITEM_MIN_PRICE_SELECTOR)

    def _parse_price_max(self) -> Optional[float]:
        return self._parse_offscreen_price(self.config.selectors.FIELD_WISH_LIST_ITEM_MAX_PRICE_SELECTOR)

    def _parse_variation(self) -> Optional[str]:
        variation = self._text(self.config.selectors.FIELD_WISH_LIST_ITEM_VARIATION_SELECTOR)
        if variation is None:
            return None

        return re.sub(r"\s*:\s*", ": ", variation)

    def _parse_note(self) -> Optional[str]:
        return self._text(self.config.selectors.FIELD_WISH_LIST_ITEM_NOTE_SELECTOR)

    def _parse_int(self,
                   selector: str) -> Optional[int]:
        value = self._text(selector)
        if value is None:
            return None

        return int(value.replace(",", ""))

    def _parse_quantity_requested(self) -> Optional[int]:
        return self._parse_int(self.config.selectors.FIELD_WISH_LIST_ITEM_REQUESTED_SELECTOR)

    def _parse_quantity_purchased(self) -> Optional[int]:
        return self._parse_int(self.config.selectors.FIELD_WISH_LIST_ITEM_PURCHASED_SELECTOR)

    def _parse_priority(self) -> Optional[int]:
        return self._parse_int(self.config.selectors.FIELD_WISH_LIST_ITEM_PRIORITY_SELECTOR)

    def _parse_priority_label(self) -> Optional[str]:
        return self._text(self.config.selectors.FIELD_WISH_LIST_ITEM_PRIORITY_LABEL_SELECTOR)

    def _parse_purchased(self) -> bool:
        if self.purchased_date is not None:
            return True

        if self.quantity_requested is None or self.quantity_purchased is None:
            return False

        return self.quantity_requested > 0 and self.quantity_purchased >= self.quantity_requested

    def _parse_rating(self) -> Optional[float]:
        value = self._text(self.config.selectors.FIELD_WISH_LIST_ITEM_RATING_SELECTOR)
        match = RATING_REGEX.search(value) if value else None

        return float(match.group(1)) if match else None

    def _parse_review_count(self) -> Optional[int]:
        return self._parse_int(self.config.selectors.FIELD_WISH_LIST_ITEM_REVIEW_COUNT_SELECTOR)

    def _parse_prime_eligible(self) -> bool:
        badge_tag = util.select_one(self.parsed, self.config.selectors.FIELD_WISH_LIST_ITEM_PRIME_BADGE_SELECTOR)

        return badge_tag is not None

    def _parse_action_label(self) -> Optional[str]:
        return self._text(self.config.selectors.FIELD_WISH_LIST_ITEM_ACTION_SELECTOR)
