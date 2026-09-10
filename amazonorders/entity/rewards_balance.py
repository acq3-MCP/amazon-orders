__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import logging
from typing import Any, Dict, Optional

from bs4 import Tag

from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.parsable import Parsable
from amazonorders.exception import AmazonOrdersError

logger = logging.getLogger(__name__)


class RewardsBalance(Parsable):
    """
    The rewards balance of one Amazon co-branded credit card (for instance, the Prime Visa), as embedded
    in the rewards card member page's ``__NEXT_DATA__`` JSON. ``parsed`` is that script tag; the fields
    are read from one entry of the card list it carries rather than from markup.

    Card identifiers in the source (wallet ID, card token, ownership references) are deliberately not
    retained.
    """

    def __init__(self,
                 parsed: Tag,
                 config: AmazonOrdersConfig,
                 card_info: Dict[str, Any]) -> None:
        super().__init__(parsed, config)

        points_balance = card_info.get("pointsBalance") or {}
        amount = points_balance.get("amount") or {}
        points = points_balance.get("points") or {}

        #: The rewards balance in currency (the dollar value of the points).
        self.balance: float = self._require_number(amount.get("value"), "balance")
        #: The currency of :attr:`balance` (e.g. ``USD``).
        self.currency: Optional[str] = amount.get("unit")
        #: The rewards balance in points. ``None`` when the page carries no points figure.
        self.points: Optional[int] = self._to_int(points.get("value"))
        #: The unit the points are denominated in (e.g. ``WPTS``).
        self.points_unit: Optional[str] = points.get("pointsUnit")
        #: The currency value of one point (e.g. ``0.01``, so 100 points is one dollar).
        self.conversion_rate: Optional[float] = points.get("conversionRate")
        #: When the balance was last refreshed, as the page reports it. ``None`` when not reported.
        self.last_update_time: Optional[str] = points_balance.get("lastUpdateTime")
        #: The card's display name (e.g. ``Prime Visa``).
        self.card_name: Optional[str] = card_info.get("cardDisplayName")
        #: The last four digits of the card number.
        self.card_last_four: Optional[str] = card_info.get("tail")
        #: The card network (e.g. ``Visa``).
        self.brand: Optional[str] = card_info.get("brand")
        #: The co-brand product (e.g. ``AmazonVisaSignature``).
        self.cobrand: Optional[str] = card_info.get("cobrand")
        #: The card variant (e.g. ``prime``).
        self.card_variant: Optional[str] = card_info.get("cardVariant")
        #: Whether the card is enrolled in Shop with Points (points redeemable at checkout).
        self.enrolled_with_shop_with_points: Optional[bool] = card_info.get("enrolledWithShopWithPoints")

    def __repr__(self) -> str:
        return f"<RewardsBalance {self.card_name} {self.card_last_four}: \"{self.balance}, Points: {self.points}\">"

    def __str__(self) -> str:  # pragma: no cover
        return f"RewardsBalance {self.card_name} {self.card_last_four}: {self.balance}, Points: {self.points}"

    def _require_number(self,
                        value: Any,
                        name: str) -> Any:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value

        err_msg = (f"RewardsBalance.{name} did not populate, but it's required. "
                   "Check if Amazon changed the page data.")
        if not self.config.warn_on_missing_required_field:
            raise AmazonOrdersError(err_msg)

        logger.warning(err_msg)
        return None

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return int(value)
