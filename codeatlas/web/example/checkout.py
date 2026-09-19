"""A tiny checkout flow to explore before importing your own code."""

from inventory import available
from payments import charge


def checkout(item, quantity):
    if not available(item, quantity):
        return {"error": "Out of stock"}
    return charge(item.price * quantity)
