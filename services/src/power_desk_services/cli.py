"""`power-desk-service <name>`: run one service in the foreground until it is stopped (SIGTERM or Ctrl-C)."""

from __future__ import annotations

import argparse
from collections.abc import Callable
import logging

import power_desk_logging
from power_desk_services import entsoe_subscription, iris

SERVICES: dict[str, Callable[[], None]] = {
    "iris": iris.main,
    "entsoe-subscription": entsoe_subscription.main,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=sorted(SERVICES))
    args = parser.parse_args()
    power_desk_logging.configure(args.service)
    # the Service Bus client logs every AMQP frame at INFO
    logging.getLogger("azure").setLevel(logging.WARNING)
    SERVICES[args.service]()


if __name__ == "__main__":
    main()
