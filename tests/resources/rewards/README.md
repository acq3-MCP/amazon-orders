# Rewards Fixtures

Fixtures for the `https://www.amazon.com/credit/rewardscard/member` page (a plain `GET`; the
rewards card member page for an account holding an Amazon co-branded credit card). Only the
"Rewards balance" box (dollar value and points) and the masked card label in the header are
parsed; the card balance and payment-due fields are Chase-hosted and render as `$-` placeholders
until a separate Chase login, so they are deliberately not covered.

| File | Variant | Provenance |
| --- | --- | --- |
| `rewards-card-member.html` | Card label in the header, Chase placeholders, referral and security-center boxes, and the Rewards balance box with a dollar value, points, and a footnote | Fabricated 2026-09-07 from a screenshot of the live page — see below |
| `rewards-card-no-card.html` | The apply landing page rendered when the account holds no card: no card label, no Rewards balance box | Fabricated 2026-09-07 |

**These fixtures are not captures.** No sanitized capture of the live page's DOM was available when
they were written, so the markup (element names, `cbcc-*` class names, nesting) is a plausible
reconstruction of what the screenshot shows, not byte-accurate. The visible text and the values are
taken from the screenshot verbatim except the card's last four digits, which are fake. Because of
this, the Rewards selectors are text-anchored ("Rewards balance", the `••••` mask) and the entity
reads the values from the enclosing box by pattern rather than by ID, so they should hold on the
live page as long as the visible text does. Replacing these files with sanitized captures (empty the
inline `<script>` bodies, remap the last four digits) is the outstanding validation step; the
integration test `test_get_rewards_balance` exercises the live page.
