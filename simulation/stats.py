"""Run statistics and the business-key sequence generator shared by every
generator — kept in one place so numbering stays consistent and the
final validation-run report has real counts to show, not estimates.
"""

from dataclasses import dataclass, field


@dataclass
class SimulationStats:
    orders_created: int = 0
    order_lines_created: int = 0
    order_lines_fully_allocated: int = 0
    order_lines_backordered: int = 0
    purchase_orders_created: int = 0
    purchase_order_lines_received: int = 0
    purchase_orders_fulfilled: int = 0
    shipments_created: int = 0
    shipments_delivered: int = 0
    returns_created: int = 0
    return_lines_inspected: int = 0
    return_lines_sellable: int = 0

    _sequence: int = field(default=0, repr=False)

    def next_seq(self) -> int:
        self._sequence += 1
        return self._sequence
