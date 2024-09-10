import phantom as ph
from typing import Iterable, Sequence
from clearing_electricity_market import SellBid, BuyBid

class Market:

    def market_clearing(
        self, supply_bids: Sequence[ph.Message[SellBid]], demand_bids: Sequence[ph.Message[BuyBid]]):
        """
        Market clearing algorithm with uniform pricing and unique bid identifiers.
        
        Parameters:
        - supply_bids: List of tuples (id, MWh, price) representing supply bids.
        - demand_bids: List of tuples (id, MWh, price) representing demand bids.
        
        Returns:
        - cleared_bids: List of tuples showing matched supply and demand (supply_id, demand_id, matched MWh, price, status).
        - clearing_price: The uniform market clearing price.
        """
        # Step 1: Sort bids by price
        supply_bids.sort(key=lambda x: x[2])  # Sort by price ascending (cheapest first)
        demand_bids.sort(key=lambda x: x[2], reverse=True)  # Sort by price descending (most expensive first)

        # Step 2: Matching process
        cleared_bids: list = []
        non_cleared_bids: list = []
        total_supplied: int = 0
        total_demanded: int = 0
        clearing_price: float = 0
        i, j = 0, 0  # indices for supply and demand lists

        # Step 3: Traverse and match bids
        while i < len(supply_bids) and j < len(demand_bids):
            supply_bid = supply_bids[i].payload

            demand_bid = demand_bids[j].payload

            #supply_id, supply_mwh, supply_price = supply_bids[i].payload
            #demand_id, demand_mwh, demand_price = demand_bids[j].payload

            # If the demand price is less than the supply price, stop clearing (no match possible)
            if demand_bid.price < supply_bid.price:
                break

            # Determine the amount to match (min of available supply and demand)
            match_mwh = min(supply_bid.mwh, demand_bid.mwh)

            # Record the match (uniform price is the price at which this match happens)
            clearing_price = min(supply_bid.price, demand_bid.price)  # Uniform price determined at the match point
            cleared_bids.append((supply_bid.seller_id, demand_bid.buyer_id, match_mwh))


            # Update the remaining supply and demand
            supply_bids[i] = (supply_bid.seller_id, supply_bid.mwh - match_mwh, supply_bid.price)
            demand_bids[j] = (demand_bid.buyer_id, demand_bid.mwh - match_mwh, demand_bid.price)

            # Total MWh supplied and demanded
            total_supplied += match_mwh
            total_demanded += match_mwh

            # Move to the next bid if fully fulfilled
            if supply_bids[i].mwh == 0:
                i += 1
            if demand_bids[j].mwh == 0:
                j += 1


        for bid in cleared_bids:
            bid.
        # Step 4: Return results
        return cleared_bids, clearing_price
    



    # Example Usage (id, MWh, price)
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

    cleared_bids, clearing_price = market_clearing(supply_bids, demand_bids)

    print("Cleared Bids:", cleared_bids)
    print("Market Clearing Price:", clearing_price)
