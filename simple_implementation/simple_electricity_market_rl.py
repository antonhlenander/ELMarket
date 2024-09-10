import sys
from typing import List, Tuple

import gymnasium as gym
import matplotlib.pyplot as plt
import numpy as np
import phantom as ph
from phantom.types import AgentID


NUM_EPISODE_STEPS = 24
CURRENT_STEP = 0

NUM_CUSTOMERS = 1
CUSTOMER_MAX_DEMAND = 2200
MAX_BID_PRICE = 30


@ph.msg_payload("CustomerAgent", "GeneratorAgent")
class Bid:
    """
    A bid to buy a certain amount of MWh at a certain price.

    Attributes:
    -----------
    size (int):         the amount of MWh
    price (float):      price of bid
    customer_id (int):  customer id
    """

    size: int
    price: float
    # customer_id: (int)

@ph.msg_payload("GeneratorAgent", "CustomerAgent")
class BidResponse:
    """
    A response to customer bid, letting the customer know if the order was cleared or not.

    Attributes:
    -----------
    size (int):            the amount of MWh cleared
    price (float):         the price at which order was cleared
    generator_id (int):    generator id
    """
    size: int
    price: float    

class GeneratorAgent(ph.Agent):
    def __init__(self, agent_id: str):
        super().__init__(agent_id)

        self.sell_prices: list = [
            10, 11, 12, 13, 14, 15, 16, 17, 20, 22, 
            20, 18, 16, 14, 12, 13, 15, 17, 20, 19,
            17, 15, 13, 9
        ]

    @ph.agents.msg_handler(Bid)
    def handle_bid(self, ctx: ph.Context, message: ph.Message):
        # Handle a bid for certain demand at certain price.

        # Get the sell price at current time step.
        index = ctx.env_view.current_step-1
        self.current_price = self.sell_prices[index]

        # The demand requested to cover (generator has infinite capacity as is)
        received_demand = message.payload.size
        # Get the received offer.
        received_offer = message.payload.price

        sell_price = 0

        if received_offer >= self.current_price:
            sell_price = received_offer
        
        return [(message.sender_id, BidResponse(received_demand, sell_price))]


class CustomerAgent(ph.StrategicAgent):
    def __init__(self, agent_id: ph.AgentID, generator_id: ph.AgentID):
        super().__init__(agent_id)

        # We need to store the generators's ID so we know who to send bids to.
        self.generator_id: str = generator_id

        # The Customer has a certain demand curve that we store.
        # TODO: Load from data which is passed to each agent.
        self.demand_curve: list = [
            1000, 1100, 1200, 1300, 1400, 1600, 1700, 1800, 2000, 2200,
            2100, 2000, 1800, 1600, 1400, 1500, 1700, 1800, 2000, 1900,
            1700, 1500, 1300, 1200
        ]

        # We keep track of how much demand the customer has at current step..
        self.demand: int = 0

        # How much demand was satisfied.
        self.satisfied_demand: int = 0

        # ...and how much demand per step that was missed due to bidding high enough.
        self.missed_demand: int = 0

        # = [Demand, Satisfied Demand, Missed Demand]
        self.observation_space = gym.spaces.Box(low=0.0, high=1.0, shape=(3,))

        # = [Bidding price]
        self.action_space = gym.spaces.Box(low=0.0, high=MAX_BID_PRICE, shape=(1,))


    def pre_message_resolution(self, ctx: ph.Context):
        self.satisfied_demand = 0
        self.missed_demand = 0
    
        
    @ph.agents.msg_handler(BidResponse)
    def handle_bid_response(self, ctx: ph.Context, message: ph.Message):

        # The customer receives a bid response which will tell if 
        # demand was covered and at which price.
        self.received_power = message.payload.size
        self.price_paid = message.payload.price

        if self.received_power == self.demand:
            self.satisfied_demand = self.received_power 
        else:
            self.missed_demand =  self.demand
    

    def encode_observation(self, ctx: ph.Context):

        return np.array(
            [
                self.demand / CUSTOMER_MAX_DEMAND,
                self.satisfied_demand / CUSTOMER_MAX_DEMAND,
                self.missed_demand / CUSTOMER_MAX_DEMAND
            ],
            dtype=np.float32,
        )

    def decode_action(self, ctx: ph.Context, action: np.ndarray):
   
        # The action the customer takes is the price it will pay in order to satisfy its demand,
        # clipped to the max allowed bid.

        # TODO: the local variables and attributes is a mess here.
        index = ctx.env_view.current_step-1
        self.demand = self.demand_curve[index]

        price_to_bid = min(float(action[0]), MAX_BID_PRICE)

        requested_demand = self.demand

        # We perform this action by sending a Bid message to the generator.
        return [(self.generator_id, Bid(requested_demand, price_to_bid))]

    def compute_reward(self, ctx: ph.Context) -> float:
        # We reward the agent for satisfying demand
        # We penalise the agent for missing demand.

        return self.satisfied_demand - self.missed_demand - self.price_paid
        # return self.satisfied_demand - self.missed_demand - (cost_weight * self.total_cost)

    def reset(self):
        self.satisfied_demand = 0 # Possibly just delete this function if no reset is needed between episodes?
        self.missed_demand = 0 



class ElectricitySupplyEnv(ph.PhantomEnv):
    def __init__(self):
        # Define agent IDs
        customer_id = "CUSTOMER"

        generator_id = "GENERATOR"

        customer_agent = CustomerAgent(customer_id, generator_id=generator_id)
        generator_agent = GeneratorAgent(generator_id)

        agents = [generator_agent, customer_agent]

        # Define Network and create connections between Actors
        network = ph.Network(agents)
        
        # Connect the shop to the factory
        network.add_connection(generator_id, customer_id)

        super().__init__(num_steps=NUM_EPISODE_STEPS, network=network)

# TODO: correct metrics
metrics = {
    "CUSTOMER/demand": ph.metrics.SimpleAgentMetric("CUSTOMER", "demand", "mean"),
    "CUSTOMER/satisfied_demand": ph.metrics.SimpleAgentMetric("CUSTOMER", "satisfied_demand", "mean"),
    "CUSTOMER/missed_demand": ph.metrics.SimpleAgentMetric("CUSTOMER", "missed_demand", "mean"),
    "GENERATOR/current_price": ph.metrics.SimpleAgentMetric("GENERATOR", "current_price", "mean")
}


if sys.argv[1] == "train":
    ph.utils.rllib.train(
        algorithm="PPO",
        env_class=ElectricitySupplyEnv,
        env_config={},
        iterations=500,
        checkpoint_freq=50,
        policies={"customer_policy": ["CUSTOMER"]},
        metrics=metrics,
        results_dir="~/ray_results/electricity_market",
        num_workers=1
    )

elif sys.argv[1] == "rollout":
    results = ph.utils.rllib.rollout(
        directory="~/ray_results/electricity_market/LATEST",
        num_repeats=1,
        num_workers=1,
        metrics=metrics,
    )

    results = list(results)

    customer_actions = []
    customer_demand = []
    customer_satisfied_demand = []
    customer_missed_demand = []
    generator_prices = []

    for rollout in results:
        # Adds all customer actions sequentially to one big list
        # TODO: Take mean of all values across each timestep (vertically)
        # Episode1: a1, a2, a3, a4, a5
        # Episode2: a1, a2, a3, a4, a5
        # Mean:     m1, m2, m3, m4, m5
        customer_actions += list(
            int(round(x[0])) for x in rollout.actions_for_agent("CUSTOMER")
        )
        customer_demand += list(rollout.metrics["CUSTOMER/demand"])
        customer_satisfied_demand += list(rollout.metrics["CUSTOMER/satisfied_demand"])
        customer_missed_demand += list(rollout.metrics["CUSTOMER/missed_demand"])
        generator_prices += list(rollout.metrics["GENERATOR/current_price"])

    # print (results)
    # print(customer_actions)
    print(generator_prices)

    # Plot agent acions for each step
    plt.plot(customer_actions)
    plt.plot(generator_prices)
    plt.title("Customer action at each hour (price bid)")
    plt.xlabel("Hour")
    plt.ylabel("Price")
    plt.savefig("electricity_market_customer_bids")
    plt.close()

    # Plot distribution of shop action (stock request) per step for all rollouts
    plt.hist(customer_actions, bins=30)
    plt.title("Distribution of Customer Action Values (Price Bid Per Step)")
    plt.xlabel("Customer Action (Price Bid Per Step)")
    plt.ylabel("Frequency")
    plt.savefig("electricity_market_customer_action_values.png")
    plt.close()

    plt.hist(customer_demand, bins=30)
    plt.title("Distribution of Customer Demand")
    plt.xlabel("Customer Demand (Per Step)")
    plt.ylabel("Frequency")
    plt.savefig("electricity_market_customer_demand.png")
    plt.close()

    plt.hist(customer_satisfied_demand, bins=20)
    plt.axvline(np.mean(customer_satisfied_demand), c="k")
    plt.title("Distribution of Customer Satisfied Demand")
    plt.xlabel("Customer Demand Satisfied (Per Step)")
    plt.ylabel("Frequency")
    plt.savefig("electricity_market_demand_satisfied.png")
    plt.close()

    plt.hist(customer_missed_demand, bins=20)
    plt.title("Distribution of Customer Missed Demand")
    plt.xlabel("Customer Missed Demand (Per Step)")
    plt.ylabel("Frequency")
    plt.savefig("electricity_market_customer_missed_demand.png")
    plt.close()
