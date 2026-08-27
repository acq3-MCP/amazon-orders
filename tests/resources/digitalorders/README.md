# Digital Orders Fixtures

Sanitized captures of the Digital Orders tab of the Order history page
(`{ORDER_HISTORY_URL}?orderFilter=digital&timeFilter=year-YYYY&startIndex=N`), captured
2026-08-26/27. Only the `div.your-orders-content-container__content.js-yo-main-content`
region is retained — the order cards, the `js-time-filter-form` (count header + `timeFilter`
dropdown), and the pagination all live inside it.

Key facts these fixtures encode:

- The tab's **default window is "past 3 months"** — without an explicit `timeFilter`, older
  digital history is silently absent (`digital-order-history-default-window.html` shows the
  resulting legitimate "0 orders" state on an account whose digital orders are all older).
- The count header renders as `<b>N orders</b> placed in` inside `form.js-time-filter-form`
  (not the `.num-orders` markup of the standard history page).
- The `timeFilter` `<select>` advertises the valid windows (`last30`, `months-3`,
  `year-2026` … `year-2005` at capture time) — year enumeration parses this, never a
  hard-coded range.
- Digital order rows are standard `div.order-card` markup and parse with the existing
  `Order` entity; pagination is the standard `ul.a-pagination` Next link.

| File | Variant |
| --- | --- |
| `digital-order-history-default-window.html` | No `timeFilter` sent: 0 orders, no pagination, full dropdown |
| `digital-order-history-2005-0.html` | Explicit year with 0 orders ("0 orders" header) |
| `digital-order-history-2026-0.html` | 1-page year with 1 order (a gift-card-paid digital purchase) |
| `digital-order-history-2024-0.html` | Page 1 of a 3-page year ("29 orders" header, Next link) |
| `digital-order-history-2024-10.html` | Page 2 (Next link present) |
| `digital-order-history-2024-20.html` | Page 3 (9 orders, no Next link) |

Sanitization applied (DOM structure is byte-accurate to the captures):

- Order IDs remapped to fake `D01-…` values (repeats preserved; consistent across files)
- Item titles replaced with generic `Digital Item NN` names (consistent across files)
- Amounts scaled by a constant factor
- Inline `<script>` bodies emptied

Not yet covered, pending captures: digital order **detail** pages (needed to confirm
`get_order("D01-…")` and the `Order.gift_card` payment breakdown), and a cancelled/refunded
digital order row if one exists.
