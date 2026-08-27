__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import datetime
import logging
from typing import List, Optional

from amazonorders import util
from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.order import Order
from amazonorders.exception import AmazonOrdersError
from amazonorders.orders import AmazonOrders
from amazonorders.session import AmazonSession

logger = logging.getLogger(__name__)

DIGITAL_ORDER_FILTER = "digital"


class DigitalOrdersWindowStats:
    """
    Per-window metadata from a digital Order history pull.
    """

    def __init__(self,
                 window: str,
                 pages_walked: int,
                 rows_parsed: int,
                 header_count: Optional[int]) -> None:
        #: The time filter window (e.g. ``year-2024``, ``last30``).
        self.window: str = window
        #: The number of history pages fetched for the window.
        self.pages_walked: int = pages_walked
        #: The number of Orders returned for the window.
        self.rows_parsed: int = rows_parsed
        #: The Order count the page's own header reported for the window, or ``None`` if it could
        #: not be parsed. ``rows_parsed`` matching this value is a parse-completeness check.
        self.header_count: Optional[int] = header_count

    def __repr__(self) -> str:
        return (f"<DigitalOrdersWindowStats {self.window}: {self.pages_walked} pages, "
                f"{self.rows_parsed} rows, header {self.header_count}>")

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.window}: {self.pages_walked} pages, {self.rows_parsed} rows, header {self.header_count}"


class DigitalOrdersPullResult:
    """
    Metadata about the most recent successful digital Orders pull.
    """

    def __init__(self,
                 windows: List[DigitalOrdersWindowStats],
                 stop_reason: str) -> None:
        #: Per-window stats, in the order the windows were walked.
        self.windows: List[DigitalOrdersWindowStats] = windows
        #: Why the pull stopped: ``all_windows_walked`` (a full-history walk completed), or the
        #: single window's :attr:`~amazonorders.orders.OrderHistoryPullResult.stop_reason`
        #: (``no_more_pages``, ``empty_history``, or ``single_page_requested``).
        self.stop_reason: str = stop_reason

    def __repr__(self) -> str:
        return f"<DigitalOrdersPullResult: {len(self.windows)} windows, \"{self.stop_reason}\">"

    def __str__(self) -> str:  # pragma: no cover
        return f"{len(self.windows)} windows, {self.stop_reason}"


class AmazonDigitalOrders:
    """
    Using an authenticated :class:`~amazonorders.session.AmazonSession`, can be used to query the
    Digital Orders tab of Amazon's Order history (orders with ``D01-`` IDs, which do not appear
    in the default Order history).

    Digital orders parse with the standard :class:`~amazonorders.entity.order.Order` entity
    (fields tied to physical fulfillment, like shipments and recipient, will be empty). An
    explicit ``timeFilter`` is always sent, because the Digital Orders tab defaults to a
    "past 3 months" window that silently hides older history.
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

        self._amazon_orders: AmazonOrders = AmazonOrders(amazon_session, debug=debug, config=config)

        #: Metadata about the most recent successful digital Orders pull. ``None`` before the
        #: first pull, and reset to ``None`` at the start of each pull (so it stays ``None`` if
        #: the pull raises).
        self.last_digital_pull: Optional[DigitalOrdersPullResult] = None

    def get_digital_orders(self,
                           year: Optional[int] = None,
                           time_filter: Optional[str] = None,
                           full_details: bool = False,
                           keep_paging: bool = True) -> List[Order]:
        """
        Get digital Orders for a single time window. On success, :attr:`last_digital_pull` is
        populated with the window's stats.

        :param year: The year for which to get digital Orders. Ignored if ``time_filter`` is
            provided. Defaults to the current year if neither is specified.
        :param time_filter: The time filter to use (``last30``, ``months-3``, or ``year-YYYY``).
        :param full_details: Get the full details for each Order. This will execute an additional
            request per Order.
        :param keep_paging: ``False`` if only one page should be fetched.
        :return: A list of the requested digital Orders.
        """
        self.last_digital_pull = None

        orders = self._amazon_orders.get_order_history(year=year,
                                                       time_filter=time_filter,
                                                       order_filter=DIGITAL_ORDER_FILTER,
                                                       full_details=full_details,
                                                       keep_paging=keep_paging)

        history_pull = self._amazon_orders.last_history_pull
        if time_filter:
            window = time_filter
        else:
            window = f"year-{year if year is not None else datetime.date.today().year}"
        if history_pull:
            self.last_digital_pull = DigitalOrdersPullResult(
                windows=[DigitalOrdersWindowStats(window=window,
                                                  pages_walked=history_pull.pages_walked,
                                                  rows_parsed=history_pull.rows_parsed,
                                                  header_count=history_pull.header_count)],
                stop_reason=history_pull.stop_reason)

        return orders

    def get_all_digital_orders(self,
                               full_details: bool = False) -> List[Order]:
        """
        Get the account's full digital Order history by enumerating the year windows the Digital
        Orders tab's own time filter dropdown advertises (never a hard-coded year range) and
        walking each, newest first.

        On success, :attr:`last_digital_pull` carries per-window stats. On a mid-walk failure,
        the raised :class:`~amazonorders.exception.AmazonOrdersError`'s
        :attr:`~amazonorders.exception.AmazonOrdersError.meta` carries ``partial_orders`` (the
        Orders from the windows completed before the failure) and ``window`` (the window that
        failed) in addition to any inner resume metadata.

        :param full_details: Get the full details for each Order. This will execute an additional
            request per Order.
        :return: A list of all digital Orders, newest window first.
        """
        if not self.amazon_session.is_authenticated:
            raise AmazonOrdersError("Call AmazonSession.login() to authenticate first.")

        self.last_digital_pull = None

        tab_url = (f"{self.config.constants.ORDER_HISTORY_URL}"
                   f"?{self.config.constants.ORDER_FILTER_QUERY_PARAM}={DIGITAL_ORDER_FILTER}")
        page_response = self.amazon_session.get(tab_url)
        self.amazon_session.check_response(page_response)

        option_tags = util.select(page_response.parsed,
                                  self.config.selectors.ORDER_HISTORY_TIME_FILTER_OPTIONS_SELECTOR)
        year_filters = [str(tag["value"]) for tag in option_tags
                        if str(tag.get("value", "")).startswith("year-")]

        if not year_filters:
            raise AmazonOrdersError("Could not parse the Digital Orders time filters. "
                                    "Check if Amazon changed the HTML.")

        orders: List[Order] = []
        windows: List[DigitalOrdersWindowStats] = []
        for window in year_filters:
            try:
                window_orders = self._amazon_orders.get_order_history(time_filter=window,
                                                                      order_filter=DIGITAL_ORDER_FILTER,
                                                                      full_details=full_details)
            except AmazonOrdersError as e:
                e.meta = dict(e.meta or {})
                e.meta.update({"partial_orders": orders, "window": window})
                raise

            orders.extend(window_orders)

            history_pull = self._amazon_orders.last_history_pull
            if history_pull:
                windows.append(DigitalOrdersWindowStats(window=window,
                                                        pages_walked=history_pull.pages_walked,
                                                        rows_parsed=history_pull.rows_parsed,
                                                        header_count=history_pull.header_count))

        self.last_digital_pull = DigitalOrdersPullResult(windows=windows,
                                                         stop_reason="all_windows_walked")

        return orders
