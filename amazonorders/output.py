__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import csv
import io
import json
import logging
from typing import Any, Dict, List, Sequence

import yaml

from amazonorders.conf import AmazonOrdersConfig
from amazonorders.entity.gift_card_activity import GiftCardActivity
from amazonorders.entity.order import Order
from amazonorders.entity.parsable import Parsable
from amazonorders.entity.prime_payment import PrimePayment
from amazonorders.entity.rewards_balance import RewardsBalance
from amazonorders.entity.transaction import Transaction
from amazonorders.entity.wish_list import WishList
from amazonorders.entity.wish_list_item import WishListItem

logger = logging.getLogger(__name__)


class OutputFormatter:
    """
    A class that renders entities for output. Extend and override with ``output_class`` in the config:

    .. code-block:: python

        from amazonorders.conf import AmazonOrdersConfig

        config = AmazonOrdersConfig(data={"output_class": "my_module.MyOutputFormatter"})

    ``json``, ``yaml``, and ``csv`` are built from
    :func:`~amazonorders.entity.parsable.Parsable.to_dict`, so any
    :class:`~amazonorders.entity.parsable.Parsable` can be rendered in them, nested entities included.
    ``text`` is rendered by this class's per-entity methods, falling back to the entity's own ``__str__``.

    ``csv`` renders one row per entity, since a spreadsheet cannot nest: a nested entity becomes
    ``parent_child`` columns (e.g. ``recipient_name``), and a list becomes a ``<field>_count`` column
    alongside its values joined by :attr:`CSV_LIST_DELIMITER`. Columns are the union of the fields
    present, so an empty result has no columns and renders as an empty document, where ``json`` and
    ``yaml`` render as an empty list.
    """

    #: The formats accepted by the CLI's ``--output`` option.
    OUTPUT_FORMATS = ["text", "json", "yaml", "csv"]
    #: Joins a list's values within a single CSV column.
    CSV_LIST_DELIMITER = "; "
    #: Fields tried, in order, to summarize a nested entity in a CSV column.
    CSV_SUMMARY_FIELDS = ["title", "name"]

    def __init__(self,
                 config: AmazonOrdersConfig) -> None:
        #: The config to use.
        self.config: AmazonOrdersConfig = config

    def format(self,
               entities: Sequence[Parsable],
               output_format: str) -> str:
        """
        Render the given entities in the given format.

        :param entities: The entities to render.
        :param output_format: One of :attr:`OUTPUT_FORMATS`.
        :return: The rendered output.
        """
        if output_format == "text":
            return "\n".join(f"{self.text(entity)}\n" for entity in entities)

        serialized = [entity.to_dict() for entity in entities]
        if output_format == "json":
            return f"{json.dumps(serialized, indent=2)}\n"
        elif output_format == "yaml":
            return yaml.safe_dump(serialized, sort_keys=False, allow_unicode=True, default_flow_style=False)

        return self._csv(serialized)

    def text(self,
             entity: Parsable) -> str:
        """
        Render a single entity as human-readable text.

        :param entity: The entity to render.
        :return: The entity as text.
        """
        if isinstance(entity, Order):
            return self.order_text(entity)
        elif isinstance(entity, Transaction):
            return self.transaction_text(entity)
        elif isinstance(entity, GiftCardActivity):
            return self.gift_card_activity_text(entity)
        elif isinstance(entity, RewardsBalance):
            return self.rewards_balance_text(entity)
        elif isinstance(entity, PrimePayment):
            return self.prime_payment_text(entity)
        elif isinstance(entity, WishList):
            return self.wish_list_text(entity)
        elif isinstance(entity, WishListItem):
            return self.wish_list_item_text(entity)

        return str(entity)

    def order_text(self,
                   order: Order) -> str:
        """
        Render an Order as human-readable text.

        :param order: The Order to render.
        :return: The Order as text.
        """
        order_str = """-----------------------------------------------------------------------
Order #{order_number}
-----------------------------------------------------------------------""".format(
            order_number=order.order_number)

        order_str += f"\n  Shipments: {order.shipments}"
        order_str += f"\n  Order Details Link: {order.order_details_link}"
        if order.grand_total:
            order_str += f"\n  Grand Total: {self.config.constants.format_currency(order.grand_total)}"
        order_str += f"\n  Order Placed Date: {order.order_placed_date}"
        if order.recipient:
            order_str += f"\n  {order.recipient}"
        else:
            order_str += "\n  Recipient: None"

        if order.payment_method:
            order_str += f"\n  Payment Method: {order.payment_method}"
        if order.payment_method_last_4:
            order_str += f"\n  Payment Method Last 4: {order.payment_method_last_4}"
        if order.subtotal:
            order_str += f"\n  Subtotal: {self.config.constants.format_currency(order.subtotal)}"
        if order.shipping_total:
            order_str += f"\n  Shipping Total: {self.config.constants.format_currency(order.shipping_total)}"
        if order.free_shipping:
            order_str += f"\n  Free Shipping: {self.config.constants.format_currency(order.free_shipping)}"
        if order.subscription_discount:
            order_str += ("\n  Subscription Discount: "
                          f"{self.config.constants.format_currency(order.subscription_discount)}")
        if order.total_before_tax:
            order_str += f"\n  Total Before Tax: {self.config.constants.format_currency(order.total_before_tax)}"
        if order.estimated_tax:
            order_str += f"\n  Estimated Tax: {self.config.constants.format_currency(order.estimated_tax)}"
        if order.refund_total:
            order_str += f"\n  Refund Total: {self.config.constants.format_currency(order.refund_total)}"

        order_str += "\n-----------------------------------------------------------------------"

        return order_str

    def transaction_text(self,
                         transaction: Transaction) -> str:
        """
        Render a Transaction as human-readable text.

        :param transaction: The Transaction to render.
        :return: The Transaction as text.
        """
        transaction_str = f"Transaction: {transaction.completed_date}"
        transaction_str += f"\n  Order #{transaction.order_number}"
        if transaction.grand_total:
            transaction_str += f"\n  Grand Total: {self.config.constants.format_currency(transaction.grand_total)}"
        transaction_str += f"\n  Order Details Link: {transaction.order_details_link}"

        return transaction_str

    def gift_card_activity_text(self,
                                activity: GiftCardActivity) -> str:
        """
        Render a GiftCardActivity entry as human-readable text.

        :param activity: The GiftCardActivity to render.
        :return: The GiftCardActivity as text.
        """
        activity_str = f"Gift Card Activity: {activity.activity_date}"
        if activity.description:
            activity_str += f"\n  Description: {activity.description}"
        if activity.amount is not None:
            activity_str += f"\n  Amount: {self.config.constants.format_currency(activity.amount)}"
        if activity.closing_balance is not None:
            activity_str += f"\n  Closing Balance: {self.config.constants.format_currency(activity.closing_balance)}"
        if activity.order_number:
            activity_str += f"\n  Order #{activity.order_number}"
            activity_str += f"\n  Order Details Link: {activity.order_details_link}"

        return activity_str

    def rewards_balance_text(self,
                             rewards: RewardsBalance) -> str:
        """
        Render a RewardsBalance as human-readable text.

        :param rewards: The RewardsBalance to render.
        :return: The RewardsBalance as text.
        """
        rewards_str = f"Rewards Balance: {self.config.constants.format_currency(rewards.balance)}"
        if rewards.points is not None:
            rewards_str += f"\n  Points: {rewards.points:,}"
        card_parts = []
        if rewards.card_name:
            card_parts.append(rewards.card_name)
        if rewards.card_last_four:
            card_parts.append(f"\u2022\u2022\u2022\u2022 {rewards.card_last_four}")
        if card_parts:
            rewards_str += f"\n  Card: {' '.join(card_parts)}"
        if rewards.last_update_time:
            rewards_str += f"\n  Last Updated: {rewards.last_update_time}"

        return rewards_str

    def _csv(self,
             entities: List[Dict[str, Any]]) -> str:
        if not entities:
            return ""

        rows = [self._flatten_for_csv(entity) for entity in entities]
        columns: List[str] = []
        for row in rows:
            columns += [column for column in row if column not in columns]

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

        return output.getvalue()

    def _flatten_for_csv(self,
                         entity: Dict[str, Any]) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        for field, value in entity.items():
            if isinstance(value, dict):
                for nested_field, nested_value in self._flatten_for_csv(value).items():
                    row[f"{field}_{nested_field}"] = nested_value
            elif isinstance(value, list):
                row[f"{field}_count"] = len(value)
                row[field] = self.CSV_LIST_DELIMITER.join(self._csv_summary(item) for item in value)
            elif isinstance(value, str):
                row[field] = self._single_line(value)
            else:
                row[field] = value

        return row

    def _csv_summary(self,
                     item: Any) -> str:
        if isinstance(item, dict):
            for field in self.CSV_SUMMARY_FIELDS:
                if item.get(field):
                    return self._single_line(str(item[field]))

            return ""

        return self._single_line(str(item))

    def _single_line(self,
                     value: str) -> str:
        return " ".join(value.split())

    def prime_payment_text(self,
                           payment: PrimePayment) -> str:
        """
        Render a PrimePayment as human-readable text.

        :param payment: The PrimePayment to render.
        :return: The PrimePayment as text.
        """
        total = self.config.constants.format_currency(payment.total) if payment.total is not None else "N/A"
        payment_str = f"Prime Payment {payment.payment_date}: {total}"
        if payment.order_number:
            payment_str += f"\n  Order #: {payment.order_number}"
        if payment.receipt_link:
            payment_str += f"\n  Receipt: {payment.receipt_link}"

        return payment_str

    def wish_list_text(self,
                       wish_list: WishList) -> str:
        """
        Render a WishList as human-readable text, with its items when they were fetched.

        :param wish_list: The WishList to render.
        :return: The WishList as text.
        """
        wish_list_str = f"List {wish_list.list_id}: {wish_list.name}"
        flags = []
        if wish_list.privacy:
            flags.append(wish_list.privacy)
        if wish_list.is_default:
            flags.append("Default")
        if wish_list.is_collaborative:
            flags.append("Collaborative")
        if wish_list.list_type and wish_list.list_type != "WishList":
            flags.append(wish_list.list_type)
        if flags:
            wish_list_str += f" ({', '.join(flags)})"
        if wish_list.collaborators:
            members = ", ".join(f"{c.name}{' (owner)' if c.is_owner else ''}" for c in wish_list.collaborators)
            wish_list_str += f"\n  Members: {members}"
        if wish_list.items is not None:
            showing = f", showing {wish_list.items_filter}" if wish_list.items_filter else ""
            wish_list_str += f"\n  Items: {len(wish_list.items)}{showing}"
            for item in wish_list.items:
                wish_list_str += "\n\n" + "\n".join(f"  {line}" for line in self.wish_list_item_text(item).split("\n"))

        return wish_list_str

    def wish_list_item_text(self,
                            item: WishListItem) -> str:
        """
        Render a WishListItem as human-readable text.

        :param item: The WishListItem to render.
        :return: The WishListItem as text.
        """
        item_str = f"{item.title}"
        if item.variation:
            item_str += f" [{item.variation}]"
        if item.price_min is not None and item.price_max is not None:
            price = (f"{self.config.constants.format_currency(item.price_min)} - "
                     f"{self.config.constants.format_currency(item.price_max)}")
        elif item.price is not None:
            price = self.config.constants.format_currency(item.price)
        else:
            price = "N/A"
        item_str += f"\n  Price: {price}"
        if item.asin:
            item_str += f"\n  ASIN: {item.asin}"
        if item.quantity_requested is not None:
            item_str += f"\n  Needs: {item.quantity_requested}, Has: {item.quantity_purchased}"
        if item.priority_label:
            item_str += f"\n  Priority: {item.priority_label}"
        if item.note:
            item_str += f"\n  Note: {item.note}"
        if item.purchased:
            item_str += f"\n  Purchased: {item.purchased_date or 'yes'}"
        elif item.added_date:
            item_str += f"\n  Added: {item.added_date}"
        if item.link:
            item_str += f"\n  Link: {item.link}"

        return item_str
