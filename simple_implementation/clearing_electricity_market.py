import sys
print(sys.argv)
from typing import List, Tuple
import logging

import gymnasium as gym
import matplotlib.pyplot as plt
import numpy as np
import phantom as ph
from phantom.types import AgentID
from typing import Iterable, Sequence
from market_clearing import Market


NUM_EPISODE_STEPS = 24
CURRENT_STEP = 0

NUM_CUSTOMERS = 1
CUSTOMER_MAX_DEMAND = 2200
MAX_BID_PRICE = 30

LOG_LEVEL = "DEBUG"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("electricity-market")
logger.setLevel(LOG_LEVEL)


@ph.msg_payload()
class BuyBid:
    """
    A bid to buy a certain amount of MWh at a certain price.

    Attributes:
    -----------
    customer_id str:    customer id
    size (int):         the amount of MWh
    price (float):      price of bid
    time:               possibly timestamp for bid?
    """

    buyer_id: str
    mwh: int
    price: float
    

@ph.msg_payload()
class SellBid:
    """
    A bid to sell a certain amount of MWh at a certain price.

    Attributes:
    -----------
    seller_id (str):    seller id
    size (int):         the amount of MWh
    price (float):      price of bid
    time:               possibly timestamp for bid?
    """
    
    seller_id: str
    mwh: int
    price: float
    

@ph.msg_payload()
class ClearedBid:
    """
    A cleared bid designating the amount of MWh at which price
    and the id of buyer and seller.

    Attributes:
    -----------
    size (int):         the amount of MWh
    price (float):      price of bid
    customer_id (int)
    seller_id (int):    customer id
    time:               possibly timestamp for bid?
    """

    seller_id: str
    buyer_id: str
    mwh: int
    price: float

@ph.msg_payload()
class DummyMsg:
    """
    Empty message
    """

    msg: str


class ExchangeAgent(ph.Agent):
    def __init__(self, agent_id: str):
        super().__init__(agent_id)

    @ph.agents.msg_handler(BuyBid)
    def handle_buy_bid(self, ctx: ph.Context, message: ph.Message):
        # Handle a buy bid
        return

    @ph.agents.msg_handler(SellBid)
    def handle_sell_bid(self, ctx: ph.Context, message: ph.Message):
        # Handle a sell bid
        return
    
    @ph.agents.msg_handler(DummyMsg)
    def handle_sell_bid(self, ctx: ph.Context, message: ph.Message):
        # Handle a dummy msg
        return

    def handle_batch(
        self, ctx: ph.Context, batch: Sequence[ph.Message]):
        """@override
        We override the method `handle_batch` to consume all the bids messages
        as one block in order to perform the auction. The batch object contains
        all the messages that were sent to the actor.

        Note:
        -----
        The default logic is to consume each message individually.
        """
        buy_bids = []
        sell_bids = []

        msgs = []

        # Create lists of buy and sell bids
        for message in batch:
            if isinstance(message.payload, BuyBid):
                buy_bids.append(message)
            elif isinstance(message.payload, SellBid):
                sell_bids.append(message)
            else:
                msgs += self.handle_message(ctx, message)

        if len(buy_bids) > 0 and len(sell_bids) > 0:
            msgs = self.market_clearing(buy_bids=buy_bids, sell_bids=sell_bids)

        return msgs
    
    def market_clearing(
        self, buy_bids: Sequence[ph.Message[BuyBid]], sell_bids: Sequence[ph.Message[SellBid]]):   
        """
        Encode and decode buy and sell bids and pass to external market clearing mechanism.

        """
        encoded_buy_bids = []
        encoded_sell_bids = []

        # ENCODING
        for bid in buy_bids:
            tuple = (bid.payload.buyer_id, bid.payload.mwh, bid.payload.price)
            encoded_buy_bids.append(tuple)

        for bid in sell_bids:
            tuple = (bid.payload.seller_id, bid.payload.mwh, bid.payload.price)
            encoded_sell_bids.append(tuple)

        # CLEAR BIDS
        cleared_bids, clearing_price = Market.market_clearing(supply_bids=encoded_sell_bids, demand_bids=encoded_buy_bids)

        # DECODING
        msgs = []

        for cleared_bid in cleared_bids:
            buyer_id, seller_id, mwh, price = cleared_bid
            decoded_cleared_bid = ClearedBid(seller_id=seller_id, buyer_id=buyer_id, mwh=mwh, price=price)
            # Create message for both seller and buyer
            msg1 = (seller_id, decoded_cleared_bid)
            msg2 = (buyer_id, decoded_cleared_bid)
            logger.debug("Cleared bid between: %s and %s for %s MWh at cost: %s", seller_id, buyer_id, mwh, price)
            msgs.extend((msg1, msg2))  # TODO: this is possibly wrong

        return msgs

# Simple Generator Agent for development
class GeneratorAgent(ph.Agent):
    def __init__(self, agent_id: str, exchange_id: str, capacity: int, price: float):
        super().__init__(agent_id)

        # Store the ID of the Exchange that Bids go through
        self.exchange_id = exchange_id
        self.capacity = capacity
        self.price = price

        self.capacity_left: int = 0

        self.supplied_capacity: int = 0
        self.missed_capacity: int = 0

    # Generate supply bid 
    def generate_messages(self, ctx: ph.Context):
        return [(self.exchange_id, SellBid(self.id, self.capacity, self.price))]

    @ph.agents.msg_handler(ClearedBid)
    def handle_cleared_bid(self, _ctx: ph.Context, msg: ph.Message):
        self.supplied_capacity = msg.payload.mwh
        self.capacity_left -= msg.payload.mwh
        logger.debug("Generator Agent %s supplies: %s to %s at price %s", self.id, msg.payload.mwh, msg.payload.buyer_id, msg.payload.price)

    def pre_message_resolution(self, ctx: ph.Context):
        self.capacity_left = self.capacity
        self.supplied_capacity = 0
        self.missed_capacity = 0

    def post_message_resolution(self, ctx: ph.Context):
        self.missed_capacity = self.capacity_left

# Simple Demand Agent for development
class SimpleDemandAgent(ph.Agent):
    def __init__(self, agent_id: str, exchange_id: str, demand: int, price: float):
        super().__init__(agent_id)

        # Store the ID of the Exchange that Bids go through
        self.exchange_id = exchange_id
        self.demand = demand
        self.price = price

        self.demand_left: int = 0

        # How much demand was satisfied.
        self.satisfied_demand: int = 0

        # ...and how much demand per step that was missed due to not bidding high enough.
        self.missed_demand: int = 0


    def generate_messages(self, ctx: ph.Context):
        return [(self.exchange_id, BuyBid(self.id, self.demand, self.price))]
    
    @ph.agents.msg_handler(ClearedBid)
    def handle_cleared_bid(self, _ctx: ph.Context, msg: ph.Message):
        self.satisfied_demand = msg.payload.mwh
        self.demand_left -= msg.payload.mwh
        logger.debug("Customer Agent %s receives: %s from %s at price %s", self.id, msg.payload.mwh, msg.payload.seller_id, msg.payload.price)

    def pre_message_resolution(self, ctx: ph.Context):
        self.demand_left = self.demand
        self.satisfied_demand = 0
        self.missed_demand = 0

    def post_message_resolution(self, ctx: ph.Context):
        self.missed_demand = self.demand_left
    
    def reset(self):
        self.demand_left = 0

class DummyAgent(ph.StrategicAgent):
    def __init__(self, agent_id: ph.AgentID):
        super().__init__(agent_id)

        self.obs: float = 0

        self.observation_space = gym.spaces.Box(low=0.0, high=1.0, shape=(1,))

        self.action_space = gym.spaces.Box(low=0.0, high=1.0, shape=(1,))

    def encode_observation(self, ctx: ph.Context):
        return np.array([0.9])

    def decode_action(self, ctx: ph.Context, action):
        # We perform this action by sending a Bid message to the generator.
        return [("ExchangeAgent", DummyMsg("Hello"))]

    def compute_reward(self, ctx: ph.Context) -> float:
        return 0.9
    
    def reset(self):
        self.obs = self.action_space.sample()

# Strategic RL customer agent
# class CustomerAgent(ph.StrategicAgent):
#     def __init__(self, agent_id: ph.AgentID, generator_id: ph.AgentID):
#         super().__init__(agent_id)

#         # We need to store the generators's ID so we know who to send bids to.
#         self.generator_id: str = generator_id

#         # The Customer has a certain demand curve that we store.
#         # TODO: Load from data which is passed to each agent.
#         self.demand_curve: list = [
#             1000, 1100, 1200, 1300, 1400, 1600, 1700, 1800, 2000, 2200,
#             2100, 2000, 1800, 1600, 1400, 1500, 1700, 1800, 2000, 1900,
#             1700, 1500, 1300, 1200
#         ]

#         # We keep track of how much demand the customer has at current step..
#         self.demand: int = 0

#         # How much demand was satisfied.
#         self.satisfied_demand: int = 0

#         # ...and how much demand per step that was missed due to bidding high enough.
#         self.missed_demand: int = 0

#         # = [Demand, Satisfied Demand, Missed Demand]
#         self.observation_space = gym.spaces.Box(low=0.0, high=1.0, shape=(3,))

#         # = [Bidding price]
#         self.action_space = gym.spaces.Box(low=0.0, high=MAX_BID_PRICE, shape=(1,))


#     def pre_message_resolution(self, ctx: ph.Context):
#         self.satisfied_demand = 0
#         self.missed_demand = 0
    
        
#     @ph.agents.msg_handler(BidResponse)
#     def handle_bid_response(self, ctx: ph.Context, message: ph.Message):

#         # The customer receives a bid response which will tell if 
#         # demand was covered and at which price.
#         self.received_power = message.payload.size
#         self.price_paid = message.payload.price

#         if self.received_power == self.demand:
#             self.satisfied_demand = self.received_power 
#         else:
#             self.missed_demand =  self.demand
    

#     def encode_observation(self, ctx: ph.Context):

#         return np.array(
#             [
#                 self.demand / CUSTOMER_MAX_DEMAND,
#                 self.satisfied_demand / CUSTOMER_MAX_DEMAND,
#                 self.missed_demand / CUSTOMER_MAX_DEMAND
#             ],
#             dtype=np.float32,
#         )

#     def decode_action(self, ctx: ph.Context, action: np.ndarray):
   
#         # The action the customer takes is the price it will pay in order to satisfy its demand,
#         # clipped to the max allowed bid.

#         # TODO: the local variables and attributes is a mess here.
#         index = ctx.env_view.current_step-1
#         self.demand = self.demand_curve[index]

#         price_to_bid = min(float(action[0]), MAX_BID_PRICE)

#         requested_demand = self.demand

#         # We perform this action by sending a Bid message to the generator.
#         return [(self.generator_id, Bid(requested_demand, price_to_bid))]

#     def compute_reward(self, ctx: ph.Context) -> float:
#         # We reward the agent for satisfying demand
#         # We penalise the agent for missing demand.

#         return self.satisfied_demand - self.missed_demand - self.price_paid
#         # return self.satisfied_demand - self.missed_demand - (cost_weight * self.total_cost)

#     def reset(self):
#         self.satisfied_demand = 0 # Possibly just delete this function if no reset is needed between episodes?
#         self.missed_demand = 0 



class EL_Clearing_Env(ph.FiniteStateMachineEnv):
    def __init__(self, num_steps=24, **kwargs):
        # TODO: Add multiple buyers and sellers
  
        # Predefine supply and demand bids
        supply_bids = [("G1", 120, 0), ("G2", 50, 0), ("G3", 200, 15), 
                ("G4", 400, 30), ("G5", 60, 32.5), ("G6", 50, 34),
                ("G7", 60, 36), ("G8", 100, 37.5), ("G9", 70, 39),
                ("G10", 50, 40), ("G11", 70, 60), ("G12", 45, 70),
                ("G13", 50, 100), ("G14", 60, 150), ("G15", 50, 200)
                ]
        
        demand_bids = [("D1", 250, 200), ("D2", 300, 110), ("D3", 120, 100), 
                    ("D4", 80, 90), ("D5", 40, 85), ("D6", 70, 75),
                    ("D7", 60, 65), ("D8", 45, 40), ("D9", 30, 38),
                    ("D10", 35, 31), ("D11", 25, 24), ("D12", 10, 16),
                        ]

        # Define Agent IDs
        generator_ids = [f"G{i+1}" for i in range(len(supply_bids))]
        buyer_ids = [f"D{i+1}" for i in range(len(demand_bids))]

        # Initiate Agents
        dummy_agent = DummyAgent("DummyAgent")
        exchange_agent = ExchangeAgent("ExchangeAgent")
        generator_agents = []
        for gid, mwh, price in supply_bids:
            generator_agents.append(GeneratorAgent(gid, "ExchangeAgent", mwh, price))
        buyer_agents = []
        for id, mwh, price in demand_bids:
            buyer_agents.append(SimpleDemandAgent(id, "ExchangeAgent", mwh, price))

        # Define Network and create connections between Actors
        agents = [exchange_agent, dummy_agent] + generator_agents + buyer_agents
        network = ph.Network(agents)

        # Connect the agents
        network.add_connection("ExchangeAgent", "DummyAgent")
        for gid in generator_ids:
            network.add_connection("ExchangeAgent", gid)
        
        for id in buyer_ids:
            network.add_connection("ExchangeAgent", id)

        # Setup the FSM stages
        stages = [
            ph.FSMStage(
                stage_id="Bid Stage",
                next_stages=["Clearing Stage"],
                acting_agents=["DummyAgent"] + buyer_ids + generator_ids,
            ),
            ph.FSMStage(
                stage_id="Clearing Stage",
                next_stages=["Bid Stage"],
                acting_agents=["DummyAgent", "ExchangeAgent"],
            )
        ]

        super().__init__(
            num_steps=num_steps,
            network=network,
            initial_stage="Bid Stage",
            stages=stages,
            **kwargs,
        )

# TODO: correct metrics
# metrics = {
#     "CUSTOMER/demand": ph.metrics.SimpleAgentMetric("CUSTOMER", "demand", "mean"),
#     "CUSTOMER/satisfied_demand": ph.metrics.SimpleAgentMetric("CUSTOMER", "satisfied_demand", "mean"),
#     "CUSTOMER/missed_demand": ph.metrics.SimpleAgentMetric("CUSTOMER", "missed_demand", "mean"),
#     "GENERATOR/current_price": ph.metrics.SimpleAgentMetric("GENERATOR", "current_price", "mean")
# }

# Setup env
env = EL_Clearing_Env()

# Run
observations, _ = env.reset()
rewards = {}
infos = {}

while env.current_step < env.num_steps:
    logger.debug("Current step is %s", env.current_step)
    stage = env.current_stage
    logger.debug("Current stage is %s", env.current_stage)

    # print("\nobservations:")
    # print(observations)
    # print("\nrewards:")
    # print(rewards)
    # print("\ninfos:")
    # print(infos)

    actions = {}
    for aid, obs in observations.items():
        agent = env.agents[aid]
        if isinstance(agent, DummyAgent):
            actions[aid] = 0.9

    #print("\nactions:")
    #print(actions)

    step = env.step(actions)
    observations = step.observations
    rewards = step.rewards
    infos = step.infos