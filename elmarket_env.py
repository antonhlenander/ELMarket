import phantom as ph
import gymnasium as gym
import numpy as np

from elmarket_agents import DummyAgent, ExchangeAgent, GeneratorAgent, SimpleDemandAgent

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