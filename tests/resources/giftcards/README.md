# Gift Card Fixtures

Sanitized captures of the `https://www.amazon.com/gc/balance` page (a plain `GET`; the
activity table paginates via the `ul.a-pagination li.a-last a` link with a base64 `next`
token). Only the `div#gc-balance-table` region is retained — everything the Gift Card
selectors parse lives inside it.

| File | Variant | Provenance |
| --- | --- | --- |
| `gift-card-balance-activity.html` | Balance plus 15 activity rows (applied-to-order debits, a Reload credit, refund credits) and an enabled Next pagination link | Captured 2026-08-25, sanitized |
| `gift-card-balance-activity-last-page.html` | Same rows with the Next link disabled (final page) | Fabricated from the capture — replace when a real page-02 capture lands |
| `gift-card-balance-zero-activity.html` | Balance present, no activity table | Fabricated from the capture — replace when a real zero-activity capture lands |

Not yet covered, pending captures: a claim code redemption row, and a real second page.

Sanitization applied (DOM structure is byte-accurate to the capture):

- Order IDs remapped to fake `111-55009xx-24786xx` values (repeats preserved)
- Amounts and closing balances replaced with the real ledger scaled by a constant factor,
  recomputed so `closing = older closing + amount` holds exactly on every row, signs and
  zero-closings preserved, and the balance box matches the newest closing balance
- Inline `<script>` bodies emptied (they carried customer/session identifiers)
- The pagination `next` token replaced with a fake (the real token encodes an account ID)
