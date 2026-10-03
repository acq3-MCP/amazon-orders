# Lists Fixtures

Sanitized captures of two Amazon List (wish list) pages, `https://www.amazon.com/hz/wishlist/ls/<listId>`,
captured 2026-10-03 (browser "Save Page As", which serializes the page as served), and of the live DOM of
one of them scrolled to its end (DevTools "Copy outerHTML"). The page is server-rendered: the left nav
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
`itemComment_`, `itemRequested_`, `itemPurchased_`, `itemPriority_`/`itemPriorityLabel_` (medium is `0`,
highest `2`), `itemAddedDate_` on an item never purchased or `itemPurchasedDate_` on one with a purchase
recorded, the hidden "This item is marked as purchased" alert `itemGiftedFromElsewhereSuccessAlert_` on an
item whose quantity had has reached its quantity wanted, `review_stars_`, `review_count_`,
`itemAction_`). The page renders ten items; the rest load by infinite scroll from the "See More" control,
a no-JS anchor `a.wl-see-more` to `/hz/wishlist/slv/items?filter=…&paginationToken=…` (its JS twin holds
the same URL in a `form.scroll-state`'s `input[name="showMoreUrl"]`). Each batch appends to `ul#g-items`
its own `input#viewItemCount`, its items, and a scroll-state form of its own (so a scrolled page holds one
`showMoreUrl` per batch, the first ones stale), followed by another "See More" or, on the last batch, by
`div#endOfListMarker` ("End of list"); the last batch's form carries an empty `paginationToken` and an empty
`lastEvaluatedKey`. The live DOM also moves the "List members" popover out of `div#list-header` to an
`a-popover-modal` at the end of the body.

| File | Variant | Provenance |
| --- | --- | --- |
| `wish-list-shared.html` | A collaborative list (two members, one the owner) rendered with the `all` filter: one unpurchased item with a price range, nine purchased items, and a "See More" control | Captured, sanitized |
| `wish-list-default.html` | The account's default list rendered with the `unpurchased` filter: ten unpurchased items, among them books (ISBN ASINs, author bylines, Kindle "Buy now with 1-Click" buttons) and one item with no price (`data-price="-Infinity"`), and a "See More" control | Captured, sanitized |
| `wish-list-shared-edited.html` | The live DOM of the collaborative list after one purchased item was given a note, the "highest" priority (encoded `2`), and a wanted quantity of two: its quantity row reads "Needs 2 · Has: 1", its purchase date remains, and its "marked as purchased" alert is gone | Captured (DOM), sanitized |
| `wish-list-shared-scrolled.html` | The live DOM of the collaborative list scrolled to its end: three batches (22 items, the last two added by the final batch) with their scroll-state forms, the end-of-list marker, and the members modal at the end of the body | Captured (DOM), sanitized |
| `wish-list-shared-batch-last.html` | The last batch as the "See More" control serves it: its item-count input, two items, its scroll-state form with an empty token, and the end-of-list marker, as a bare sequence of `li` | Cut from the scrolled DOM's `ul#g-items` (the batch as appended; the response's own framing, if any, is not observed) |
| `wish-list-empty.html` | The default list with no items and no "See More" control | Fabricated from the capture by removing the items and the control — the real no-items rendering is unverified |

Sanitization applied (the retained markup is otherwise byte-accurate to the capture):

- Only `div#wishlist-page` (nav, header with its popovers, control bar, and items), plus the members modal
  where the live DOM moved it, is retained, inside a minimal page shell with a placeholder nav greeting; every `<script>`, `<style>`, `<noscript>`, and
  `<link>` removed, along with the share and move-to-list popovers and lazy-load image sources
- The six list IDs remapped to `1AAAAAAAAAAAA` … `WFFFFFFFFFFF`; the two lists named for a street address
  renamed `Household` and `Household (shared)`; item IDs kept
- Member names replaced with `Jane Doe` and `John Doe`, their profile IDs with one `amzn1.account.A…` placeholder
- The session ID, customer ID, CSRF tokens, offer listing IDs, the location validation token, and the
  pagination tokens (`paginationToken=TOKEN_PAGE_2`, also in `input[name="lastEvaluatedKey"]`) zeroed or replaced
- On the default list, two items replaced with generic products (title, brand or author, and ASIN), keeping
  the item IDs and markup
