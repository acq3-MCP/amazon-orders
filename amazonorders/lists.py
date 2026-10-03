__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import logging
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Tag

from amazonorders import util
from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.wish_list import WishList
from amazonorders.entity.wish_list_item import WishListItem
from amazonorders.exception import AmazonOrdersError, AmazonOrdersNotFoundError
from amazonorders.session import AmazonSession

logger = logging.getLogger(__name__)


class WishListPageResult:
    """
    The parsed contents of a Lists page, as returned by
    :func:`~amazonorders.lists.AmazonLists.parse_wish_list_page`.
    """

    def __init__(self,
                 wish_list: Optional[WishList],
                 lists: List[WishList],
                 next_page_url: Optional[str],
                 page_type: str,
                 next_page_off_origin: bool = False) -> None:
        #: The list the page shows, with :attr:`~amazonorders.entity.wish_list.WishList.items` holding the
        #: items this page rendered (the first batch; see :attr:`next_page_url`). ``None`` unless
        #: :attr:`page_type` is ``wish_list``.
        self.wish_list: Optional[WishList] = wish_list
        #: Every list the page's nav indexes, in nav order (the page's own list among them). Empty unless
        #: :attr:`page_type` is ``wish_list``.
        self.lists: List[WishList] = lists
        #: The items the page rendered, in page order: :attr:`wish_list`'s items on a list page, or the
        #: items of an items batch.
        self.items: List[WishListItem] = wish_list.items if wish_list is not None and wish_list.items else []
        #: The absolute URL of the "See More" control, which serves the next batch of items. ``None`` at the end
        #: of the list (the last batch renders an end-of-list marker in place of the control), and ``None`` when
        #: the control's URL names another origin (see :attr:`next_page_off_origin`).
        self.next_page_url: Optional[str] = next_page_url
        #: Whether the page carried a "See More" URL on another origin, which is dropped rather than followed:
        #: a page must not send the session anywhere but the site.
        self.next_page_off_origin: bool = next_page_off_origin
        #: What the page is: ``wish_list`` (a list page, with its nav, header, and first batch of items),
        #: ``items`` (a batch of items with no nav or header, as the "See More" control serves), or
        #: ``not_wish_list`` (a sign-in, Captcha, or challenge page; the supplied HTML is not a Lists page
        #: at all).
        self.page_type: str = page_type

    def __repr__(self) -> str:
        return f"<WishListPageResult: \"{self.page_type}\", {len(self.lists)} lists, {len(self.items)} items>"

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.page_type}: {len(self.lists)} lists, {len(self.items)} items"


class WishListPullResult:
    """
    Metadata about a completed :func:`~amazonorders.lists.AmazonLists.get_list` pull.
    """

    def __init__(self,
                 pages_walked: int,
                 items_parsed: int,
                 stop_reason: str) -> None:
        #: How many pages (the list page and each "See More" batch) were fetched.
        self.pages_walked: int = pages_walked
        #: How many items were parsed.
        self.items_parsed: int = items_parsed
        #: Why the walk stopped: ``no_more_pages`` (the end of the list), ``single_page_requested``
        #: (``keep_paging`` was ``False``), or ``off_origin_next_page`` (the "See More" URL named another
        #: origin and was not followed, so the items are those of the pages before it).
        self.stop_reason: str = stop_reason

    def __repr__(self) -> str:
        return f"<WishListPullResult: {self.pages_walked} pages, {self.items_parsed} items, \"{self.stop_reason}\">"

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.pages_walked} pages, {self.items_parsed} items, {self.stop_reason}"


def _parse_items(parsed: Tag,
                 config: AmazonOrdersConfig) -> Tuple[List[WishListItem], Optional[str], bool]:
    """
    Parse the items a page or batch rendered, and the URL of the next batch.

    If an item fails to parse, the raised exception's
    :attr:`~amazonorders.exception.AmazonOrdersError.meta` carries ``partial_items`` (the items parsed
    before the failure).

    :param parsed: The parsed page or batch.
    :param config: The config to use.
    :return: The items in page order, the absolute URL of the next batch (``None`` at the end of the list, or
        when it names another origin), and whether it named another origin.
    """
    items: List[WishListItem] = []
    for item_tag in util.select(parsed, config.selectors.WISH_LIST_ITEM_SELECTOR):
        try:
            items.append(WishListItem(item_tag, config))
        except AmazonOrdersError as e:
            e.meta = {**{"partial_items": items}, **(e.meta or {})}
            raise

    next_page_url, off_origin = _parse_next_page_url(parsed, config)

    return items, next_page_url, off_origin


def _parse_next_page_url(parsed: Tag,
                         config: AmazonOrdersConfig) -> Tuple[Optional[str], bool]:
    """
    Find the URL of the next batch of items, or ``None`` at the end of the list.

    The end is the end-of-list marker the last batch renders in place of a "See More" control. Short
    of it, the control's no-JS anchor carries the URL, and failing that its JS twin, the last
    ``showMoreUrl`` input (a scrolled page keeps one per batch loaded, so the first is stale); an
    input whose URL carries an empty pagination token is the last batch's and also means the end.
    A URL on another origin is dropped (:func:`~amazonorders.util.resolve_site_url`) and reported.

    :param parsed: The parsed page or batch.
    :param config: The config to use.
    :return: The absolute URL of the next batch (``None`` at the end of the list, or when it names another
        origin), and whether it named another origin.
    """
    if util.select_one(parsed, config.selectors.WISH_LIST_END_OF_LIST_SELECTOR) is not None:
        return None, False

    next_page_url = None
    link_tag = util.select_one(parsed, config.selectors.WISH_LIST_NEXT_PAGE_LINK_SELECTOR)
    if link_tag is not None and link_tag.get("href"):
        next_page_url = str(link_tag["href"])
    else:
        input_tags = util.select(parsed, config.selectors.WISH_LIST_NEXT_PAGE_INPUT_SELECTOR)
        if input_tags and input_tags[-1].get("value"):
            next_page_url = str(input_tags[-1]["value"])

    if not next_page_url:
        return None, False

    query = parse_qs(urlparse(next_page_url).query, keep_blank_values=True)
    if "paginationToken" in query and not any(query["paginationToken"]):
        return None, False

    resolved = util.resolve_site_url(next_page_url, config)

    return resolved, resolved is None


def _parse_wish_list_page(parsed: Tag,
                          config: AmazonOrdersConfig) -> WishListPageResult:
    """
    Classify a parsed Lists page and parse its lists and items.

    A page with neither the Lists nav, a batch of items, nor a recognizable sign-in or challenge
    page raises, since that is a page that failed to render rather than an empty list. If an item
    fails to parse, the raised exception's :attr:`~amazonorders.exception.AmazonOrdersError.meta`
    carries ``partial_items`` (the items parsed before the failure).

    :param parsed: The parsed page.
    :param config: The config to use.
    :return: The parsed page.
    """
    nav_tag = util.select_one(parsed, config.selectors.WISH_LIST_NAV_SELECTOR)

    if nav_tag is None:
        if util.select_one(parsed, config.selectors.AUTH_CHALLENGE_PAGE_SELECTORS):
            return WishListPageResult(wish_list=None, lists=[], next_page_url=None, page_type="not_wish_list")

        if util.select_one(parsed, config.selectors.WISH_LIST_ITEM_SELECTOR):
            items, next_page_url, off_origin = _parse_items(parsed, config)
            result = WishListPageResult(wish_list=None, lists=[], next_page_url=next_page_url, page_type="items",
                                        next_page_off_origin=off_origin)
            result.items = items
            return result

        raise AmazonOrdersError("Could not parse the Lists page. Check if Amazon changed the HTML.")

    lists: List[WishList] = []
    wish_list: Optional[WishList] = None
    for entry_tag in util.select(nav_tag, config.selectors.WISH_LIST_NAV_ENTRY_SELECTOR):
        lists.append(WishList(entry_tag, config))

    selected_tag = util.select_one(nav_tag, config.selectors.WISH_LIST_NAV_SELECTED_ENTRY_SELECTOR)
    if selected_tag is None:
        # Fall back to the list the header names, when the nav marks none as selected
        id_tag = util.select_one(parsed, config.selectors.FIELD_WISH_LIST_ID_SELECTOR)
        page_list_id = str(id_tag.get("value") or "").strip() if id_tag is not None else ""
        for entry_tag in util.select(nav_tag, config.selectors.WISH_LIST_NAV_ENTRY_SELECTOR):
            if page_list_id and util.select_one(entry_tag, f"a#wl-list-link-{page_list_id}") is not None:
                selected_tag = entry_tag
                break

    next_page_url = None
    off_origin = False
    if selected_tag is not None:
        wish_list = WishList(selected_tag, config, page=parsed)
        items, next_page_url, off_origin = _parse_items(parsed, config)
        wish_list.items = items

    return WishListPageResult(wish_list=wish_list, lists=lists, next_page_url=next_page_url, page_type="wish_list",
                              next_page_off_origin=off_origin)


class AmazonLists:
    """
    Using an authenticated :class:`~amazonorders.session.AmazonSession`, can be used to query Amazon
    for the account's Lists (wish lists) and their items. Read-only: adding, buying, and marking items
    purchased are left to Amazon's own pages.

    A list is the unit of intent here. The list page carries no per-item attribution, so on a
    collaborative list nothing says which member added an item; a list kept for one purpose (one
    member's requests, say) is how that purpose is read back. Amazon marks an item purchased when it
    is bought through the item's :attr:`~amazonorders.entity.wish_list_item.WishListItem.link`, so a
    list filtered to unpurchased items is a queue that clears itself.
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

        #: Metadata about the last successful :func:`get_list` pull. ``None`` until a pull completes, and
        #: reset to ``None`` when a pull starts, so it stays ``None`` after a failed pull.
        self.last_list_pull: Optional[WishListPullResult] = None

    def get_lists(self) -> List[WishList]:
        """
        Get every list the account's Lists page indexes, in nav order, with the fields the index carries
        (ID, name, privacy, and the default and collaborative flags); the items of a list come from
        :func:`get_list`.

        :return: The lists (empty when the account has none).
        """
        if not self.amazon_session.is_authenticated:
            raise AmazonOrdersError("Call AmazonSession.login() to authenticate first.")

        page_response = self.amazon_session.get(self.config.constants.WISH_LISTS_URL)
        self.amazon_session.check_response(page_response)

        result = _parse_wish_list_page(page_response.parsed, self.config)
        if result.page_type != "wish_list":
            raise AmazonOrdersError("Amazon rendered a sign-in or challenge page instead of the Lists page.")

        return result.lists

    def get_list(self,
                 list_id: str,
                 keep_paging: bool = True,
                 next_page_url: Optional[str] = None) -> WishList:
        """
        Get a list with its items. The list page renders the first batch of items and serves the rest from
        its "See More" control, which is followed until the end of the list unless ``keep_paging`` is
        ``False``.

        On success, :attr:`last_list_pull` is populated with metadata about the pull. On a mid-pagination
        failure, the raised :class:`~amazonorders.exception.AmazonOrdersError`'s
        :attr:`~amazonorders.exception.AmazonOrdersError.meta` carries ``next_page_url`` (where paging
        stopped) and ``partial_items`` (the items fetched before the failure). Resuming with
        ``next_page_url`` fetches the remaining batches on to a list entity built from the list page again.

        :param list_id: The list's ID.
        :param keep_paging: ``False`` if only the list page's first batch of items should be fetched.
        :param next_page_url: If a call to this method previously errored out, passing the exception's
            :attr:`~amazonorders.exception.AmazonOrdersError.meta` value for ``next_page_url`` will
            continue paging where it left off.
        :return: The list, with its items in page order.
        """
        if not self.amazon_session.is_authenticated:
            raise AmazonOrdersError("Call AmazonSession.login() to authenticate first.")

        self.last_list_pull = None

        wish_list, first_page_next_url, off_origin = self._get_list_page(list_id)
        items: List[WishListItem] = wish_list.items if wish_list.items is not None else []
        pages_walked = 1
        stop_reason = "off_origin_next_page" if off_origin else ""

        if next_page_url is None:
            next_page_url = first_page_next_url
        else:
            stop_reason = ""

        while next_page_url:
            if not keep_paging:
                stop_reason = "single_page_requested"
                break

            meta = {"next_page_url": next_page_url, "partial_items": items}

            page_response = self.amazon_session.get(next_page_url)
            self.amazon_session.check_response(page_response, meta=meta)

            pages_walked += 1

            try:
                page_items, next_page_url, off_origin = _parse_items(page_response.parsed, self.config)
            except AmazonOrdersError as e:
                # The batch's partial items follow the items of the pages before it
                e.meta = {**(e.meta or {}), **meta,
                          "partial_items": items + list((e.meta or {}).get("partial_items", []))}
                raise

            items.extend(page_items)
            if off_origin:
                stop_reason = "off_origin_next_page"

        if not stop_reason:
            stop_reason = "no_more_pages"

        wish_list.items = items

        self.last_list_pull = WishListPullResult(pages_walked=pages_walked,
                                                 items_parsed=len(items),
                                                 stop_reason=stop_reason)

        return wish_list

    def _get_list_page(self,
                       list_id: str) -> Tuple[WishList, Optional[str], bool]:
        """
        Fetch and parse the page of a list, verifying it is the list asked for: Amazon answers an unknown or
        inaccessible list ID with another list's page rather than an error.

        :param list_id: The list's ID.
        :return: The list, with the page's first batch of items, the URL of the next batch, and whether that URL
            named another origin.
        """
        page_response = self.amazon_session.get(f"{self.config.constants.WISH_LISTS_URL}/{list_id}")
        self.amazon_session.check_response(page_response)

        result = _parse_wish_list_page(page_response.parsed, self.config)
        if result.page_type != "wish_list":
            raise AmazonOrdersError("Amazon rendered a sign-in or challenge page instead of the Lists page.")
        if result.wish_list is None:
            raise AmazonOrdersError("Could not tell which list the Lists page shows. "
                                    "Check if Amazon changed the HTML.")
        if result.wish_list.list_id != list_id:
            raise AmazonOrdersNotFoundError(f"Amazon rendered list {result.wish_list.list_id} instead of list "
                                            f"{list_id}, which may not exist or may not be shared with this account.")

        return result.wish_list, result.next_page_url, result.next_page_off_origin

    @staticmethod
    def parse_wish_list_page(html: str,
                             config: AmazonOrdersConfig) -> WishListPageResult:
        """
        Parse an already-fetched Lists page into its lists and items, without a session driving the fetch.

        The result's :attr:`~amazonorders.lists.WishListPageResult.page_type` distinguishes a list page
        (``wish_list``: the nav indexing every list, the page's own list with its first batch of items, and
        the "See More" URL of the next batch) from a batch of items alone (``items``, as the "See More"
        control serves) and from a page that is not a Lists page at all (``not_wish_list``: sign-in,
        Captcha, or challenge pages). A page with none of these raises, since that is a page that failed
        to render rather than an empty list; a list with no items is a ``wish_list`` page whose list has
        no items.

        If an item fails to parse, the raised exception's
        :attr:`~amazonorders.exception.AmazonOrdersError.meta` carries ``partial_items`` (the items
        parsed before the failure).

        :param html: The Lists page (or items batch) HTML to parse.
        :param config: The config providing the selectors used for parsing.
        :return: The parsed page.
        """
        parsed = BeautifulSoup(html, config.bs4_parser)

        return _parse_wish_list_page(parsed, config)
