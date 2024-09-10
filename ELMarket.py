import sys
print(sys.argv)
from typing import List, Tuple
import logging

import matplotlib.pyplot as plt
import phantom as ph
from elmarket_agents import DummyAgent
from elmarket_env import EL_Clearing_Env

NUM_EPISODE_STEPS = 24
CURRENT_STEP = 0

NUM_CUSTOMERS = 1
CUSTOMER_MAX_DEMAND = 2200
MAX_BID_PRICE = 30

# logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
# logger = logging.getLogger("electricity-market")
# logger.setLevel(LOG_LEVEL)


ph.telemetry.logger.configure_print_logging(enable=True)
ph.telemetry.logger.configure_file_logging(file_path="log.json", append=False)

# Setup env
env = EL_Clearing_Env()

# Run
observations, _ = env.reset()
rewards = {}
infos = {}

while env.current_step < env.num_steps:

    # logger.debug("Current step is %s", env.current_step)
    # stage = env.current_stage
    # logger.debug("Current stage is %s", env.current_stage)

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