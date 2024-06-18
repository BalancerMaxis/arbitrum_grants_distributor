from web3 import Web3
from automation.constants import (
    FIXED_INCENTIVE_TOKENS_PER_EPOCH,
    DESIRED_DEFAULT_VOTE_CAP,
)

#####
# Notes for the maintainers of this config file
#####
# Default cap was set to 10% when this comment was written, will be used if not overridden. (see constants.py)
# Default fixedBoost is 1 if not specified
# Default fixexEmissions is 0 if not specified
# All fixedEmissions should equal up to under constants.py/FIXED_INCENTIVE_TOKENS_PER_EPOCH

# meta information is not required to run, and you can put whatever you want there in json format as notes.
# gauge

# {
#         "pool_id": "0x5f8893506ddc4c271837187d14a9c87964a074dc000000000000000000000106",
#         "meta": {"symbol": "eth-trip", "boostReason": "100% LST"},
#         "fixedBoost": 1.5,
#         "capOverride": 20,
#         "fixedEmissions": 3_000,
#     },

#  THIS CONFIG IS FOR ARBITRUM CHAIN - includes all current core pools with no modifiers
ACTIVE_POOLS_AND_OVERRIDES = [
    ## for each pool in core_pools_arbi, add a dict with pool_id and symbol/meta
    ## like the example above
    ## {
    ##     "pool_id": "0x125bc5a031b2db6733bfa35d914ffa428095978b000200000000000000000514",
    ##     "meta": {"symbol": "ECLP-AUSDC-AUSDT"},
    ## },
    ## {
    {
        "pool_id": "0x125bc5a031b2db6733bfa35d914ffa428095978b000200000000000000000514",
        "meta": {"symbol": "ECLP-AUSDC-AUSDT"},
    },
    {
        "pool_id": "0x260dbd54d87a10a0fc9d08622ebc969a3bf4e6bb000200000000000000000536",
        "meta": {"symbol": "jitoSOL/wstETH"},
    },
    {
        "pool_id": "0x2ce4457acac29da4736ae6f5cd9f583a6b335c270000000000000000000004dc",
        "meta": {"symbol": "sFRAX/4POOL"},
    },
    {
        "pool_id": "0x2d6ced12420a9af5a83765a8c48be2afcd1a8feb000000000000000000000500",
        "meta": {"symbol": "cbETH/rETH/wstETH"},
        "fixedBoost": 1.5,
    },
    {
        "pool_id": "0x3fd4954a851ead144c2ff72b1f5a38ea5976bd54000000000000000000000480",
        "meta": {"symbol": "ankrETH/wstETH-BPT"},
        "fixedBoost": 1.5,
    },
    {
        "pool_id": "0x451b0afd69ace11ec0ac339033d54d2543b088a80000000000000000000004d5",
        "meta": {"symbol": "plsRDNT-Stable"},
    },
    {
        "pool_id": "0x9791d590788598535278552eecd4b211bfc790cb000000000000000000000498",
        "meta": {"symbol": "wstETH-WETH-BPT"},
    },
    {
        "pool_id": "0xb61371ab661b1acec81c699854d2f911070c059e000000000000000000000516",
        "meta": {"symbol": "ezETH/wstETH"},
        "fixedBoost": 1.5,
    },
    {
        "pool_id": "0xc2598280bfea1fe18dfcabd21c7165c40c6859d30000000000000000000004f3",
        "meta": {"symbol": "wstETH/sfrxETH"},
        "fixedBoost": 1.5,
    },
    {
        "pool_id": "0xd0ec47c54ca5e20aaae4616c25c825c7f48d40690000000000000000000004ef",
        "meta": {"symbol": "rETH/wETH BPT"},
    },
    {
        "pool_id": "0xef0c116a2818a5b1a5d836a291856a321f43c2fb00020000000000000000053a",
        "meta": {"symbol": "ECLP-WOETH-WETH"},
    },
    {
        "pool_id": "0x9f8ed1acfe0c863381b9081aff2144fc867aa7730002000000000000000004d4",
        "meta": {"symbol": "ANKR:ankrETH"},
    },
    {
        "pool_id": "0x90e6cb5249f5e1572afbf8a96d8a1ca6acffd73900000000000000000000055c",
        "meta": {"symbol": "rsETH-wETH"},
        "fixedEmissions": 2000/2, #/2 for aura split
    },
    {
        "pool_id": "0xcdcef9765d369954a4a936064535710f7235110a000200000000000000000558",
        "meta": {"symbol": "weETH-wstETH ECLP"},
        "fixedBoost": 1.5,
        "fixedEmissions": 2000/2, #/2 for Aura split
    },
]


# assert that the total sum of all fixedEmissions is equal to FIXED_INCENTIVE_TOKENS_PER_EPOCH
total_fixed_emissions = sum(
    [x.get("fixedEmissions", 0) for x in ACTIVE_POOLS_AND_OVERRIDES]
)
assert (
    total_fixed_emissions == FIXED_INCENTIVE_TOKENS_PER_EPOCH
), f"Sum of fixed emissions configured:{total_fixed_emissions} does not equal FIXED_INCENTIVE_TOKENS_PER_EPOCH:{FIXED_INCENTIVE_TOKENS_PER_EPOCH} configured in constants.py"

# Load static boost data
boost_data = {}
cap_override_data = {}
fixed_emissions_per_pool = {}
# Load static boost here
for pooldata in ACTIVE_POOLS_AND_OVERRIDES:
    pool_id_lower = pooldata["pool_id"].lower()
    boost_data[pool_id_lower] = pooldata.get("fixedBoost", 1)
    cap_override_data[pool_id_lower] = pooldata.get(
        "capOverride", DESIRED_DEFAULT_VOTE_CAP
    )
    fixed_emissions_per_pool[pool_id_lower] = pooldata.get("fixedEmissions", 0)
