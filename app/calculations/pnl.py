from dataclasses import dataclass
from decimal import Decimal, localcontext
from app.calculations.money import decimal_value


@dataclass(frozen=True)
class Position:
    quantity: Decimal = Decimal(0)
    cost: Decimal = Decimal(0)
    realized: Decimal = Decimal(0)

    def __post_init__(self):
        decimal_value(self.quantity)
        # Cost is kept at calculation precision; rounding belongs at the reporting boundary.
        if not self.cost.is_finite() or self.cost < 0 or not self.realized.is_finite():
            raise ValueError("Invalid position balances")
        if self.quantity == 0 and self.cost != 0:
            raise ValueError("Empty position cannot carry acquisition cost")

    @property
    def average_price(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 38
            return self.cost / self.quantity if self.quantity else Decimal(0)

    def buy(self, quantity, price, fees=0):
        qty, unit, costs = decimal_value(quantity, positive=True), decimal_value(price, positive=True), decimal_value(fees)
        with localcontext() as ctx:
            ctx.prec = 38
            return Position(self.quantity + qty, self.cost + qty * unit + costs, self.realized)

    def sell(self, quantity, price, fees=0):
        qty, unit, costs = decimal_value(quantity, positive=True), decimal_value(price, positive=True), decimal_value(fees)
        if qty > self.quantity:
            raise ValueError("Insufficient position")
        with localcontext() as ctx:
            ctx.prec = 38
            removed = self.cost if qty == self.quantity else self.cost * qty / self.quantity
            realized = qty * unit - costs - removed
            return Position(self.quantity - qty, self.cost - removed, self.realized + realized)

    def unrealized(self, price):
        with localcontext() as ctx:
            ctx.prec = 38
            return self.quantity * decimal_value(price, positive=True) - self.cost
