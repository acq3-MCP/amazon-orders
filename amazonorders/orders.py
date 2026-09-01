__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import asyncio
import concurrent.futures
import datetime
import logging
import re
from typing import Any, Callable, List, Optional
from urllib.parse import quote

from bs4 import BeautifulSoup, Tag

from amazonorders import util
from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.order import Order
from amazonorders.exception import AmazonOrdersError, AmazonOrdersNotFoundError
from amazonorders.session import AmazonSession

logger = logging.getLogger(__name__)


class OrderHistoryPullResult:
    """
    Metadata about the most recent successful call to
    :func:`~amazonorders.orders.AmazonOrders.get_order_history`.
    """

    def __init__(self,
                 pages_walked: int,
                 rows_parsed: int,
                 header_count: Optional[int],
                 stop_reason: str) -> None:
        #: The number of history pages fetched during the pull.
        self.pages_walked: int = pages_walked
        #: The number of Orders returned.
        self.rows_parsed: int = rows_parsed
        #: The Order count the history page's own header reported for the window ("N orders placed
        #: in …"), or ``None`` if the header could not be parsed. When paging from the start of the
        #: window, ``rows_parsed`` matching this value is a parse-completeness check.
        self.header_count: Optional[int] = header_count
        #: Why paging stopped: ``no_more_pages`` (the final page was reached), ``empty_history``
        #: (the window contains no Orders), or ``single_page_requested`` (``keep_paging`` was
        #: ``False``).
        self.stop_reason: str = stop_reason

    def __repr__(self) -> str:
        return (f"<OrderHistoryPullResult: {self.pages_walked} pages, "
                f"{self.rows_parsed} rows, \"{self.stop_reason}\">")

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.pages_walked} pages, {self.rows_parsed} rows, {self.stop_reason}"


class OrderHistoryPageResult:
    """
    The parsed contents of a single Order history page, as returned by
    :func:`~amazonorders.orders.AmazonOrders.parse_order_history_page`.
    """

    def __init__(self,
                 orders: List[Order],
                 header_count: Optional[int],
                 next_page_url: Optional[str],
                 page_type: str) -> None:
        #: The Orders on this page.
        self.orders: List[Order] = orders
        #: The Order count the page's own header reports for the window ("N orders placed in …"),
        #: or ``None`` if the header could not be parsed.
        self.header_count: Optional[int] = header_count
        #: The absolute URL of the next history page, or ``None`` on the final page.
        self.next_page_url: Optional[str] = next_page_url
        #: What the page is: ``orders`` (Order rows were parsed), ``empty_window`` (the page's own
        #: count confirms there are no Orders at this index), ``not_order_history`` (a sign-in,
        #: Captcha, or challenge page — the supplied HTML is not an Order history page at all), or
        #: ``csd_encrypted`` (an Order history page whose card content Amazon served as an encrypted
        #: client-side-decryption payload — observed on browser-fetched digital history; the rows are
        #: unreadable, though :attr:`header_count` often still parses from the time-filter label).
        self.page_type: str = page_type

    def __repr__(self) -> str:
        return (f"<OrderHistoryPageResult: \"{self.page_type}\", {len(self.orders)} rows, "
                f"header {self.header_count}>")

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.page_type}: {len(self.orders)} rows, header {self.header_count}"


class AmazonOrders:
    """
    Using an authenticated :class:`~amazonorders.session.AmazonSession`, can be used to query Amazon
    for Order details and history.
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
        #: :func:`~amazonorders.orders.AmazonOrders.get_order_history` pull. ``None`` before the
        #: first pull, and reset to ``None`` at the start of each pull (so it stays ``None`` if
        #: the pull raises).
        self.last_history_pull: Optional[OrderHistoryPullResult] = None

    @staticmethod
    def _parse_header_count(parsed: Tag,
                            config: AmazonOrdersConfig) -> Optional[int]:
        # Parse just the leading number so the count survives thousands separators
        # (e.g. "1,213 orders") and any trailing copy in the label
        order_count_tag = util.select_one(parsed, config.selectors.ORDER_HISTORY_COUNT_SELECTOR)
        if not order_count_tag:
            return None
        count_match = re.match(r"\s*([\d,]+)", order_count_tag.text)
        if not count_match:
            return None
        return int(count_match.group(1).replace(",", ""))

    @staticmethod
    def _parse_next_page_url(parsed: Tag,
                             config: AmazonOrdersConfig) -> Optional[str]:
        next_page_tag = util.select_one(parsed, config.selectors.NEXT_PAGE_LINK_SELECTOR)
        if not next_page_tag:
            return None
        next_page = str(next_page_tag["href"])
        if not next_page.startswith("http"):
            next_page = f"{config.constants.BASE_URL}{next_page}"
        return next_page

    @staticmethod
    def parse_order_history(html: str,
                            config: AmazonOrdersConfig) -> List[Order]:
        """
        Parse an already-fetched Amazon Order history page into Orders, without a session driving the
        fetch — useful for parsing HTML obtained elsewhere (a browser, a proxy, a fixture) and for
        network-free testing.

        Only the Orders on the given page are returned, with no classification of the page itself —
        a page with no Order rows parses to an empty list whatever the reason. Use
        :func:`parse_order_history_page` when the page's header count, next-page URL, or a
        distinction between an empty window and a non-history page is needed.

        :param html: The Order history page HTML to parse.
        :param config: The config providing the selectors and entity classes used for parsing.
        :return: A list of the parsed Orders.
        """
        parsed = BeautifulSoup(html, config.bs4_parser)
        order_tags = util.select(parsed, config.selectors.ORDER_HISTORY_ENTITY_SELECTOR)
        return [config.order_cls(tag, config, index=i) for i, tag in enumerate(order_tags)]

    @staticmethod
    def parse_order_details(html: str,
                            config: AmazonOrdersConfig) -> Order:
        """
        Parse an already-fetched Amazon Order details page into an Order, without a session driving the
        fetch — useful for parsing HTML obtained elsewhere and for network-free testing. Digital
        (``D01-``) Order details pages parse the same way — their row-label differences are handled
        by the :class:`~amazonorders.entity.order.Order` entity itself.

        :param html: The Order details page HTML to parse.
        :param config: The config providing the selectors and entity classes used for parsing.
        :return: The parsed Order.
        """
        parsed = BeautifulSoup(html, config.bs4_parser)
        order_details_tag = util.select_one(parsed, config.selectors.ORDER_DETAILS_ENTITY_SELECTOR)
        if not order_details_tag:
            raise AmazonOrdersError("Could not parse Order details. Check if Amazon changed the HTML.")
        return config.order_cls(order_details_tag, config, full_details=True)

    @staticmethod
    def parse_order_history_page(html: str,
                                 config: AmazonOrdersConfig,
                                 start_index: int = 0) -> "OrderHistoryPageResult":
        """
        Parse a single already-fetched Amazon Order history page — including a digital Order history
        page (``orderFilter=digital``), which shares the same markup — into its Orders and page
        metadata, without a session driving the fetch.

        The result's :attr:`~amazonorders.orders.OrderHistoryPageResult.page_type` distinguishes a
        genuinely empty window (the page's own header count confirms there are no Orders at
        ``start_index``) from a page that is not Order history at all (sign-in, Captcha, or
        challenge pages), and from a ``csd_encrypted`` page — one whose Order cards Amazon served
        as an encrypted client-side-decryption payload rather than readable markup (observed on
        browser-fetched digital history; such pages carry a ``disableCsd`` noscript fallback). A
        page with no Order rows whose count does *not* confirm the window is spent raises, since
        that is a page that failed to render rather than an empty window.

        If a row fails to parse, the raised exception's
        :attr:`~amazonorders.exception.AmazonOrdersError.meta` carries ``partial_orders`` (the
        Orders parsed before the failure), mirroring the resume metadata on the fetching walks.

        :param html: The Order history page HTML to parse.
        :param config: The config providing the selectors and entity classes used for parsing.
        :param start_index: The index of the first Order on this page within its window, used both
            to populate :attr:`~amazonorders.entity.order.Order.index` and in the empty-window
            check against the header count.
        :return: The parsed page.
        """
        parsed = BeautifulSoup(html, config.bs4_parser)

        header_count = AmazonOrders._parse_header_count(parsed, config)

        # An encrypted page still renders card shells, so this must be checked before row parsing
        if util.select_one(parsed, config.selectors.ORDER_HISTORY_CSD_ENCRYPTED_SELECTOR):
            return OrderHistoryPageResult(orders=[],
                                          header_count=header_count,
                                          next_page_url=None,
                                          page_type="csd_encrypted")

        order_tags = util.select(parsed, config.selectors.ORDER_HISTORY_ENTITY_SELECTOR)

        if not order_tags:
            if header_count is not None and header_count <= start_index:
                return OrderHistoryPageResult(orders=[],
                                              header_count=header_count,
                                              next_page_url=None,
                                              page_type="empty_window")

            not_order_history_selectors = [config.selectors.SIGN_IN_FORM_SELECTOR,
                                           config.selectors.CAPTCHA_1_FORM_SELECTOR,
                                           config.selectors.ACIC_CHALLENGE_SELECTOR,
                                           config.selectors.AWS_WAF_CHALLENGE_SCRIPT_SELECTOR] + \
                list(config.selectors.CAPTCHA_2_FORM_SELECTOR)
            if util.select_one(parsed, not_order_history_selectors):
                return OrderHistoryPageResult(orders=[],
                                              header_count=header_count,
                                              next_page_url=None,
                                              page_type="not_order_history")

            raise AmazonOrdersError("Could not parse Order history. Check if Amazon changed the HTML.")

        orders: List[Order] = []
        for i, order_tag in enumerate(order_tags):
            try:
                orders.append(config.order_cls(order_tag, config, index=start_index + i))
            except AmazonOrdersError as e:
                e.meta = {**{"partial_orders": orders}, **(e.meta or {})}
                raise

        return OrderHistoryPageResult(orders=orders,
                                      header_count=header_count,
                                      next_page_url=AmazonOrders._parse_next_page_url(parsed, config),
                                      page_type="orders")

    def get_order(self,
                  order_id: str,
                  clone: Optional[Order] = None) -> Order:
        """
        Get the full details for a given Amazon Order ID.

        :param order_id: The Amazon Order ID to lookup.
        :param clone: If a partially populated version of the Order has already been fetched from history.
        :return: The requested Order.
        """
        if not self.amazon_session.is_authenticated:
            raise AmazonOrdersError("Call AmazonSession.login() to authenticate first.")

        meta = {"index": clone.index} if clone else None

        order_details_response = self.amazon_session.get(
            f"{self.config.constants.ORDER_DETAILS_URL}?orderID={order_id}")
        self.amazon_session.check_response(order_details_response, meta=meta)

        response_url = order_details_response.response.url
        if not response_url.startswith(self.config.constants.ORDER_DETAILS_URL):
            if self._is_whole_foods_details_url(response_url):
                # GET already followed the redirect, so order_details_response is the FOPO/receipt page.
                return self._get_whole_foods_order(order_details_response, order_number=order_id, clone=clone)

            raise AmazonOrdersNotFoundError(f"Amazon redirected, which likely means Order {order_id} was not found.",
                                            meta=meta)

        order_details_tag = util.select_one(order_details_response.parsed,
                                            self.config.selectors.ORDER_DETAILS_ENTITY_SELECTOR)

        if not order_details_tag:
            raise AmazonOrdersError(f"Could not parse details for Order {order_id}. Check if Amazon changed the HTML.")

        order: Order = self.config.order_cls(order_details_tag, self.config, full_details=True, clone=clone,
                                             order_number=order_id)

        return order

    def get_invoice(self,
                    order_id: str) -> util.AmazonSessionResponse:
        """
        Get the print-friendly invoice page for a given Amazon Order ID, returning the response
        (including its parsed HTML) so callers can render or print the page.

        :param order_id: The Amazon Order ID to lookup.
        :return: The invoice page response.
        """
        if not self.amazon_session.is_authenticated:
            raise AmazonOrdersError("Call AmazonSession.login() to authenticate first.")

        invoice_response = self.amazon_session.get(
            f"{self.config.constants.ORDER_INVOICE_URL}?orderID={order_id}")
        self.amazon_session.check_response(invoice_response)

        if not invoice_response.response.url.startswith(self.config.constants.ORDER_INVOICE_URL):
            raise AmazonOrdersNotFoundError(f"Amazon redirected, which likely means Order {order_id} was not found.")

        return invoice_response

    def get_order_history(self,
                          year: Optional[int] = None,
                          start_index: Optional[int] = None,
                          full_details: bool = False,
                          keep_paging: bool = True,
                          time_filter: Optional[str] = None,
                          order_filter: Optional[str] = None) -> List[Order]:
        """
        Get the Amazon Order history for a given time period.

        :param year: The year for which to get history. May not be combined with ``time_filter``.
            Defaults to the current year if neither ``year`` nor ``time_filter`` is specified.
        :param start_index: The index of the Order from which to start fetching in the history. See
            :attr:`~amazonorders.entity.order.Order.index` to correlate, or if a call to this method previously errored
            out, see ``index`` in the exception's :attr:`~amazonorders.exception.AmazonOrdersError.meta` to continue
            paging where it left off.
        :param full_details: Get the full details for each Order in the history. This will execute an additional
            request per Order.
        :param keep_paging: ``False`` if only one page should be fetched.
        :param time_filter: The time filter to use. Supported values are ``"last30"`` (last 30 days),
            ``"months-3"`` (past 3 months), or ``"year-YYYY"`` (specific year). If provided, this takes
            precedence over the ``year`` parameter.
        :param order_filter: The order type filter to use. If provided, appended alongside the time filter.
        :return: A list of the requested Orders.
        """
        if not self.amazon_session.is_authenticated:
            raise AmazonOrdersError("Call AmazonSession.login() to authenticate first.")

        if time_filter and year:
            raise AmazonOrdersError("Only one of 'year' or 'time_filter' may be used at a time.")

        self.last_history_pull = None

        # Determine the filter value to use
        if time_filter:
            # Validate time_filter value
            valid_filters = ["last30", "months-3"]
            is_year_filter = time_filter.startswith("year-") and time_filter[5:].isdigit()
            if time_filter not in valid_filters and not is_year_filter:
                raise AmazonOrdersError(
                    f"Invalid time_filter '{time_filter}'. "
                    f"Valid values are 'last30', 'months-3', or 'year-YYYY'."
                )
            filter_value = time_filter
        else:
            if year is None:
                year = datetime.date.today().year
            filter_value = f"year-{year}"

        optional_start_index = f"&startIndex={start_index}" if start_index else ""
        optional_order_filter = (
            f"&{self.config.constants.ORDER_FILTER_QUERY_PARAM}={quote(order_filter, safe='')}"
            if order_filter else ""
        )
        next_page: Optional[str] = (
            "{url}?{query_param}={filter_value}{optional_order_filter}{optional_start_index}"
        ).format(
            url=self.config.constants.ORDER_HISTORY_URL,
            query_param=self.config.constants.HISTORY_FILTER_QUERY_PARAM,
            filter_value=filter_value,
            optional_order_filter=optional_order_filter,
            optional_start_index=optional_start_index
        )

        current_index = int(start_index) if start_index else 0

        return asyncio.run(self._build_orders_async(next_page, keep_paging, full_details, current_index))

    async def _build_orders_async(self,
                                  next_page: Optional[str],
                                  keep_paging: bool,
                                  full_details: bool,
                                  current_index: int) -> List[Order]:
        order_tasks = []
        pages_walked = 0
        header_count = None
        stop_reason = ""

        while next_page:
            page_response = self.amazon_session.get(next_page)
            self.amazon_session.check_response(page_response, meta={"index": current_index})

            pages_walked += 1

            page_count = self._parse_header_count(page_response.parsed, self.config)
            if pages_walked == 1:
                header_count = page_count

            order_tags = util.select(page_response.parsed,
                                     self.config.selectors.ORDER_HISTORY_ENTITY_SELECTOR)

            if not order_tags:
                if page_count is not None and page_count <= current_index:
                    stop_reason = "empty_history"
                    break
                else:
                    raise AmazonOrdersError("Could not parse Order history. Check if Amazon changed the HTML.")

            for order_tag in order_tags:
                order_tasks.append(self._async_wrapper(self._build_order, order_tag, full_details, current_index))

                current_index += 1

            next_page = None
            if keep_paging:
                next_page = self._parse_next_page_url(page_response.parsed, self.config)
                if not next_page:
                    stop_reason = "no_more_pages"
                    logger.debug("No next page")
            else:
                stop_reason = "single_page_requested"
                logger.debug("keep_paging is False, not paging")

        orders = await asyncio.gather(*order_tasks)

        self.last_history_pull = OrderHistoryPullResult(pages_walked=pages_walked,
                                                        rows_parsed=len(order_tasks),
                                                        header_count=header_count,
                                                        stop_reason=stop_reason)

        return orders

    def _build_order(self,
                     order_tag: List[Tag],
                     full_details: bool,
                     current_index: int) -> Order:
        order: Order = self.config.order_cls(order_tag, self.config, index=current_index)

        if full_details:
            if order.is_whole_foods:
                link = order.order_details_link or ""
                if self._is_whole_foods_details_url(link):
                    details_response = self.amazon_session.get(link)
                    self.amazon_session.check_response(details_response, meta={"index": order.index})
                    order = self._get_whole_foods_order(details_response, order_number=order.order_number,
                                                        clone=order)
                else:
                    logger.warning(f"Order {order.order_number} is a Whole Foods Market order whose details "
                                   f"page could not be located, so it was left partially populated.")
            elif len(util.select(order.parsed, self.config.selectors.ORDER_SKIP_ITEMS)) > 0:
                logger.warning(f"Order {order.order_number} was partially populated, "
                               f"since it is an unsupported Order type.")
            elif not order.order_number:
                logger.warning(f"Order at index {current_index} was partially populated, "
                               f"since its order number could not be parsed from the history page.")
            else:
                order = self.get_order(order.order_number, clone=order)

        return order

    def _is_whole_foods_details_url(self,
                                    url: str) -> bool:
        return any(route in url for route in self.config.constants.WHOLE_FOODS_DETAILS_ROUTES)

    def _get_whole_foods_order(self,
                               details_response: util.AmazonSessionResponse,
                               order_number: Optional[str] = None,
                               clone: Optional[Order] = None) -> Order:
        """Builds an Order from an already-fetched Whole Foods Market details page response."""
        details_tag = util.select_one(details_response.parsed,
                                      self.config.selectors.ORDER_DETAILS_ENTITY_SELECTOR)

        if not details_tag:
            if clone:
                logger.warning(f"Could not parse Whole Foods Market details for Order {clone.order_number}, "
                               f"so it was left partially populated.")
                return clone

            raise AmazonOrdersError(f"Could not parse Whole Foods Market details for Order {order_number}. "
                                    f"Check if Amazon changed the HTML.")

        return self.config.order_cls(details_tag, self.config, full_details=True, clone=clone,
                                     order_number=order_number)

    async def _async_wrapper(self,
                             func: Callable,
                             *args: Any) -> Order:
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.thread_pool_size) as pool:
            result = await loop.run_in_executor(pool, func, *args)
        return result
