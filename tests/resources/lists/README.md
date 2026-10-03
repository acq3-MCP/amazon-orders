# Lists Fixtures

Sanitized captures of two Amazon List (wish list) pages, `https://www.amazon.com/hz/wishlist/ls/<listId>`,
captured 2026-10-03 (browser "Save Page As"). The page is server-rendered: the left nav
`div#your-lists-nav` indexes every list on the account as one `div.wl-list` (the page's own list is
`.selected`) wrapping an anchor `a#wl-list-link-<listId>` with the name in `span#wl-list-entry-title-<listId>`,
a "Default List" or "Collaborator" label in `span#list-default-collaborator-label`, and the privacy in
`div#wl-list-entry-privacy-<listId>`; the Alexa shopping list is indexed alongside with a
`/gp/alexa-shopping-list` link. The page's own list is described by `div#list-header` (name in
`span#profile-list-name`, the members of a collaborative list in the "List members" popover's
`div#manage-collaborators-row-N` rows, one labeled "Owner") and the filter and sort it rendered with in
`form#wl-item-search`'s hidden `filter` and `sort` inputs. Items render in `ul#g-items` as one
`li[data-itemid][data-id][data-price]` each, every field tagged with an id suffixed by the item ID
(`itemName_`, `item-byline-`, `itemPrice_` with `itemMinPrice_`/`itemMaxPrice_` for a range, `twisterText`,
`itemComment_`, `itemRequested_`, `itemPurchased_`, `itemPriority_`/`itemPriorityLabel_`, `itemAddedDate_` on
an unpurchased item or `itemPurchasedDate_` on a purchased one, `review_stars_`, `review_count_`,
`itemAction_`). The page renders ten items; the rest load by infinite scroll from the "See More" control,
a no-JS anchor `a.wl-see-more` to `/hz/wishlist/slv/items?filter=…&paginationToken=…` (its JS twin holds
the same URL in `input[name="showMoreUrl"]`). What that URL serves (a full page or a bare batch) was not
captured; the parser accepts either.

| File | Variant | Provenance |
| --- | --- | --- |
| `wish-list-shared.html` | A collaborative list (two members, one the owner) rendered with the `all` filter: one unpurchased item with a price range, nine purchased items, and a "See More" control | Captured, sanitized |
| `wish-list-default.html` | The account's default list rendered with the `unpurchased` filter: ten unpurchased items, among them books (ISBN ASINs, author bylines, Kindle "Buy now with 1-Click" buttons) and one item with no price (`data-price="-Infinity"`), and a "See More" control | Captured, sanitized |
| `wish-list-shared-last-page.html` | The collaborative list with no "See More" control | Fabricated from the capture by removing the control and its hidden URL input — the real end-of-list rendering is unverified |
| `wish-list-empty.html` | The default list with no items and no "See More" control | Fabricated from the capture by removing the items and the control — the real no-items rendering is unverified |

Sanitization applied (the retained markup is otherwise byte-accurate to the capture):

- Only `div#wishlist-page` (nav, header with its popovers, control bar, and items) is retained, inside a
  minimal page shell with a placeholder nav greeting; every `<script>`, `<style>`, `<noscript>`, and
  `<link>` removed, along with the share and move-to-list popovers and lazy-load image sources
- The six list IDs remapped to `1AAAAAAAAAAAA` … `WFFFFFFFFFFF`; the two lists named for a street address
  renamed `Household` and `Household (shared)`; item IDs kept
- Member names replaced with `Jane Doe` and `John Doe`, their profile IDs with one `amzn1.account.A…` placeholder
- The session ID, customer ID, CSRF tokens, offer listing IDs, the location validation token, and the
  pagination tokens (`paginationToken=TOKEN_PAGE_2`, also in `input[name="lastEvaluatedKey"]`) zeroed or replaced
- On the default list, two items replaced with generic products (title, brand or author, and ASIN), keeping
  the item IDs and markup
