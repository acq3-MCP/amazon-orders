__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import datetime
import json
import os

import responses
from bs4 import BeautifulSoup

from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.wish_list import WishList
from amazonorders.entity.wish_list_item import WishListItem
from amazonorders.exception import AmazonOrdersAuthRedirectError, AmazonOrdersError, AmazonOrdersNotFoundError
from amazonorders.lists import AmazonLists
from amazonorders.session import AmazonSession
from tests.unittestcase import UnitTestCase

SHARED_LIST_ID = "1CCCCCCCCCCCC"
DEFAULT_LIST_ID = "1AAAAAAAAAAAA"
NEXT_PAGE_URL = ("https://www.amazon.com/hz/wishlist/slv/items?filter=all&paginationToken=TOKEN_PAGE_2%3D"
                 "&lid=1CCCCCCCCCCCC&itemsLayout=LIST&sort=purchase-date-added&type=wishlist"
                 "&completeSectionPresent=true")


class TestLists(UnitTestCase):
    def setUp(self):
        super().setUp()

        self.amazon_session = AmazonSession("some-username@gmail.com",
                                            "some-password",
                                            config=self.test_config)

        self.amazon_lists = AmazonLists(self.amazon_session)

    def _read_resource(self, html_file):
        with open(os.path.join(self.RESOURCES_DIR, "lists", html_file), "r", encoding="utf-8") as f:
            return f.read()

    def _given_list_page_exists(self, list_id, html_file):
        return responses.add(
            responses.GET,
            f"{self.test_config.constants.WISH_LISTS_URL}/{list_id}",
            body=self._read_resource(html_file),
            status=200,
        )

    def _item_tag(self, html, item_id):
        parsed = BeautifulSoup(html, self.test_config.bs4_parser)
        return parsed.select_one(f"li[data-itemid='{item_id}']")

    def _entry_tag(self, html, list_id):
        parsed = BeautifulSoup(html, self.test_config.bs4_parser)
        return parsed.select_one(f"a#wl-list-link-{list_id}").find_parent("div", class_="wl-list")

    def test_get_lists_unauthenticated(self):
        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_lists.get_lists()

        self.assertEqual("Call AmazonSession.login() to authenticate first.", str(cm.exception))

    def test_get_list_unauthenticated(self):
        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_lists.get_list(SHARED_LIST_ID)

        self.assertEqual("Call AmazonSession.login() to authenticate first.", str(cm.exception))

    @responses.activate
    def test_get_lists_session_expires(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        auth_redirect_response = self.given_authenticated_url_renders_login()
        signout_response = self.given_logout_response_success()

        # WHEN
        with self.assertRaises(AmazonOrdersAuthRedirectError) as cm:
            self.amazon_lists.get_lists()

        self.assertIn("Amazon redirected to login.", str(cm.exception))
        self.assertFalse(self.amazon_session.is_authenticated)
        self.assertEqual(1, auth_redirect_response.call_count)
        self.assertEqual(1, signout_response.call_count)

    @responses.activate
    def test_get_lists(self):
        # GIVEN the Lists page renders the default list, whose nav indexes every list
        self.amazon_session.is_authenticated = True
        resp = responses.add(
            responses.GET,
            self.test_config.constants.WISH_LISTS_URL,
            body=self._read_resource("wish-list-default.html"),
            status=200,
        )

        # WHEN
        lists = self.amazon_lists.get_lists()

        # THEN every list in nav order, the Alexa shopping list among them
        self.assertEqual(1, resp.call_count)
        self.assertEqual([DEFAULT_LIST_ID, "1BBBBBBBBBBBB", SHARED_LIST_ID, "2DDDDDDDDDDD", "1EEEEEEEEEEEE",
                          "WFFFFFFFFFFF"],
                         [wish_list.list_id for wish_list in lists])
        self.assertEqual(["Wish List", "Household", "Household (shared)", "Alexa List", "New PC", "Shopping List"],
                         [wish_list.name for wish_list in lists])
        self.assertEqual(["Private"] * 6, [wish_list.privacy for wish_list in lists])
        self.assertEqual(["WishList", "WishList", "WishList", "AlexaList", "WishList", "WishList"],
                         [wish_list.list_type for wish_list in lists])
        self.assertEqual([True, False, False, False, False, False], [wish_list.is_default for wish_list in lists])
        self.assertEqual([False, False, True, False, False, False],
                         [wish_list.is_collaborative for wish_list in lists])
        self.assertEqual(f"https://www.amazon.com/hz/wishlist/ls/{SHARED_LIST_ID}?ref_=list_d_wl_lfu_nav_3",
                         lists[2].link)
        self.assertEqual("https://www.amazon.com/gp/alexa-shopping-list?externalId=2DDDDDDDDDDD"
                         "&ref_=list_d_gl_lfu_nav_4", lists[3].link)
        # the index carries no items or members
        for wish_list in lists:
            self.assertIsNone(wish_list.items)
            self.assertIsNone(wish_list.collaborators)
            self.assertIsNone(wish_list.items_filter)
        self.assertEqual(f"<WishList {SHARED_LIST_ID}: \"Household (shared)\">", repr(lists[2]))

    @responses.activate
    def test_get_lists_challenge_page(self):
        # GIVEN a challenge page served with a 200 (a login redirect is handled by the session instead)
        self.amazon_session.is_authenticated = True
        with open(os.path.join(self.RESOURCES_DIR, "auth", "post-signin-captcha-1.html"), "r", encoding="utf-8") as f:
            resp = responses.add(
                responses.GET,
                self.test_config.constants.WISH_LISTS_URL,
                body=f.read(),
                status=200,
            )

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_lists.get_lists()

        # THEN
        self.assertEqual(1, resp.call_count)
        self.assertIn("sign-in or challenge page", str(cm.exception))

    @responses.activate
    def test_get_lists_invalid_page(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        with open(os.path.join(self.RESOURCES_DIR, "500.html"), "r", encoding="utf-8") as f:
            resp = responses.add(
                responses.GET,
                self.test_config.constants.WISH_LISTS_URL,
                body=f.read(),
                status=200,
            )

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_lists.get_lists()

        # THEN
        self.assertEqual(1, resp.call_count)
        self.assertIn("Could not parse the Lists page.", str(cm.exception))

    @responses.activate
    def test_get_list(self):
        # GIVEN a collaborative list whose page renders ten items and whose "See More" serves the last batch
        self.amazon_session.is_authenticated = True
        page_resp = self._given_list_page_exists(SHARED_LIST_ID, "wish-list-shared.html")
        batch_resp = responses.add(
            responses.GET,
            NEXT_PAGE_URL,
            body=self._read_resource("wish-list-shared-batch-last.html"),
            status=200,
        )

        # WHEN
        wish_list = self.amazon_lists.get_list(SHARED_LIST_ID)

        # THEN the list, its members, and every batch's items
        self.assertEqual(1, page_resp.call_count)
        self.assertEqual(1, batch_resp.call_count)
        self.assertEqual(SHARED_LIST_ID, wish_list.list_id)
        self.assertEqual("Household (shared)", wish_list.name)
        self.assertEqual("Private", wish_list.privacy)
        self.assertTrue(wish_list.is_collaborative)
        self.assertFalse(wish_list.is_default)
        self.assertEqual("all", wish_list.items_filter)
        self.assertEqual("date-added", wish_list.items_sort)
        self.assertEqual(["Jane Doe", "John Doe"], [c.name for c in wish_list.collaborators])
        self.assertEqual([True, False], [c.is_owner for c in wish_list.collaborators])
        self.assertEqual("amzn1.account.AAAAAAAAAAAAAAAAAAAAAAAAAAAA", wish_list.collaborators[0].profile_id)
        self.assertEqual("<WishListCollaborator \"Jane Doe\" (owner)>", repr(wish_list.collaborators[0]))
        self.assertEqual(12, len(wish_list.items))
        self.assertEqual("IB096Y9Q2RVX9", wish_list.items[0].item_id)
        self.assertEqual(["I59IY3H8KA5H5", "I5SPXECT3404O"], [item.item_id for item in wish_list.items[10:]])
        self.assertEqual(datetime.date(2026, 5, 12), wish_list.items[11].purchased_date)
        self.assertEqual(2, self.amazon_lists.last_list_pull.pages_walked)
        self.assertEqual(12, self.amazon_lists.last_list_pull.items_parsed)
        self.assertEqual("no_more_pages", self.amazon_lists.last_list_pull.stop_reason)
        self.assertEqual("<WishListPullResult: 2 pages, 12 items, \"no_more_pages\">",
                         repr(self.amazon_lists.last_list_pull))

    @responses.activate
    def test_get_list_single_page(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        page_resp = self._given_list_page_exists(SHARED_LIST_ID, "wish-list-shared.html")
        batch_resp = responses.add(responses.GET, NEXT_PAGE_URL, body="", status=200)

        # WHEN
        wish_list = self.amazon_lists.get_list(SHARED_LIST_ID, keep_paging=False)

        # THEN the "See More" batch is not fetched
        self.assertEqual(1, page_resp.call_count)
        self.assertEqual(0, batch_resp.call_count)
        self.assertEqual(10, len(wish_list.items))
        self.assertEqual("single_page_requested", self.amazon_lists.last_list_pull.stop_reason)
        self.assertEqual(1, self.amazon_lists.last_list_pull.pages_walked)

    @responses.activate
    def test_get_list_resume(self):
        # GIVEN a previous pull stopped at a later batch than the list page's "See More" serves
        self.amazon_session.is_authenticated = True
        page_resp = self._given_list_page_exists(SHARED_LIST_ID, "wish-list-shared.html")
        resume_url = NEXT_PAGE_URL.replace("TOKEN_PAGE_2", "TOKEN_PAGE_3")
        skipped_resp = responses.add(responses.GET, NEXT_PAGE_URL, body="", status=200)
        batch_resp = responses.add(
            responses.GET,
            resume_url,
            body=self._read_resource("wish-list-shared-batch-last.html"),
            status=200,
        )

        # WHEN
        wish_list = self.amazon_lists.get_list(SHARED_LIST_ID, next_page_url=resume_url)

        # THEN the given URL is followed in place of the list page's own
        self.assertEqual(1, page_resp.call_count)
        self.assertEqual(0, skipped_resp.call_count)
        self.assertEqual(1, batch_resp.call_count)
        self.assertEqual(12, len(wish_list.items))

    @responses.activate
    def test_get_list_empty(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        resp = self._given_list_page_exists(DEFAULT_LIST_ID, "wish-list-empty.html")

        # WHEN
        wish_list = self.amazon_lists.get_list(DEFAULT_LIST_ID)

        # THEN a list with no items, not a failure
        self.assertEqual(1, resp.call_count)
        self.assertEqual([], wish_list.items)
        self.assertEqual("unpurchased", wish_list.items_filter)
        self.assertEqual("no_more_pages", self.amazon_lists.last_list_pull.stop_reason)

    @responses.activate
    def test_get_list_wrong_list_rendered(self):
        # GIVEN Amazon answers an unknown list ID with another list's page
        self.amazon_session.is_authenticated = True
        resp = self._given_list_page_exists("1ZZZZZZZZZZZZ", "wish-list-default.html")

        # WHEN
        with self.assertRaises(AmazonOrdersNotFoundError) as cm:
            self.amazon_lists.get_list("1ZZZZZZZZZZZZ")

        # THEN
        self.assertEqual(1, resp.call_count)
        self.assertIn(f"rendered list {DEFAULT_LIST_ID} instead of list 1ZZZZZZZZZZZZ", str(cm.exception))
        self.assertIsNone(self.amazon_lists.last_list_pull)

    @responses.activate
    def test_get_list_challenge_page(self):
        # GIVEN
        self.amazon_session.is_authenticated = True
        with open(os.path.join(self.RESOURCES_DIR, "auth", "post-signin-captcha-1.html"), "r", encoding="utf-8") as f:
            resp = responses.add(
                responses.GET,
                f"{self.test_config.constants.WISH_LISTS_URL}/{SHARED_LIST_ID}",
                body=f.read(),
                status=200,
            )

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_lists.get_list(SHARED_LIST_ID)

        # THEN
        self.assertEqual(1, resp.call_count)
        self.assertIn("sign-in or challenge page", str(cm.exception))

    @responses.activate
    def test_get_list_batch_fails_meta(self):
        # GIVEN the "See More" batch's second item has no title
        self.amazon_session.is_authenticated = True
        self._given_list_page_exists(SHARED_LIST_ID, "wish-list-shared.html")
        batch_html = self._read_resource("wish-list-shared-batch-last.html")
        batch_html = batch_html.replace("id=\"itemName_I5SPXECT3404O\"", "id=\"broken\"")
        responses.add(responses.GET, NEXT_PAGE_URL, body=batch_html, status=200)

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            self.amazon_lists.get_list(SHARED_LIST_ID)

        # THEN the items fetched before the failure, and where paging stopped, ride the exception
        self.assertIn("WishListItem.title did not populate", str(cm.exception))
        self.assertEqual(NEXT_PAGE_URL, cm.exception.meta["next_page_url"])
        self.assertEqual(11, len(cm.exception.meta["partial_items"]))
        self.assertIsNone(self.amazon_lists.last_list_pull)

    def test_parse_wish_list_page(self):
        # WHEN
        result = AmazonLists.parse_wish_list_page(self._read_resource("wish-list-shared.html"), self.test_config)

        # THEN
        self.assertEqual("wish_list", result.page_type)
        self.assertEqual(6, len(result.lists))
        self.assertEqual(SHARED_LIST_ID, result.wish_list.list_id)
        self.assertEqual(10, len(result.items))
        self.assertIs(result.items, result.wish_list.items)
        self.assertEqual(NEXT_PAGE_URL, result.next_page_url)
        self.assertEqual("<WishListPageResult: \"wish_list\", 6 lists, 10 items>", repr(result))

    def test_parse_wish_list_page_scrolled_to_end(self):
        # GIVEN the live DOM of the list scrolled to its end: every batch appended (each with its own
        # scroll-state form, so three showMoreUrl inputs, the first two stale), the end-of-list marker, and
        # the "List members" popover moved out of the header to a modal at the end of the body
        result = AmazonLists.parse_wish_list_page(self._read_resource("wish-list-shared-scrolled.html"),
                                                  self.test_config)

        # THEN every item, no next batch, and the members still found
        self.assertEqual("wish_list", result.page_type)
        self.assertEqual(22, len(result.items))
        self.assertEqual("IB096Y9Q2RVX9", result.items[0].item_id)
        self.assertEqual("I5SPXECT3404O", result.items[-1].item_id)
        self.assertEqual(21, len([item for item in result.items if item.purchased]))
        self.assertIsNone(result.next_page_url)
        self.assertEqual(["Jane Doe", "John Doe"], [c.name for c in result.wish_list.collaborators])
        self.assertTrue(result.wish_list.is_collaborative)

    def test_parse_wish_list_page_last_batch(self):
        # GIVEN the last batch the "See More" control serves: two items, a scroll-state form whose
        # pagination token is empty, and the end-of-list marker in place of another control
        result = AmazonLists.parse_wish_list_page(self._read_resource("wish-list-shared-batch-last.html"),
                                                  self.test_config)

        # THEN
        self.assertEqual("items", result.page_type)
        self.assertIsNone(result.wish_list)
        self.assertEqual(["I59IY3H8KA5H5", "I5SPXECT3404O"], [item.item_id for item in result.items])
        self.assertIsNone(result.next_page_url)

    def test_parse_wish_list_page_empty_pagination_token(self):
        # GIVEN a batch with no end-of-list marker whose only showMoreUrl carries an empty token
        parsed = BeautifulSoup(self._read_resource("wish-list-shared-batch-last.html"), self.test_config.bs4_parser)
        parsed.select_one("div#endOfListMarker").decompose()

        # WHEN
        result = AmazonLists.parse_wish_list_page(str(parsed), self.test_config)

        # THEN the empty token is the end too
        self.assertEqual(2, len(result.items))
        self.assertIsNone(result.next_page_url)

    def test_parse_wish_list_page_last_show_more_input_wins(self):
        # GIVEN a scrolled page with no marker, whose last scroll-state form carries a live token
        parsed = BeautifulSoup(self._read_resource("wish-list-shared-scrolled.html"), self.test_config.bs4_parser)
        parsed.select_one("div#endOfListMarker").decompose()
        input_tags = parsed.select("input[name='showMoreUrl']")
        input_tags[-1]["value"] = input_tags[-1]["value"].replace("paginationToken=&", "paginationToken=TOKEN_PAGE_4&")

        # WHEN
        result = AmazonLists.parse_wish_list_page(str(parsed), self.test_config)

        # THEN the last form's URL is the next batch, not the stale first one
        self.assertIn("paginationToken=TOKEN_PAGE_4&", result.next_page_url)

    def test_parse_wish_list_page_items_batch(self):
        # GIVEN a batch of items with no nav or header, as the "See More" control serves
        parsed = BeautifulSoup(self._read_resource("wish-list-shared.html"), self.test_config.bs4_parser)
        html = str(parsed.select_one("ul#g-items"))

        # WHEN
        result = AmazonLists.parse_wish_list_page(html, self.test_config)

        # THEN
        self.assertEqual("items", result.page_type)
        self.assertIsNone(result.wish_list)
        self.assertEqual([], result.lists)
        self.assertEqual(10, len(result.items))
        self.assertEqual(NEXT_PAGE_URL, result.next_page_url)

    def test_parse_wish_list_page_next_page_from_hidden_input(self):
        # GIVEN a page whose no-JS "See More" anchor is gone but whose JS twin still holds the URL
        parsed = BeautifulSoup(self._read_resource("wish-list-shared.html"), self.test_config.bs4_parser)
        parsed.select_one("a.wl-see-more").decompose()

        # WHEN
        result = AmazonLists.parse_wish_list_page(str(parsed), self.test_config)

        # THEN
        self.assertEqual(NEXT_PAGE_URL, result.next_page_url)

    def test_parse_wish_list_page_selected_entry_from_header(self):
        # GIVEN a nav that marks no entry as selected
        html = self._read_resource("wish-list-shared.html").replace("class=\"wl-list selected\"", "class=\"wl-list\"")

        # WHEN
        result = AmazonLists.parse_wish_list_page(html, self.test_config)

        # THEN the header's list ID picks the entry
        self.assertEqual(SHARED_LIST_ID, result.wish_list.list_id)
        self.assertEqual(10, len(result.items))

    def test_parse_wish_list_page_not_wish_list(self):
        # GIVEN the pages a session-expired or challenged browser fetch supplies instead
        for html_file in ["signin.html", "post-signin-captcha-1.html", "acic-challenge.html", "waf-challenge.html"]:
            with self.subTest(html_file=html_file):
                with open(os.path.join(self.RESOURCES_DIR, "auth", html_file), "r",
                          encoding="utf-8") as f:
                    html = f.read()

                # WHEN
                result = AmazonLists.parse_wish_list_page(html, self.test_config)

                # THEN
                self.assertEqual("not_wish_list", result.page_type)
                self.assertIsNone(result.wish_list)
                self.assertEqual([], result.lists)
                self.assertEqual([], result.items)

    def test_parse_wish_list_page_unrecognized_page(self):
        # GIVEN a page with neither the nav, items, nor a recognizable challenge
        with open(os.path.join(self.RESOURCES_DIR, "500.html"), "r", encoding="utf-8") as f:
            html = f.read()

        # WHEN / THEN
        with self.assertRaises(AmazonOrdersError) as cm:
            AmazonLists.parse_wish_list_page(html, self.test_config)
        self.assertIn("Could not parse the Lists page.", str(cm.exception))

    def test_parse_wish_list_page_partial_items_meta(self):
        # GIVEN the third item has no item ID
        html = self._read_resource("wish-list-shared.html")
        html = html.replace("data-itemid=\"I3JOF2YQGGDZQY\"", "data-itemid=\"\"")

        # WHEN
        with self.assertRaises(AmazonOrdersError) as cm:
            AmazonLists.parse_wish_list_page(html, self.test_config)

        # THEN the items parsed before the failure ride the exception
        self.assertIn("WishListItem.item_id did not populate", str(cm.exception))
        self.assertEqual(["IB096Y9Q2RVX9", "I3W1WERO0RFQBJ"],
                         [item.item_id for item in cm.exception.meta["partial_items"]])

    def test_wish_list_item_unpurchased_with_price_range(self):
        # GIVEN an item not yet purchased, whose offers vary in price
        item = WishListItem(self._item_tag(self._read_resource("wish-list-shared.html"), "IB096Y9Q2RVX9"),
                            self.test_config)

        # THEN
        self.assertEqual("IB096Y9Q2RVX9", item.item_id)
        self.assertEqual(SHARED_LIST_ID, item.list_id)
        self.assertEqual("B0C1G62PNP", item.asin)
        self.assertTrue(item.title.startswith("Scotch-Brite"))
        self.assertEqual(f"https://www.amazon.com/dp/B0C1G62PNP/?coliid=IB096Y9Q2RVX9&colid={SHARED_LIST_ID}"
                         "&psc=0&ref_=list_c_wl_lv_cv_lig_dp_it", item.link)
        self.assertEqual("https://m.media-amazon.com/images/I/512O1Eg-zAL._SS135_.jpg", item.image_link)
        self.assertEqual("Scotch-Brite (Product Bundle)", item.byline)
        self.assertEqual(5.94, item.price)
        self.assertEqual(5.64, item.price_min)
        self.assertEqual(5.94, item.price_max)
        self.assertEqual("Size: 3 Pads (Pack of 2)", item.variation)
        self.assertIsNone(item.note)
        self.assertEqual(1, item.quantity_requested)
        self.assertEqual(0, item.quantity_purchased)
        self.assertEqual(0, item.priority)
        self.assertEqual("medium", item.priority_label)
        self.assertEqual(datetime.date(2026, 9, 24), item.added_date)
        self.assertIsNone(item.purchased_date)
        self.assertFalse(item.purchased)
        self.assertEqual(4.7, item.rating)
        self.assertEqual(9165, item.review_count)
        self.assertFalse(item.prime_eligible)
        self.assertEqual("See all buying options", item.action_label)
        self.assertEqual("<WishListItem IB096Y9Q2RVX9: \"" + item.title + "\">", repr(item))

    def test_wish_list_item_purchased(self):
        # GIVEN an item Amazon has marked purchased, which renders the purchase date in place of the added date
        item = WishListItem(self._item_tag(self._read_resource("wish-list-shared.html"), "I3W1WERO0RFQBJ"),
                            self.test_config)

        # THEN
        self.assertEqual("B0H7BG9RBX", item.asin)
        self.assertEqual(17.99, item.price)
        self.assertIsNone(item.price_min)
        self.assertIsNone(item.price_max)
        self.assertEqual("Size: Medium", item.variation)
        self.assertEqual(1, item.quantity_requested)
        self.assertEqual(1, item.quantity_purchased)
        self.assertIsNone(item.added_date)
        self.assertEqual(datetime.date(2026, 9, 24), item.purchased_date)
        self.assertTrue(item.purchased)
        self.assertIsNone(item.rating)
        self.assertIsNone(item.review_count)
        self.assertTrue(item.prime_eligible)
        self.assertEqual("Add to Cart", item.action_label)

    def test_wish_list_item_no_price(self):
        # GIVEN an item with no price (the page sorts it as -Infinity)
        item = WishListItem(self._item_tag(self._read_resource("wish-list-default.html"), "I3ETCRLF6FJ2IY"),
                            self.test_config)

        # THEN
        self.assertIsNone(item.price)
        self.assertIsNone(item.price_min)
        self.assertIsNone(item.price_max)
        self.assertEqual("See all buying options", item.action_label)
        self.assertEqual(datetime.date(2020, 11, 12), item.added_date)

    def test_wish_list_item_book(self):
        # GIVEN a book, whose ASIN is an ISBN and whose byline is the author
        item = WishListItem(self._item_tag(self._read_resource("wish-list-default.html"), "IXY4HWUYDHK1M"),
                            self.test_config)

        # THEN
        self.assertEqual("1982141182", item.asin)
        self.assertEqual("The Will of the Many (Hierarchy)", item.title)
        self.assertEqual("James Islington (Paperback)", item.byline)
        self.assertEqual("Format: Paperback", item.variation)
        self.assertEqual(13.28, item.price)

    def test_wish_list_item_note_priority_and_quantities(self):
        # GIVEN a purchased item that was then given a note, the "highest" priority, and a wanted quantity of
        # two, so one more is needed
        item = WishListItem(self._item_tag(self._read_resource("wish-list-shared-edited.html"), "I3W1WERO0RFQBJ"),
                            self.test_config)

        # THEN the note and priority read as entered, and the item is no longer purchased although its
        # purchase date remains
        self.assertEqual("test note. I changes the \"Needs\" to 2 and the \"Priority\" to \"Highest\"", item.note)
        self.assertEqual(2, item.priority)
        self.assertEqual("highest", item.priority_label)
        self.assertEqual(2, item.quantity_requested)
        self.assertEqual(1, item.quantity_purchased)
        self.assertEqual(datetime.date(2026, 9, 24), item.purchased_date)
        self.assertIsNone(item.added_date)
        self.assertFalse(item.purchased)

        # WHEN the quantity had reaches the quantity wanted
        item_tag = self._item_tag(self._read_resource("wish-list-shared-edited.html"), "I3W1WERO0RFQBJ")
        item_tag.select_one("span#itemPurchased_I3W1WERO0RFQBJ").string = "2"
        item = WishListItem(item_tag, self.test_config)

        # THEN purchased
        self.assertTrue(item.purchased)

    def test_wish_list_item_purchased_without_quantities(self):
        # GIVEN a purchased item whose quantity row is gone
        item_tag = self._item_tag(self._read_resource("wish-list-shared-edited.html"), "I3JOF2YQGGDZQY")
        item_tag.select_one("span#itemQuantityRow_I3JOF2YQGGDZQY").decompose()

        # WHEN
        item = WishListItem(item_tag, self.test_config)

        # THEN the purchased marker decides
        self.assertIsNone(item.quantity_requested)
        self.assertTrue(item.purchased)

        # WHEN the marker is gone too
        item_tag.select_one("div#itemGiftedFromElsewhereSuccessAlert_I3JOF2YQGGDZQY").decompose()
        item = WishListItem(item_tag, self.test_config)

        # THEN the purchase date decides
        self.assertTrue(item.purchased)

        # WHEN that is gone as well
        item_tag.select_one("span#itemPurchasedDate_I3JOF2YQGGDZQY").decompose()
        item = WishListItem(item_tag, self.test_config)

        # THEN
        self.assertFalse(item.purchased)

    def test_parse_wish_list_page_edited(self):
        # GIVEN the live DOM of the list after the edit (its members popover moved to the body modal)
        result = AmazonLists.parse_wish_list_page(self._read_resource("wish-list-shared-edited.html"),
                                                  self.test_config)

        # THEN
        self.assertEqual("wish_list", result.page_type)
        self.assertEqual(10, len(result.items))
        self.assertEqual(8, len([item for item in result.items if item.purchased]))
        self.assertEqual(["Jane Doe", "John Doe"], [c.name for c in result.wish_list.collaborators])
        self.assertIsNotNone(result.next_page_url)

    def test_wish_list_item_asin_from_link(self):
        # GIVEN an item whose hidden external ID is gone
        item_tag = self._item_tag(self._read_resource("wish-list-shared.html"), "IB096Y9Q2RVX9")
        item_tag.select_one("input[name='itemExternalId']").decompose()

        # WHEN
        item = WishListItem(item_tag, self.test_config)

        # THEN the ASIN falls back to the product link
        self.assertEqual("B0C1G62PNP", item.asin)

    def test_wish_list_item_missing_required_fields(self):
        # GIVEN an item with no title link
        item_tag = self._item_tag(self._read_resource("wish-list-shared.html"), "IB096Y9Q2RVX9")
        item_tag.select_one("a#itemName_IB096Y9Q2RVX9").decompose()

        # WHEN / THEN the title is required
        with self.assertRaises(AmazonOrdersError) as cm:
            WishListItem(item_tag, self.test_config)
        self.assertIn("WishListItem.title did not populate", str(cm.exception))

        # WHEN warn_on_missing_required_field is set it degrades to None
        config = AmazonOrdersConfig(data={"output_dir": self.test_output_dir,
                                          "cookie_jar_path": self.test_cookie_jar_path,
                                          "warn_on_missing_required_field": True})
        item = WishListItem(item_tag, config)

        # THEN
        self.assertIsNone(item.title)
        self.assertIsNone(item.link)
        self.assertEqual("B0C1G62PNP", item.asin)
        self.assertEqual(5.94, item.price)

    def test_wish_list_item_to_dict(self):
        # GIVEN
        item = WishListItem(self._item_tag(self._read_resource("wish-list-shared.html"), "I3W1WERO0RFQBJ"),
                            self.test_config)

        # WHEN
        serialized = item.to_dict()

        # THEN the item tag and config are omitted and the rest are primitives
        self.assertNotIn("parsed", serialized)
        self.assertNotIn("config", serialized)
        self.assertEqual("2026-09-24", serialized["purchased_date"])
        self.assertIsNone(serialized["added_date"])
        self.assertTrue(serialized["purchased"])
        self.assertEqual(17.99, serialized["price"])
        self.assertEqual(json.loads(json.dumps(serialized)), serialized)

    def test_wish_list_entry_missing_required_fields(self):
        # GIVEN a nav entry whose anchor carries no list ID
        entry_tag = self._entry_tag(self._read_resource("wish-list-shared.html"), SHARED_LIST_ID)
        entry_tag.select_one("a")["id"] = "broken"

        # WHEN / THEN the list ID is required
        with self.assertRaises(AmazonOrdersError) as cm:
            WishList(entry_tag, self.test_config)
        self.assertIn("WishList.list_id did not populate", str(cm.exception))

    def test_wish_list_to_dict(self):
        # GIVEN a list built from its page, members and items included
        result = AmazonLists.parse_wish_list_page(self._read_resource("wish-list-shared.html"), self.test_config)

        # WHEN
        serialized = result.wish_list.to_dict()

        # THEN nested entities serialize too
        self.assertNotIn("parsed", serialized)
        self.assertEqual(SHARED_LIST_ID, serialized["list_id"])
        self.assertEqual("Household (shared)", serialized["name"])
        self.assertEqual("all", serialized["items_filter"])
        self.assertEqual([{"name": "Jane Doe", "profile_id": "amzn1.account.AAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                           "is_owner": True},
                          {"name": "John Doe", "profile_id": "amzn1.account.AAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                           "is_owner": False}],
                         serialized["collaborators"])
        self.assertEqual(10, len(serialized["items"]))
        self.assertEqual("IB096Y9Q2RVX9", serialized["items"][0]["item_id"])
        self.assertEqual(json.loads(json.dumps(serialized)), serialized)
