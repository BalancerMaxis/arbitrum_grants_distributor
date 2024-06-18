import json
import os
from collections import defaultdict
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from typing import Dict
from typing import List
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from gql import Client
from gql import gql
from gql.transport.requests import RequestsHTTPTransport
from pycoingecko import CoinGeckoAPI
from web3 import Web3
import importlib

from automation.constants import TOTAL_TOKENS_PER_EPOCH
from automation.constants import TOKENS_TO_FOLLOW_VOTING
from automation.constants import BALANCER_GAUGE_CONTROLLER_ABI
from automation.constants import CHAIN_NAME
from automation.constants import DYNAMIC_BOOST_CAP
from automation.constants import MIN_BAL_IN_USD_FOR_BOOST
from automation.constants import POOLS_SNAPSHOTS_QUERY
from automation.constants import DESIRED_DEFAULT_VOTE_CAP
from automation.constants import FILE_PREFIX
from automation.emissions_per_year import (
    get_emissions_per_week,
)
from automation.helpers import fetch_all_pools_info
from automation.helpers import get_abi
from automation.helpers import get_block_by_ts

# import boost_data, cap_override_data and fixed_emissions_per_pool from the python file specified in POOL_CONFIG
pool_config = importlib.import_module(f"automation.{FILE_PREFIX}")
boost_data = pool_config.boost_data
cap_override_data = pool_config.cap_override_data
fixed_emissions_per_pool = pool_config.fixed_emissions_per_pool
from bal_addresses import AddrBook
from bal_tools import Subgraph
from bal_addresses import to_checksum_address

# Configure Library objects for chain
addressbook = AddrBook(CHAIN_NAME)
subgraph = Subgraph(CHAIN_NAME)
BALANCER_GAUGE_CONTROLLER_ADDR = (
    AddrBook("mainnet").search_unique("GaugeController").address
)

# Build the whitelist
whitelist = []
for _pid in fixed_emissions_per_pool.keys():
    whitelist.append(_pid.lower())

# Make sure we have enough capacity to distribute all our votes.
# There is still an edge case here when some pools are capped under the final default cap and hence there is not
# capacity to distribute 100% of tokens
default_vote_cap = max(DESIRED_DEFAULT_VOTE_CAP, 100 / len(whitelist))
if not default_vote_cap == DESIRED_DEFAULT_VOTE_CAP:
    print(
        f"WARNING: Default vote cap was set to {DESIRED_DEFAULT_VOTE_CAP} but was overridden to {default_vote_cap} to ensure all tokens are distributed"
    )
else:
    print(
        f"Default vote cap set to {DESIRED_DEFAULT_VOTE_CAP} which should be sufficient to distribute all tokens"
    )


def get_root_dir() -> str:
    return os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


## Todo: remove once all subgraph interactions have moved to bal_tools
def make_gql_client(url: str) -> Optional[Client]:
    transport = RequestsHTTPTransport(url=url, retries=3)
    return Client(
        transport=transport, fetch_schema_from_transport=True, execute_timeout=60
    )


def get_balancer_pool_fees_between_timestamps(start_ts: int, end_ts: int) -> List[Dict]:
    """
    Fetch balancer pool snapshots from the subgraph and calculate protocol fees collected for each pool.
    This works like this: fetch snapshots by time range from the graph, then find the first and last snapshot
    and calculate the difference between them. This will give us the protocol fees collected for the period.
    """
    ## TODO: move to bal_tools
    client = make_gql_client(subgraph.get_subgraph_url("core"))
    all_snapthots = []
    limit = 100
    offset = 0
    while True:
        result = client.execute(
            gql(
                POOLS_SNAPSHOTS_QUERY.format(
                    first=limit, skip=offset, start_ts=start_ts, end_ts=end_ts
                )
            )
        )
        all_snapthots.extend(result["poolSnapshots"])
        offset += limit
        if len(result["poolSnapshots"]) < limit - 1:
            break
    # Need to group by pool address, since there are multiple snapshots per pool and we need to calculate
    # difference between first and last snapshot
    pools = defaultdict(list)
    for snapshot in all_snapthots:
        pools[snapshot["pool"]["address"]].append(snapshot.get("protocolFee", 0))
    # Now calculate the difference between first and last snapshot
    fees_snapshots = []
    for pool_addr, snapshots in pools.items():
        if len(snapshots) > 1:
            # Convert to int with respect that there might be null values and string values
            first_snapshot = float(snapshots[0]) if snapshots[0] else 0
            last_snapshot = float(snapshots[-1]) if snapshots[-1] else 0
            fee_collected = first_snapshot - last_snapshot
            assert fee_collected >= 0, f"Fee collected for pool {pool_addr} is negative"
            fees_snapshots.append(
                {
                    "pool": {
                        "address": pool_addr,
                    },
                    "protocolFee": fee_collected,
                }
            )
    return fees_snapshots


def get_bal_token_price() -> float:
    """
    Fetch bal token price from coingecko
    """
    # fetch balancer token usd price:
    cg = CoinGeckoAPI()
    return cg.get_price(ids="balancer", vs_currencies="usd")["balancer"]["usd"]


def recur_distribute_unspend_tokens(
        max_tokens_per_pool: Dict, tokens_gauge_distributions: Dict
) -> None:
    """
    Recursively distribute unspent tokens to uncapped gauges proportionally to their voting weight until
    there is no unspent tokens left
    """
    unspent_tokens = TOTAL_TOKENS_PER_EPOCH - sum(
        [gauge["distribution"] for gauge in tokens_gauge_distributions.values()]
    )
    print(f"recursively distributing {unspent_tokens} unspent tokens")
    if unspent_tokens > 0:
        # Find out total voting weight of uncapped gauges and mark it as 100%:
        total_uncapped_weight = sum(
            [
                g["voteWeight"]
                for g in [
                gauge
                for addr, gauge in tokens_gauge_distributions.items()
                if gauge["distribution"] < max_tokens_per_pool[addr]
            ]
            ]
        )
        # if total uncapped weight is 0, then we can not continue
        print(f"Distributing {total_uncapped_weight} of vote weight is still uncapped.")
        if total_uncapped_weight == 0:
            print(
                f"WARNING: Was not able to get all tokens under the cap due to a lack of capacity. Double check that final distributions are sensible"
            )
        # Iterate over uncapped gauges and distribute unspent tokens
        # proportionally to their voting weight which is total uncapped weight
        for a, uncap_gauge in {
            addr: gauge
            for addr, gauge in tokens_gauge_distributions.items()
            if gauge["distribution"] < max_tokens_per_pool[addr]
        }.items():
            # For each loop calculate unspent tokens
            unspent_tokens = TOTAL_TOKENS_PER_EPOCH - sum(
                [gauge["distribution"] for gauge in tokens_gauge_distributions.values()]
            )
            # Don't distribute more than vote cap
            distribution = min(
                uncap_gauge["distribution"]
                + unspent_tokens * uncap_gauge["voteWeight"] / total_uncapped_weight,
                max_tokens_per_pool[a],
            )
            uncap_gauge["distribution"] = distribution
            uncap_gauge["pctDistribution"] = (
                    uncap_gauge["distribution"] / TOTAL_TOKENS_PER_EPOCH * 100
            )
    # Call recursively if there is still unspent tokens
    if (
            TOTAL_TOKENS_PER_EPOCH
            - sum([g["distribution"] for g in tokens_gauge_distributions.values()])
            > 0
    ):
        recur_distribute_unspend_tokens(max_tokens_per_pool, tokens_gauge_distributions)


def generate_and_save_transaction(
        tokens_gauge_distributions: Dict, start_date: datetime, end_date: datetime
) -> Dict:
    """
    Take tx template and inject data into it
    """
    # Dump into output.json using:
    with open(f"{get_root_dir()}/data/output_tx_template.json") as f:
        output_data = json.load(f)
    # Find transaction with func name `setRecipientList` and dump gauge
    gauge_distributions = tokens_gauge_distributions.values()
    for tx in output_data["transactions"]:
        if tx["contractMethod"]["name"] == "setRecipientList":
            # Inject list of gauges addresses:
            tx["contractInputsValues"][
                "gaugeAddresses"
            ] = f"[{','.join([gauge['recipientGaugeAddr'] for gauge in gauge_distributions])}]"
            # Inject vote weights:
            # Dividing by 2 since we are distributing for 2 weeks and 1 week is a period
            tx["contractInputsValues"][
                "amountsPerPeriod"
            ] = f"[{','.join([str(int(Decimal(gauge['distribution']) * Decimal(1e18) / 2)) for gauge in gauge_distributions])}]"
            tx["contractInputsValues"][
                "maxPeriods"
            ] = f"[{','.join(['2' for gauge in gauge_distributions])}]"
        if tx["contractMethod"]["name"] == "transfer":
            tx["contractInputsValues"]["amount"] = str(
                int(Decimal(TOKENS_TO_FOLLOW_VOTING) * Decimal(1e18))
            )

    # Dump back to tokens_distribution_for_msig.json
    with open(
            f"{get_root_dir()}/output/{FILE_PREFIX}_{start_date.date()}_{end_date.date()}.json",
            "w",
    ) as _f:
        json.dump(output_data, _f, indent=4)
    return output_data


def run_stip_pipeline(end_date: int) -> None:
    """
    Main function to execute STIP calculations
    """
    load_dotenv()
    ####
    # Collect data
    ####
    web3_mainnet = Web3(Web3.HTTPProvider(os.environ["ETHNODEURL"]))
    end_date = datetime.fromtimestamp(end_date)
    start_date = end_date - timedelta(days=14)
    start_ts = int(start_date.timestamp())
    end_ts = int(end_date.timestamp())
    target_block = get_block_by_ts(end_ts, chain="mainnet")
    pool_snapshots = get_balancer_pool_fees_between_timestamps(start_ts, end_ts)
    print(f"Collected data for dates: {start_date.date()} - {end_date.date()}")
    print(f"Block height at the end date: {target_block}")
    emissions_per_week = get_emissions_per_week()

    # Fetch all pools from Balancer API
    all_pools = fetch_all_pools_info(addressbook.chain)

    # Collect gauges
    gauges = {}
    for pool in all_pools:
        # Only collect gauges for the whitelisted pools on the proper chain that are not killed
        if (
                pool["chain"].lower() == addressbook.chain
                and pool["gauge"]["isKilled"] is False
                and pool["id"].lower() in whitelist
        ):
            _gauge_addr = to_checksum_address(pool["gauge"]["address"])
            gauges[_gauge_addr] = {
                "gaugeAddress": to_checksum_address(pool["gauge"]["address"]),
                "poolAddress": to_checksum_address(pool["address"]),
                "pool": to_checksum_address(pool["address"]),
                "symbol": pool["symbol"],
                "id": pool["id"],
            }
    print(f"Total gauges eligible for STIP emissions: {len(gauges)}")

    pool_protocol_fees = {}
    # Collect protocol fees from the pool snapshots:
    for gauge_addr, gauge_data in gauges.items():
        for pool_snapshot in pool_snapshots:
            if Web3.to_checksum_address(
                    pool_snapshot["pool"]["address"]
            ) == Web3.to_checksum_address(gauge_data["pool"]):
                # Since snapshots are sorted by timestamp descending,
                # we can just take the first one we find for each pool and break
                protocol_fee = (
                    float(pool_snapshot["protocolFee"])
                    if pool_snapshot["protocolFee"]
                    else 0
                )
                pool_protocol_fees[Web3.to_checksum_address(gauge_addr)] = protocol_fee
                break
    print(f"Total protocol fees collected: {sum(pool_protocol_fees.values())}")
    # Apply boost data to gauges
    vote_weights = {}
    combined_boost = {}
    # Dynamic boost data to print out in the final table
    dynamic_boosts = {}
    # Collect gauge voting weights from the gauge controller on chain
    gauge_c_contract = web3_mainnet.eth.contract(
        address=BALANCER_GAUGE_CONTROLLER_ADDR,
        abi=BALANCER_GAUGE_CONTROLLER_ABI,
    )
    bal_token_price = get_bal_token_price()
    for gauge_addr, gauge_data in gauges.items():
        weight = (
                gauge_c_contract.functions.gauge_relative_weight(
                    Web3.to_checksum_address(gauge_addr)
                ).call(block_identifier=target_block)
                / 1e18
                * 100
        )
        gauges[gauge_addr]["weightNoBoost"] = weight
        # Calculate dynamic boost. Formula is `[Fees earned*multipler/value of bal emitted per pool]`
        # Value of bal earned must always be >1 to allow for the desired effect from division.
        dollar_value_of_bal_emitted = (
                (weight / 100) * emissions_per_week * bal_token_price
        )
        if (
                dollar_value_of_bal_emitted >= MIN_BAL_IN_USD_FOR_BOOST
                and dollar_value_of_bal_emitted > 1
        ):
            dynamic_boost = min(
                pool_protocol_fees.get(gauge_addr, 0) / dollar_value_of_bal_emitted,
                DYNAMIC_BOOST_CAP,
            )
            print(
                f"Gauge {gauge_addr} has a fees of {pool_protocol_fees.get(gauge_addr, 0)} and earned {dollar_value_of_bal_emitted} in USD BAL rendering a raw dynamic boost of {dynamic_boost}")
        else:
            dynamic_boost = 1.0
        if dynamic_boost < 1:
            dynamic_boost = 1.0
        dynamic_boosts[gauge_addr] = dynamic_boost

        # Now calculate the final boost value, which uses formula - (dynamic boost + fixed boost) - 1
        boost = (dynamic_boost + boost_data.get(gauge_data["id"], 1)) - 1
        combined_boost[gauge_addr] = boost
        weight *= boost
        vote_weights[gauge_addr] = weight
        gauges[gauge_addr]["voteWeight"] = weight
    print(
        f"Total boosted %veBAL vote weight across eligible ARB gauges: {sum(vote_weights.values())}"
    )

    ####
    # Handle Caps
    ####

    # Vote caps in percents are calculated as a percentage of the total amount of arb to distribute
    # Custom gauge caps taken from override data in constants.py, calculated as a percentage of the total amount of
    # arb to distribute
    percent_vote_caps_per_gauge = {}
    max_tokens_per_gauge = {}
    for gauge_addr in gauges.keys():
        percent_vote_caps_per_gauge[gauge_addr] = cap_override_data.get(
            gauges[gauge_addr]["id"].lower(), default_vote_cap
        )
        max_tokens_per_gauge[gauge_addr] = (
                percent_vote_caps_per_gauge[gauge_addr] / 100 * TOTAL_TOKENS_PER_EPOCH
        )
    # Calculate total weight
    total_weight = sum([gauge["voteWeight"] for gauge in gauges.values()])
    gauge_distributions = {}
    for gauge_addr, gauge_data in gauges.items():
        gauge_addr = Web3.to_checksum_address(gauge_addr)
        # Calculate distribution based on vote weight and total weight
        to_distribute = (
                TOKENS_TO_FOLLOW_VOTING * gauge_data["voteWeight"] / total_weight
        )
        # Add in fixed incentives
        to_distribute += fixed_emissions_per_pool.get(gauge_data["id"], 0)
        # Cap distribution
        to_distribute = (
            to_distribute
            if to_distribute < max_tokens_per_gauge[gauge_addr]
            else max_tokens_per_gauge[gauge_addr]
        )
        # Get L2 gauge addr

        ## Note this ABI should work for most chains given the functions we need
        mainnet_root_gauge_contract = web3_mainnet.eth.contract(
            address=Web3.to_checksum_address(gauge_addr), abi=get_abi("ArbRootGauge")
        )
        gauge_distributions[gauge_addr] = {
            "recipientGaugeAddr": mainnet_root_gauge_contract.functions.getRecipient().call(),
            "poolAddress": gauge_data["poolAddress"],
            "symbol": gauge_data["symbol"],
            "voteWeight": gauge_data["voteWeight"],
            "voteWeightNoBoost": gauge_data["weightNoBoost"],
            "distribution": to_distribute
            if to_distribute < max_tokens_per_gauge[gauge_addr]
            else max_tokens_per_gauge[gauge_addr],
            "pctDistribution": to_distribute / TOTAL_TOKENS_PER_EPOCH * 100,
            "boost": combined_boost.get(gauge_addr, 1),
            "staticBoost": boost_data.get(gauges[gauge_addr]["id"], 1),
            "dynamicBoost": dynamic_boosts.get(gauge_addr, 1),
            "cap": f"{percent_vote_caps_per_gauge[gauge_addr]}%",
            "fixedIncentive": fixed_emissions_per_pool[gauge_data["id"]],
        }
    recur_distribute_unspend_tokens(max_tokens_per_gauge, gauge_distributions)
    print(
        f"Unspent arb: {TOTAL_TOKENS_PER_EPOCH - sum([gauge['distribution'] for gauge in gauge_distributions.values()])}"
    )
    print(
        f"Tokens distributed: {sum([gauge['distribution'] for gauge in gauge_distributions.values()])}"
    )

    # # Remove  gauges with 0 distribution
    gauge_distributions = {
        addr: gauge
        for addr, gauge in gauge_distributions.items()
        if gauge["distribution"] > 0
    }

    gauge_distributions_df = pd.DataFrame.from_dict(gauge_distributions, orient="index")
    gauge_distributions_df = gauge_distributions_df.sort_values(
        by="pctDistribution", ascending=False
    )
    print(
        f"Total arb distributed incl bonus: "
        f"{sum([gauge['distribution'] for gauge in gauge_distributions.values()])}"
    )
    # Export to csv
    gauge_distributions_df.to_csv(
        f"{get_root_dir()}/output/{FILE_PREFIX}_{start_date.date()}_{end_date.date()}.csv",
        index=False,
    )

    generate_and_save_transaction(gauge_distributions, start_date, end_date)
