__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import logging
import re
from typing import List, Optional, TypeVar

from bs4 import Tag

from amazonorders import util
from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.parsable import Parsable
from amazonorders.entity.wish_list_item import WishListItem
from amazonorders.exception import AmazonOrdersError

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: The list ID inside a nav entry's anchor id (``wl-list-link-<listId>``).
ENTRY_LINK_ID_REGEX = re.compile(r"^wl-list-link-(.+)$")
#: The profile ID inside a collaborator row's name span id (``manage-collaborator-profile_<profileId>``).
COLLABORATOR_PROFILE_ID_REGEX = re.compile(r"^manage-collaborator-profile_(.+)$")
#: The route of an Alexa shopping list, which the Lists nav indexes alongside wish lists but which
#: renders on its own page.
ALEXA_LIST_ROUTE = "/gp/alexa-shopping-list"


class WishListCollaborator(Parsable):
    """
    A member of a collaborative Amazon List, as the list page's "List members" rows render them.
    """

    def __init__(self,
                 parsed: Tag,
                 config: AmazonOrdersConfig) -> None:
        super().__init__(parsed, config)

        #: The member's public profile name.
        self.name: Optional[str] = self.safe_parse(self._parse_name)
        #: The member's Amazon profile ID (``amzn1.account.…``).
        self.profile_id: Optional[str] = self.safe_parse(self._parse_profile_id)
        #: Whether the member owns the list (the page labels exactly one row "Owner").
        self.is_owner: bool = self.safe_parse(self._parse_is_owner)

    def __repr__(self) -> str:
        return f"<WishListCollaborator \"{self.name}\"{' (owner)' if self.is_owner else ''}>"

    def __str__(self) -> str:  # pragma: no cover
        return f"WishListCollaborator {self.name}{' (owner)' if self.is_owner else ''}"

    def _parse_name(self) -> Optional[str]:
        tag = util.select_one(self.parsed, self.config.selectors.FIELD_WISH_LIST_COLLABORATOR_NAME_SELECTOR)

        return re.sub(r"\s+", " ", tag.text).strip() or None if tag is not None else None

    def _parse_profile_id(self) -> Optional[str]:
        tag = util.select_one(self.parsed, self.config.selectors.FIELD_WISH_LIST_COLLABORATOR_NAME_SELECTOR)
        match = COLLABORATOR_PROFILE_ID_REGEX.match(str(tag.get("id") or "")) if tag is not None else None

        return match.group(1) if match else None

    def _parse_is_owner(self) -> bool:
        tag = util.select_one(self.parsed, self.config.selectors.FIELD_WISH_LIST_COLLABORATOR_ROLE_SELECTOR)

        return tag is not None and tag.text.strip().lower() == "owner"


class WishList(Parsable):
    """
    An Amazon List (wish list), as the Lists page's left nav indexes it: ``parsed`` is the list's nav entry,
    which gives :attr:`list_id`, :attr:`name`, :attr:`privacy`, and the "Default List" and "Collaborator"
    badges. When the entity is built from the page of the list itself (as
    :func:`~amazonorders.lists.AmazonLists.get_list` does), the page's header and items also populate
    :attr:`collaborators`, :attr:`items_filter`, :attr:`items_sort`, and :attr:`items`; from the index alone
    those stay ``None``.

    The nav also indexes the account's Alexa shopping list, which is not a wish list (it renders on its own
    page, which this library does not parse); it is returned with :attr:`list_type` ``AlexaList`` so the index
    is complete.
    """

    def __init__(self,
                 parsed: Tag,
                 config: AmazonOrdersConfig,
                 page: Optional[Tag] = None) -> None:
        super().__init__(parsed, config)

        #: The list's ID (the ``colid``).
        self.list_id: str = self.safe_parse(self._parse_list_id)
        #: The list's name.
        self.name: Optional[str] = self.safe_parse(self._parse_name)
        #: The list's privacy as the nav labels it (``Private``, ``Shared``, or ``Public``).
        self.privacy: Optional[str] = self.safe_parse(self._parse_privacy)
        #: ``WishList`` for a wish list, ``AlexaList`` for the Alexa shopping list the nav also indexes.
        self.list_type: Optional[str] = self.safe_parse(self._parse_list_type)
        #: Whether this is the account's default list.
        self.is_default: bool = self.safe_parse(self._parse_is_default)
        #: Whether the list is collaborative (shared with other members who can add and remove items).
        self.is_collaborative: bool = self.safe_parse(self._parse_is_collaborative)
        #: The list's page link.
        self.link: Optional[str] = self.safe_simple_parse(
            selector=self.config.selectors.FIELD_WISH_LIST_ENTRY_LINK_SELECTOR,
            attr_name="href"
        )

        #: The members of a collaborative list, as its page's "List members" rows list them. ``None`` when the
        #: entity was built from the index alone; empty when the list page carries no member rows (a list
        #: that is not collaborative).
        self.collaborators: Optional[List[WishListCollaborator]] = None
        #: Which items the list page rendered: ``all``, ``unpurchased``, or ``purchased``. The filter is a
        #: setting of the list at Amazon, so a page filtered to ``unpurchased`` omits purchased items
        #: entirely. ``None`` when the entity was built from the index alone.
        self.items_filter: Optional[str] = None
        #: The order the list page rendered its items in (``date-added``, ``custom``, ``priority``,
        #: ``price-asc``, or ``price-desc``). ``None`` when the entity was built from the index alone.
        self.items_sort: Optional[str] = None
        #: The list's items, in page order. ``None`` when the entity was built from the index alone.
        self.items: Optional[List[WishListItem]] = None

        if page is not None:
            self._populate_from_page(page)

    def __repr__(self) -> str:
        return f"<WishList {self.list_id}: \"{self.name}\">"

    def __str__(self) -> str:  # pragma: no cover
        return f"WishList {self.list_id}: {self.name}"

    def _populate_from_page(self,
                            page: Tag) -> None:
        """
        Populate the fields only the list's own page carries: its members, the filter and sort it rendered
        with, and the name as the header renders it (the nav entry truncates nothing, but the header is
        authoritative).

        :param page: The parsed list page.
        """
        header_tag = util.select_one(page, self.config.selectors.WISH_LIST_HEADER_SELECTOR)
        if header_tag is not None:
            name_tag = util.select_one(header_tag, self.config.selectors.FIELD_WISH_LIST_NAME_SELECTOR)
            if name_tag is not None and name_tag.text.strip():
                self.name = re.sub(r"\s+", " ", name_tag.text).strip()

            row_tags = util.select(header_tag, self.config.selectors.WISH_LIST_COLLABORATOR_ROW_SELECTOR)
            self.collaborators = [WishListCollaborator(row_tag, self.config) for row_tag in row_tags]
            if self.collaborators:
                self.is_collaborative = True

        filter_tag = util.select_one(page, self.config.selectors.FIELD_WISH_LIST_FILTER_SELECTOR)
        self.items_filter = str(filter_tag.get("value") or "").strip() or None if filter_tag is not None else None
        sort_tag = util.select_one(page, self.config.selectors.FIELD_WISH_LIST_SORT_SELECTOR)
        self.items_sort = str(sort_tag.get("value") or "").strip() or None if sort_tag is not None else None

        self.items = []

    def _require(self,
                 value: Optional[T],
                 name: str) -> Optional[T]:
        if value is not None:
            return value

        err_msg = (f"WishList.{name} did not populate, but it's required. "
                   "Check if Amazon changed the HTML.")
        if not self.config.warn_on_missing_required_field:
            raise AmazonOrdersError(err_msg)

        logger.warning(err_msg)
        return None

    def _link_tag(self) -> Optional[Tag]:
        return util.select_one(self.parsed, self.config.selectors.FIELD_WISH_LIST_ENTRY_LINK_SELECTOR)

    def _parse_list_id(self) -> Optional[str]:
        link_tag = self._link_tag()
        match = ENTRY_LINK_ID_REGEX.match(str(link_tag.get("id") or "")) if link_tag is not None else None

        return self._require(match.group(1) if match else None, "list_id")

    def _parse_name(self) -> Optional[str]:
        tag = util.select_one(self.parsed, self.config.selectors.FIELD_WISH_LIST_ENTRY_TITLE_SELECTOR)

        return re.sub(r"\s+", " ", tag.text).strip() or None if tag is not None else None

    def _parse_privacy(self) -> Optional[str]:
        tag = util.select_one(self.parsed, self.config.selectors.FIELD_WISH_LIST_ENTRY_PRIVACY_SELECTOR)

        return re.sub(r"\s+", " ", tag.text).strip() or None if tag is not None else None

    def _parse_list_type(self) -> Optional[str]:
        link_tag = self._link_tag()
        href = str(link_tag.get("href") or "") if link_tag is not None else ""
        if not href:
            return None

        return "AlexaList" if ALEXA_LIST_ROUTE in href else "WishList"

    def _parse_label(self) -> str:
        tag = util.select_one(self.parsed, self.config.selectors.FIELD_WISH_LIST_ENTRY_LABEL_SELECTOR)

        return tag.text.strip().lower() if tag is not None else ""

    def _parse_is_default(self) -> bool:
        return "default" in self._parse_label()

    def _parse_is_collaborative(self) -> bool:
        if util.select_one(self.parsed, self.config.selectors.FIELD_WISH_LIST_ENTRY_COLLABORATIVE_ICON_SELECTOR):
            return True

        return "collaborator" in self._parse_label()
