from automation.lstGrant import run_stip_pipeline
import argparse

# TS_NOW = 1702512000
# TS_NOW = 1703721600 # 28-12-2023
TS_NOW = 1718143200  # 2024-06-13

parser = argparse.ArgumentParser()
parser.add_argument(
    "--ts_bound", help="Timestamp up to which to run", type=int, required=False
)

if __name__ == "__main__":
    ts_now = parser.parse_args().ts_bound or TS_NOW
    run_stip_pipeline(ts_now)
