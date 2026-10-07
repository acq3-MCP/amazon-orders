__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

#: Literals in the fork-only parsers that are plumbing, not page text, for the page-text guard in
#: ``test_localization.py``: JSON keys, attribute names, URL patterns, field names, and the page type, stop
#: reason, and meta values the fork's observability reports. Kept apart from upstream's list so syncs don't
#: conflict on it.
FORK_PLUMBING_LITERALS = {
    # Order history: the no-JavaScript fallback parameter, page types, stop reasons, and meta keys
    "disableCsd", "no-js", "orders", "csd_encrypted", "empty_window", "not_order_history", "empty_history",
    "single_page_requested", "off_origin_next_page", "no_more_pages", "partial_orders",
    # Item: the Prime Video GTI in the link path (moving downstream; see the video_gti handoff)
    "/gp/video/detail/(amzn1\\.dv\\.gti\\.[0-9A-Za-z-]+)",
    # PrimePayment: field names in the required-field errors
    "total", "order_number",
    # RewardsBalance: keys of the page's __NEXT_DATA__ JSON
    "pointsBalance", "amount", "points", "balance", "unit", "pointsUnit", "conversionRate", "lastUpdateTime",
    "cardDisplayName", "tail", "brand", "cobrand", "cardVariant", "enrolledWithShopWithPoints",
    # WishList and WishListItem: element ids and attributes, URL patterns, list types, and whitespace handling
    "/gp/alexa-shopping-list", "^wl-list-link-(.+)$", "^manage-collaborator-profile_(.+)$", "list_id", "AlexaList",
    "WishList", "id", "\\s+", "ASIN:([A-Z0-9]{10})", "/dp/([A-Z0-9]{10})", "item_id", "title", "data-price",
    "\\s*:\\s*", "^", "inf", "-inf", "data-itemid", "data-id",
}
