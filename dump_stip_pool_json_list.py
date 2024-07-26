from automation.arbitrum_stip_bridge_start_q2_2024 import ACTIVE_POOLS_AND_OVERRIDES
import json

# Run this script, generate an up to date json file, then open a PR in the metadata repo to replace the existing file
# https://github.com/balancer/metadata/blob/main/pools/categories/arbitrum_grants.json

# Start with a list of custom pools/overrtides
pool_list = [
    "0x46472cba35e6800012aa9fcc7939ff07478c473e00020000000000000000056c",  ## Tokenlogic direct incentives, no yield fees, not on whitelist
    "0xf890360473c12d8015da8dbf7af11da87337a065000000000000000000000570",  ## Tokenlogic direct incentives, no yield fees, not on whitelist
]

# Add everything from our whitelist
for pool in ACTIVE_POOLS_AND_OVERRIDES:
    pool_list.append(pool["pool_id"])
with open("arbitrum_grants.json", "w") as f:
    json.dump(pool_list, f, indent=1)
