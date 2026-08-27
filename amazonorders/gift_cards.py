__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import datetime
import logging
from typing import List, Optional, Tuple

from bs4 import Tag

from amazonorders import util
from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.gift_card_activity import GiftCardActivity
from amazonorders.entity.parsable import Parsable
from amazonorders.exception import AmazonOrdersError
from amazonorders.session import AmazonSession

logger = logging.getLogger(__name__)


def _parse_gift_card_activity_page(parsed: Tag,
                                   config: AmazonOrdersConfig) \
        -> Tuple[bool, List[GiftCardActivity], Optional[str]]:
    table_tag = util.select_one(parsed, config.selectors.GIFT_CARD_ACTIVITY_TABLE_SELECTOR)

    activity: List[GiftCardActivity] = []
    if table_tag:
        for row_tag in util.select(table_tag, config.selectors.GIFT_CARD_ACTIVITY_SELECTOR):
            activity.append(GiftCardActivity(row_tag, config))

    next_page_url = None
    next_page_link = util.select_one(parsed, config.selectors.GIFT_CARD_ACTIVITY_NEXT_PAGE_LINK_SELECTOR)
    if next_page_link and next_page_link.get("href"):
        next_page_url = str(next_page_link["href"])
        if not next_page_url.startswith("http"):
            next_page_url = f"{config.constants.BASE_URL}{next_page_url}"

    return table_tag is not None, activity, next_page_url


class GiftCardActivityPullResult:
    """
    Metadata about the most recent successful call to
    :func:`~amazonorders.gift_cards.AmazonGiftCards.get_gift_card_activity`.
    """

    def __init__(self,
                 pages_walked: int,
                 rows_parsed: int,
                 stop_reason: str) -> None:
        #: The number of pages fetched during the pull.
        self.pages_walked: int = pages_walked
        #: The number of GiftCardActivity entries returned.
        self.rows_parsed: int = rows_parsed
        #: Why paging stopped: ``no_more_pages`` (the final page was reached), ``window_exceeded``
        #: (a row older than the ``days`` window was encountered), ``no_activity_table`` (the page
        #: rendered with no activity table, the legitimate zero-activity state), or
        #: ``single_page_requested`` (``keep_paging`` was ``False`` and more pages existed).
        self.stop_reason: str = stop_reason

    def __repr__(self) -> str:
        return (f"<GiftCardActivityPullResult: {self.pages_walked} pages, "
                f"{self.rows_parsed} rows, \"{self.stop_reason}\">")

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.pages_walked} pages, {self.rows_parsed} rows, {self.stop_reason}"


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

        #: Metadata about the most recent successful
        #: :func:`~amazonorders.gift_cards.AmazonGiftCards.get_gift_card_activity` pull. ``None``
        #: before the first pull, and reset to ``None`` at the start of each pull (so it stays
        #: ``None`` if the pull raises).
        self.last_activity_pull: Optional[GiftCardActivityPullResult] = None

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
            balance = Parsable.to_currency(balance_tag.text)

        if balance is None:
            raise AmazonOrdersError("Could not parse Gift Card balance. Check if Amazon changed the HTML.")

        return balance

    def get_gift_card_activity(self,
                               days: int = 365,
                               next_page_url: Optional[str] = None,
                               keep_paging: bool = True) -> List[GiftCardActivity]:
        """
        Get Amazon Gift Card activity for a given number of days.

        On success, :attr:`last_activity_pull` is populated with metadata about the pull. On a
        mid-pagination failure, the raised :class:`~amazonorders.exception.AmazonOrdersError`'s
        :attr:`~amazonorders.exception.AmazonOrdersError.meta` carries ``next_page_url`` (where
        paging stopped) and ``partial_activity`` (the entries fetched before the failure) —
        resuming with ``next_page_url`` and prepending ``partial_activity`` to the resumed call's
        result composes the complete window. Keep that order (``partial_activity`` first): entries
        are newest-first, matching the ledger order the page renders.

        :param days: The number of days worth of Gift Card activity to get.
        :param next_page_url: If a call to this method previously errored out, passing the exception's
            :attr:`~amazonorders.exception.AmazonOrdersError.meta` value for ``next_page_url`` will
            continue paging where it left off.
        :param keep_paging: ``False`` if only one page should be fetched.
        :return: A list of the requested GiftCardActivity entries, newest first.
        """
        if not self.amazon_session.is_authenticated:
            raise AmazonOrdersError("Call AmazonSession.login() to authenticate first.")

        self.last_activity_pull = None

        url = next_page_url or self.config.constants.GIFT_CARD_BALANCE_URL
        min_date = datetime.date.today() - datetime.timedelta(days=days)

        activity: List[GiftCardActivity] = []
        pages_walked = 0
        stop_reason = ""
        warned_unparsed_date = False
        while True:
            meta = {"next_page_url": url, "partial_activity": activity}

            page_response = self.amazon_session.get(url)
            self.amazon_session.check_response(page_response, meta=meta)

            pages_walked += 1

            try:
                found_table, loaded_activity, next_page_url = (
                    _parse_gift_card_activity_page(page_response.parsed, self.config)
                )
            except AmazonOrdersError as e:
                # A row-level parse failure should still carry the resume metadata
                e.meta = {**meta, **(e.meta or {})}
                raise

            if not found_table:
                if util.select_one(page_response.parsed, self.config.selectors.GIFT_CARD_BALANCE_SELECTOR):
                    # The page rendered (the balance is present), there is just no activity to show
                    stop_reason = "no_activity_table"
                    break

                raise AmazonOrdersError("Could not parse Gift Card activity. Check if Amazon changed the HTML.",
                                        meta=meta)

            for entry in loaded_activity:
                if entry.activity_date is None and not warned_unparsed_date:
                    logger.warning("GiftCardActivity.activity_date could not be parsed, so the days window "
                                   "cannot apply to such rows and paging may walk the full ledger. "
                                   "Check if Amazon changed the HTML.")
                    warned_unparsed_date = True
                if entry.activity_date is None or entry.activity_date >= min_date:
                    activity.append(entry)
                else:
                    next_page_url = None
                    stop_reason = "window_exceeded"
                    break

            if not next_page_url:
                if not stop_reason:
                    stop_reason = "no_more_pages"
                break

            if not keep_paging:
                stop_reason = "single_page_requested"
                break

            url = next_page_url

        self.last_activity_pull = GiftCardActivityPullResult(pages_walked=pages_walked,
                                                             rows_parsed=len(activity),
                                                             stop_reason=stop_reason)

        return activity
