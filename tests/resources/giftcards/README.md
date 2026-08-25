# Gift Card Fixtures

Sanitized captures of the `https://www.amazon.com/gc/balance` page (a plain `GET`; the
activity table paginates via the `ul.a-pagination li.a-last a` link with a base64 `next`
token, and the final page renders `<li class="a-disabled a-last">` with no anchor). Only
the `div#gc-balance-table` region is retained — everything the Gift Card selectors parse
lives inside it.

| File | Variant | Provenance |
| --- | --- | --- |
| `gift-card-balance-activity.html` | Balance plus 15 activity rows (applied-to-order debits, a Reload credit, refund credits) and an enabled Next pagination link | Captured 2026-08-25, sanitized |
| `gift-card-balance-activity-page-2.html` | A middle page: active Previous and Next links; claim code redemption rows ("Gift Card added", with claim code and serial number, no Order link) and refund rows rendered without an Order link | Captured 2026-08-25 (page 2 of 7), sanitized |
| `gift-card-balance-activity-last-page.html` | The final page: disabled Next item with no anchor; claim code redemption rows without a serial number; the account's first-ever activity row | Captured 2026-08-25 (page 7 of 7), sanitized |
| `gift-card-balance-zero-activity.html` | Balance present, no activity table | Fabricated from the page-1 capture — the source account has history, so a real capture needs a fresh account |

Sanitization applied (DOM structure is byte-accurate to the captures):

- Order IDs remapped to fake `111-55009xx-24786xx` values (repeats preserved; the map is
  consistent within each capture run)
- Claim code visible last-4 remapped (`xxxx-xxxxxx-TSnn`) and serial numbers replaced with
  fake same-length digits
- Amounts and closing balances replaced with the real ledger scaled by a constant factor,
  recomputed so `closing = older closing + amount` holds exactly on every row, signs and
  zero-closings preserved, and the balance box scaled from the real balance
- Inline `<script>` bodies emptied (they carried customer/session identifiers)
- The pagination `next`/`prev` tokens replaced with fakes (the real tokens encode an
  account ID)
