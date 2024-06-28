from bal_tools import Aura
import json
import os
import copy
import math
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Dict
from automation.constants import FILE_PREFIX

precision = Decimal(
    "0." + "0" * 9 + "1"
)  # 10 0s after the dot is insignificant for our purposes and takes care of rounding errors.


def get_root_dir() -> str:
    return os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def generate_and_save_aura_transaction(
    tokens_gauge_distributions: Dict,
    start_date: datetime,
    end_date: datetime,
    chain_name: str,
    pct_of_distribution: Decimal = Decimal(1),
    num_periods: int = 2,
) -> Dict:
    """
    Take a set of distributions and send them to aura direct
    """
    aura = Aura(chain_name)
    # Dump into output.json using:
    with open(f"{get_root_dir()}/data/aura_direct_stream.json") as f:
        output_data = json.load(f)
    # Find transaction with func name `setRecipientList` and dump gauge
    gauge_distributions = tokens_gauge_distributions.values()
    tx_template = output_data["transactions"][1]
    tx_list = []
    total_amount = 0
    # Inject list of gauges addresses:
    for gauge in gauge_distributions:
        aura_pid = aura.aura_pids_by_address.get(gauge["recipientGaugeAddr"])
        if not aura_pid:
            print(
                f"WARNING: No aura pid found for gauge {gauge['recipientGaugeAddr']}, using gauge address in payload instead for easy debugging."
            )
            aura_pid = gauge["recipientGaugeAddr"]
        tx = copy.deepcopy(tx_template)
        tx["contractInputsValues"]["_pid"] = aura_pid
        amount = (
            Decimal(gauge["distroToAura"]) * Decimal(pct_of_distribution)
        ).quantize(precision, rounding=ROUND_DOWN)
        wei_amount = (amount * Decimal(1e18)).to_integral_value()
        tx["contractInputsValues"]["_amount"] = str(wei_amount)
        tx["contractInputsValues"]["_periods"] = str(num_periods)
        if wei_amount > 0:
            tx_list.append(tx)
            total_amount += wei_amount
    if not tx_list:
        print("No distributions to send to aura direct")
        return
    # Add approve tx
    approve_tx = output_data["transactions"][0]
    approve_tx["contractInputsValues"]["amount"] = str(total_amount)
    tx_list.insert(0, approve_tx)
    output_data["transactions"] = tx_list
    with open(
        f"{get_root_dir()}/output/{FILE_PREFIX}_{start_date.date()}_{end_date.date()}_aura_direct_stream.json",
        "w",
    ) as _f:
        json.dump(output_data, _f, indent=2)
    print(f"{total_amount}({total_amount/Decimal(1e18)}) $ARB approved for aura direct")
    return output_data


def generate_and_save_bal_injector_transaction(
    tokens_gauge_distributions: Dict,
    start_date: datetime,
    end_date: datetime,
    pct_of_distribution: Decimal = Decimal(1),
    num_periods: int = 2,
) -> Dict:
    """
    Take tx template and inject data into it
    """
    # Dump into output.json using:
    with open(f"{get_root_dir()}/data/output_tx_template.json") as f:
        output_data = json.load(f)

    # Find transaction with func name `setRecipientList` and dump gauge
    gauge_distributions = tokens_gauge_distributions.values()
    tx_template = output_data["transactions"][0]
    transfer_tx = output_data["transactions"][1]
    tx_list = []
    gauges_list = []
    amounts_list = []
    max_periods_list = []
    total_amount = 0
    # Inject list of gauges addresses:
    for gauge in gauge_distributions:
        gauges_list.append(gauge["recipientGaugeAddr"])
        epoch_amount = (
            Decimal(gauge["distroToBalancer"]) * Decimal(pct_of_distribution)
        ).quantize(precision, rounding=ROUND_DOWN)
        period_amount = epoch_amount / Decimal(num_periods)
        wei_amount = (period_amount * Decimal(1e18)).to_integral_value()
        total_amount += (epoch_amount * Decimal(1e18)).to_integral_value()
        amounts_list.append(str(wei_amount))
        max_periods_list.append(str(num_periods))
    tx = copy.deepcopy(tx_template)
    tx["contractInputsValues"]["gaugeAddresses"] = f"[{','.join(gauges_list)}]"
    tx["contractInputsValues"]["amountsPerPeriod"] = f"[{','.join(amounts_list)}]"
    tx["contractInputsValues"]["maxPeriods"] = f"[{','.join(max_periods_list)}]"
    tx_list.append(tx)

    # Note we started on an off-week of biweekly claiming so can only transfer 1 week at a time.
    # Another transaction flow is setup to claim/pay in the other half when funds are available.
    transfer_tx["contractInputsValues"]["amount"] = str(int(total_amount) / num_periods)
    tx_list.append(transfer_tx)
    output_data["transactions"] = tx_list
    with open(
        f"{get_root_dir()}/output/{FILE_PREFIX}_{start_date.date()}_{end_date.date()}_bal_injector_stream.json",
        "w",
    ) as _f:
        json.dump(output_data, _f, indent=2)
    print(f"{total_amount} $ARB transferred for balancer injector")
    return output_data
