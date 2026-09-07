__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import logging
import re
from typing import List, Optional, Union

from bs4 import Tag

from amazonorders import util
from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.parsable import Parsable
from amazonorders.exception import AmazonOrdersError

logger = logging.getLogger(__name__)

#: Matches the points figure rendered under the dollar value (``50,666 points``).
POINTS_REGEX = re.compile(r"(\d[\d,]*)\s*points\b", re.IGNORECASE)
#: Matches the masked card label rendered in the page header (``Prime Visa •••• 9790``).
CARD_NAME_REGEX = re.compile(r"^(?P<name>.*?)\s*(?:•|\*|\.){2,}\s*(?P<last_four>\d{4})\s*$", re.DOTALL)

# Ancestors at or above these are the page itself, not the rewards box
_ROOT_TAG_NAMES = {"body", "html", "[document]"}


def _innermost(tags: List[Tag]) -> Optional[Tag]:
    """
    From a document-ordered list of matched tags, return the first one that contains no other match
    (the innermost tag of the first match, so a wrapper around the label never wins over the label).
    """
    for tag in tags:
        if not any(child in tags for child in tag.find_all(True)):
            return tag
    return None


class RewardsBalance(Parsable):
    """
    The rewards balance of the Amazon co-branded credit card (for instance, the Prime Visa) as rendered
    on the rewards card member page. The page is parsed as a whole: the masked card label comes from the
    header, and the dollar value and points from the "Rewards balance" box.
    """

    def __init__(self,
                 parsed: Tag,
                 config: AmazonOrdersConfig) -> None:
        super().__init__(parsed, config)

        self._currency_regex = re.compile(
            r"{symbol}\s*-?\d[\d,]*\.\d{{2}}".format(symbol=re.escape(self.config.constants.CURRENCY_SYMBOL)))

        balance_container = self._find_balance_container()

        #: The RewardsBalance dollar value of the rewards balance. ``None`` only when it could not be
        #: parsed and ``warn_on_missing_required_field`` is set.
        self.balance: Optional[float] = self.safe_parse(self._parse_balance, container=balance_container)
        #: The RewardsBalance in points. ``None`` when the page renders no points figure.
        self.points: Optional[int] = self.safe_parse(self._parse_points, container=balance_container)
        #: The card name from the masked label in the page header (e.g. ``Prime Visa``).
        self.card_name: Optional[str] = self.safe_parse(self._parse_card_name)
        #: The last four digits of the card from the masked label in the page header.
        self.card_last_four: Optional[str] = self.safe_parse(self._parse_card_last_four)

    def __repr__(self) -> str:
        return f"<RewardsBalance {self.card_name} {self.card_last_four}: \"{self.balance}, Points: {self.points}\">"

    def __str__(self) -> str:  # pragma: no cover
        return f"RewardsBalance {self.card_name} {self.card_last_four}: {self.balance}, Points: {self.points}"

    def _find_balance_container(self) -> Optional[Tag]:
        """
        Locate the smallest tag enclosing the "Rewards balance" label that also renders a dollar value.
        Walking up from the label (rather than scanning the page) keeps unrelated amounts elsewhere on the
        page, like referral offers, from being mistaken for the balance.
        """
        heading = _innermost(util.select(self.parsed, self.config.selectors.REWARDS_BALANCE_HEADING_SELECTOR))
        if heading is None:
            return None

        container: Optional[Tag] = heading
        while container is not None and container.name not in _ROOT_TAG_NAMES:
            if self._currency_regex.search(container.get_text(" ")):
                return container
            container = container.parent

        return None

    def _parse_balance(self,
                       container: Optional[Tag]) -> Union[float, int, None]:
        value = None
        if container is not None:
            match = self._currency_regex.search(container.get_text(" "))
            if match:
                value = self.to_currency(match.group(0))

        if value is None:
            err_msg = ("RewardsBalance.balance did not populate, but it's required. "
                       "Check if Amazon changed the HTML.")
            if not self.config.warn_on_missing_required_field:
                raise AmazonOrdersError(err_msg)
            else:
                logger.warning(err_msg)

        return value

    def _parse_points(self,
                      container: Optional[Tag]) -> Optional[int]:
        if container is None:
            return None

        match = POINTS_REGEX.search(container.get_text(" "))
        if not match:
            return None

        return int(match.group(1).replace(",", ""))

    def _card_label_match(self) -> Optional["re.Match[str]"]:
        label = _innermost(util.select(self.parsed, self.config.selectors.REWARDS_CARD_NAME_SELECTOR))
        if label is None:
            return None

        return CARD_NAME_REGEX.match(label.get_text(" ").strip())

    def _parse_card_name(self) -> Optional[str]:
        match = self._card_label_match()
        if not match or not match.group("name").strip():
            return None

        return match.group("name").strip()

    def _parse_card_last_four(self) -> Optional[str]:
        match = self._card_label_match()
        if not match:
            return None

        return match.group("last_four")
