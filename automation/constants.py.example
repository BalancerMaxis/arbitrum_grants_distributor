from web3 import Web3

# There should be a pool_config file named $FILE_PREFIX.py in the automation directory that holds the running pool config
# Outputs will also use this prefix
FILE_PREFIX = "example_op_config"

CHAIN_NAME = "optimism"
CURRENT_YEAR = 2024
# How many incentives should be taken away from vote following to be distributed as fixed incentives?  Per 2 week epoch
FIXED_INCENTIVE_TOKENS_PER_EPOCH = 1_500
# Total number of tokens available per 2 week epoch
TOTAL_TOKENS_PER_EPOCH = 7_520
DYNAMIC_BOOST_CAP = 3
MIN_BAL_IN_USD_FOR_BOOST = 200
TOKENS_TO_FOLLOW_VOTING = TOTAL_TOKENS_PER_EPOCH - FIXED_INCENTIVE_TOKENS_PER_EPOCH
DESIRED_DEFAULT_VOTE_CAP = 30

BALANCER_GAUGE_CONTROLLER_ABI = [
    {
        "stateMutability": "view",
        "type": "function",
        "name": "gauge_relative_weight",
        "inputs": [{"name": "addr", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "stateMutability": "view",
        "type": "function",
        "name": "gauge_relative_weight",
        "inputs": [
            {"name": "addr", "type": "address"},
            {"name": "time", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

# TODO at some point snapshot queries should be moved to bal_tools  also lstGrant.py to think about.
# Query to fetch pool snapshots
POOLS_SNAPSHOTS_QUERY = """
{{
  poolSnapshots(
    first: {first}
    skip: {skip}
    orderBy: timestamp
    orderDirection: desc
    where: {{timestamp_gte: {start_ts}, timestamp_lt: {end_ts}}}
  ) {{
    pool {{
      address
      id
      symbol
    }}
    timestamp
    protocolFee
    swapFees
    swapVolume
    liquidity
  }}
}}
"""
