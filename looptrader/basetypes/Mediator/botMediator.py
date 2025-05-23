import logging
import logging.config
import time
from typing import Union

import attr
import basetypes.Mediator.baseModels as baseModels
import basetypes.Mediator.reqRespTypes as baseRR
from basetypes.Broker.abstractBroker import Broker
from basetypes.Database.abstractDatabase import Database
from basetypes.Mediator.abstractMediator import Mediator
from basetypes.Notifier.abstractnotifier import Notifier
from basetypes.Strategy.abstractStrategy import Strategy

logger = logging.getLogger("autotrader")


@attr.s(auto_attribs=True)
class Bot(Mediator):
    notifier: Notifier = attr.ib(validator=attr.validators.instance_of(Notifier))  # type: ignore[misc]
    database: Database = attr.ib(validator=attr.validators.instance_of(Database))  # type: ignore[misc]
    botloopfrequency: int = attr.ib(
        validator=attr.validators.instance_of(int), init=False
    )
    killswitch: bool = attr.ib(
        default=False, validator=attr.validators.instance_of(bool), init=False
    )
    pause: bool = attr.ib(
        default=False, validator=attr.validators.instance_of(bool), init=False
    )
    brokerstrategy: dict[Strategy, Broker] = attr.ib(
        validator=attr.validators.deep_mapping(
            key_validator=attr.validators.instance_of(Strategy),  # type: ignore[misc]
            value_validator=attr.validators.instance_of(Broker),  # type: ignore[misc]
            mapping_validator=attr.validators.instance_of(dict),
        )
    )

    def __attrs_post_init__(self):
        self.botloopfrequency = 60
        self.killswitch = False

        # Set Mediators
        self.database.mediator = self
        self.notifier.mediator = self

        # Validate Broker Strategies and set Mediators
        names = []

        for strategy, broker in self.brokerstrategy.items():
            # Check for Duplicates
            if strategy.strategy_name in names:
                raise Exception("Duplicate Strategy Name")

            # Assign Strategy and Mediators
            names.append(strategy.strategy_name)
            broker.mediator = self
            strategy.mediator = self

            # Check if Strat exists, create it if needed, store the ID
            read_strat_request = baseRR.ReadDatabaseStrategyByNameRequest(
                strategy.strategy_name
            )
            result = self.database.read_first_strategy_by_name(read_strat_request)

            if result.strategy is None:
                base_strategy = baseModels.Strategy()
                base_strategy.name = strategy.strategy_name
                create_strat_request = baseRR.CreateDatabaseStrategyRequest(
                    base_strategy
                )
                strategy.strategy_id = self.database.create_strategy(
                    create_strat_request
                ).id
            else:
                strategy.strategy_id = result.strategy.id

    def process_strategies(self):
        # Get the current timestamp
        starttime = time.time()

        # If the loop is exited, send a notification
        self.send_notification(
            baseRR.SendNotificationRequestMessage(message="Bot Started.")
        )

        # While the kill switch is not enabled, loop through strategies
        while not self.killswitch:

            # Process each strategy sequentially
            strategy: Strategy
            for strategy in self.brokerstrategy:
                # Check if we are paused
                if not self.pause:
                    strategy.process_strategy()

            # Sleep for the specified time.
            logger.info("Sleeping...")
            time.sleep(
                self.botloopfrequency
                - ((time.time() - starttime) % self.botloopfrequency)
            )

        # If the loop is exited, send a notification
        self.send_notification(
            baseRR.SendNotificationRequestMessage(message="Bot Terminated.")
        )

    def get_account(
        self, request: baseRR.GetAccountRequestMessage
    ) -> Union[baseRR.GetAccountResponseMessage, None]:
        broker = self.get_broker(request.strategy_id)

        if broker is None:
            return None

        return broker.get_account(request)

    def get_all_accounts(
        self, request: baseRR.GetAllAccountsRequestMessage
    ) -> Union[baseRR.GetAllAccountsResponseMessage, None]:

        response = baseRR.GetAllAccountsResponseMessage()
        response.accounts = []

        distinct_brokers = list(set(self.brokerstrategy.keys()))

        for strategy in distinct_brokers:
            broker = self.get_broker(strategy.strategy_id)

            if broker is None:
                continue

            acct_request = baseRR.GetAccountRequestMessage(
                strategy.strategy_id, request.orders, request.positions
            )

            account = broker.get_account(acct_request)

            if account is not None:
                response.accounts.append(account)

        return response

    def place_order(
        self, request: baseRR.PlaceOrderRequestMessage
    ) -> Union[baseRR.PlaceOrderResponseMessage, None]:
        broker = self.get_broker(request.order.strategy_id)

        if broker is None:
            return None

        return broker.place_order(request)

    def cancel_order(
        self, request: baseRR.CancelOrderRequestMessage
    ) -> Union[baseRR.CancelOrderResponseMessage, None]:
        broker = self.get_broker(request.strategy_id)

        if broker is None:
            return None

        return broker.cancel_order(request)

    def get_order(
        self, request: baseRR.GetOrderRequestMessage
    ) -> Union[baseRR.GetOrderResponseMessage, None]:
        broker = self.get_broker(request.strategy_id)

        if broker is None:
            return None

        return broker.get_order(request)

    def get_market_hours(
        self, request: baseRR.GetMarketHoursRequestMessage
    ) -> Union[baseRR.GetMarketHoursResponseMessage, None]:
        broker = self.get_broker(request.strategy_id)

        if broker is None:
            return None

        return broker.get_market_hours(request)

    def get_quote(
        self, request: baseRR.GetQuoteRequestMessage
    ) -> Union[baseRR.GetQuoteResponseMessage, None]:
        broker = self.get_broker(request.strategy_id)

        if broker is None:
            return None

        return broker.get_quote(request)

    def get_option_chain(
        self, request: baseRR.GetOptionChainRequestMessage
    ) -> Union[baseRR.GetOptionChainResponseMessage, None]:
        broker = self.get_broker(request.strategy_id)

        if broker is None:
            return None

        return broker.get_option_chain(request)

    def send_notification(self, request: baseRR.SendNotificationRequestMessage) -> None:
        self.notifier.send_notification(request)

    def set_kill_switch(self, request: baseRR.SetKillSwitchRequestMessage) -> None:
        self.killswitch = request.kill_switch

    def pause_bot(self) -> None:
        self.pause = True

    def resume_bot(self) -> None:
        self.pause = False

    def get_broker(self, strategy_id: int) -> Union[Broker, None]:
        """Returns the broker object associated to a given strategy

        Args:
            strategy_id (int): Name of the Strategy to search

        Returns:
            Broker: Associated Broker object
        """
        return next(
            (
                broker
                for strategy, broker in self.brokerstrategy.items()
                if strategy.strategy_id == strategy_id
            ),
            None,
        )

    def get_all_strategies(self) -> list[str]:
        strategies = list[str]()

        for strategy in self.brokerstrategy.keys():
            strategies.append(strategy.strategy_name)

        return strategies

    def create_db_strategy(
        self, request: baseRR.CreateDatabaseStrategyRequest
    ) -> Union[baseRR.CreateDatabaseStrategyResponse, None]:
        return self.database.create_strategy(request)

    def create_db_order(
        self, request: baseRR.CreateDatabaseOrderRequest
    ) -> Union[baseRR.CreateDatabaseOrderResponse, None]:
        return self.database.create_order(request)

    def update_db_order(
        self, request: baseRR.UpdateDatabaseOrderRequest
    ) -> Union[baseRR.UpdateDatabaseOrderResponse, None]:
        return self.database.update_order(request)

    def read_active_orders(
        self, request: baseRR.ReadOpenDatabaseOrdersRequest
    ) -> Union[baseRR.ReadOpenDatabaseOrdersResponse, None]:
        return self.database.read_active_orders(request)

    def read_offset_legs_by_expiration(
        self, request: baseRR.ReadOffsetLegsByExpirationRequest
    ) -> Union[baseRR.ReadOffsetLegsByExpirationResponse, None]:
        return self.database.read_offset_legs_by_expiration(request)
