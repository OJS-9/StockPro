"""
Cost basis calculation using simple average method.
"""

from decimal import Decimal
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class CostBasisResult:
    """Result of cost basis calculation."""

    total_quantity: Decimal
    average_cost: Decimal
    total_cost_basis: Decimal
    realized_gains: Decimal


def calculate_simple_average(transactions: List[Dict]) -> CostBasisResult:
    """
    Calculate simple average cost basis from a list of transactions.

    The simple average method:
    - BUY: Increases quantity and cost basis proportionally
    - SELL: Decreases quantity, cost basis adjusts proportionally
    - Average cost remains constant after sells (until next buy)

    Args:
        transactions: List of dicts with keys:
            - transaction_type: 'buy' or 'sell'
            - quantity: Decimal or number
            - price_per_unit: Decimal or number
            - fees: Decimal or number (optional, defaults to 0)
            - transaction_date: datetime (for sorting)

    Returns:
        CostBasisResult with:
            - total_quantity: Current position size
            - average_cost: Weighted average cost per unit
            - total_cost_basis: total_quantity * average_cost
            - realized_gains: Sum of (sale_proceeds - cost_of_sold) for all sells

    Example:
        >>> txns = [
        ...     {'transaction_type': 'buy', 'quantity': 10, 'price_per_unit': 100,
        ...      'fees': 0, 'transaction_date': datetime(2024, 1, 1)},
        ...     {'transaction_type': 'buy', 'quantity': 10, 'price_per_unit': 50,
        ...      'fees': 0, 'transaction_date': datetime(2024, 1, 2)},
        ... ]
        >>> result = calculate_simple_average(txns)
        >>> result.total_quantity
        Decimal('20')
        >>> result.average_cost
        Decimal('75')  # (1000 + 500) / 20
    """
    if not transactions:
        return CostBasisResult(
            total_quantity=Decimal("0"),
            average_cost=Decimal("0"),
            total_cost_basis=Decimal("0"),
            realized_gains=Decimal("0"),
        )

    total_quantity = Decimal("0")
    total_cost = Decimal("0")
    realized_gains = Decimal("0")

    # Sort by date to process in chronological order
    sorted_txns = sorted(transactions, key=lambda x: x["transaction_date"])

    for txn in sorted_txns:
        qty = Decimal(str(txn["quantity"]))
        price = Decimal(str(txn["price_per_unit"]))
        fees = Decimal(str(txn.get("fees", 0) or 0))

        if txn["transaction_type"] == "buy":
            # Add to position: new cost = old cost + purchase cost (including fees)
            purchase_cost = (qty * price) + fees
            total_cost += purchase_cost
            total_quantity += qty

        elif txn["transaction_type"] == "sell":
            if total_quantity > 0:
                # Calculate average cost at time of sale
                avg_cost_at_sale = total_cost / total_quantity

                # Calculate realized gain/loss
                # Proceeds = (quantity * price) - fees
                sale_proceeds = (qty * price) - fees
                cost_of_sold = qty * avg_cost_at_sale
                realized_gains += sale_proceeds - cost_of_sold

                # Reduce position proportionally
                total_quantity -= qty
                total_cost = avg_cost_at_sale * total_quantity

    # Calculate final average cost
    average_cost = total_cost / total_quantity if total_quantity > 0 else Decimal("0")

    return CostBasisResult(
        total_quantity=total_quantity,
        average_cost=average_cost,
        total_cost_basis=total_cost,
        realized_gains=realized_gains,
    )
