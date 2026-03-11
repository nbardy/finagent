import json
import argparse
from ib_insync import *

# IBKR currency → price unit mapping.
# Some exchanges quote in subunits (pence, sen) but use the major currency code.
# This table defines the minimum plausible limit price per currency — any price
# below this on a limit order is almost certainly a units mistake.
_CURRENCY_PRICE_FLOOR = {
    'GBP': 1.0,    # LSE/AIM: prices in pence (GBX), not pounds. 1.0 = 1p.
    'JPY': 10.0,   # TSE: prices in yen. Sub-10 yen stocks exist but are rare penny stocks.
}


def assert_price_units(symbol: str, currency: str, price: float, tranche_id=None):
    """Guard against currency/price unit misalignment.

    Raises ValueError if a limit price is below the floor for its currency,
    which almost certainly means the caller used the wrong unit
    (e.g. pounds instead of pence).
    """
    floor = _CURRENCY_PRICE_FLOOR.get(currency)
    if floor is not None and price < floor:
        loc = f" tranche {tranche_id}" if tranche_id else ""
        raise ValueError(
            f"{symbol}{loc}: lmtPrice={price} is below {floor} {currency}. "
            f"Likely a units error — GBP stocks use pence, JPY stocks use yen."
        )


def _apply_order_fields(order, proposal, outside_rth):
    order.outsideRth = outside_rth
    order.tif = proposal.get('tif', getattr(order, 'tif', 'DAY'))
    if 'goodAfterTime' in proposal:
        order.goodAfterTime = proposal['goodAfterTime']
    if 'goodTillDate' in proposal:
        order.goodTillDate = proposal['goodTillDate']
    if 'orderRef' in proposal:
        order.orderRef = proposal['orderRef']
    if proposal.get('overridePercentageConstraints') is True:
        order.overridePercentageConstraints = True
    # IBKR Adaptive algo — works orders intelligently near midprice
    # NOTE: Not supported on OTC/Pink Sheet stocks (Error 442)
    if proposal.get('algo') == 'Adaptive':
        priority = proposal.get('algoPriority', 'Normal')  # Urgent, Normal, Patient
        order.algoStrategy = 'Adaptive'
        order.algoParams = [TagValue('adaptivePriority', priority)]
    return order


def execute_trade(file_path):
    with open('config/pmcc_config.json', 'r') as f:
        config = json.load(f)
        
    conn_cfg = config.get('connection', {})
    host = conn_cfg.get('host', '127.0.0.1')
    port = conn_cfg.get('port', 4001)
    client_id = conn_cfg.get('client_id_executor', 2)
    
    exec_cfg = config.get('execution', {})
    outside_rth = exec_cfg.get('outside_rth', False)

    with open(file_path, 'r') as f:
        data = json.load(f)

    if isinstance(data, dict) and 'trades' in data:
        proposals = data['trades']
    elif isinstance(data, list):
        proposals = data
    else:
        proposals = [data]

    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id) 
        
        for proposal in proposals:
            # Reconstruct contract — dispatch on secType
            c_data = proposal['contract']
            sec_type = c_data.get('secType', 'OPT')

            if sec_type == 'STK':
                contract = Stock(
                    c_data['symbol'],
                    c_data['exchange'],
                    c_data.get('currency', 'USD'),
                )
                ib.qualifyContracts(contract)

            elif sec_type == 'BAG':
                # Combo/spread order — build from legs
                legs = []
                for leg_data in c_data['legs']:
                    leg_contract = Option(
                        c_data['symbol'],
                        leg_data['expiry'],
                        leg_data['strike'],
                        leg_data['right'],
                        c_data['exchange'],
                        currency=c_data.get('currency', 'USD'),
                    )
                    ib.qualifyContracts(leg_contract)
                    leg_action = leg_data['action']
                    combo_leg = ComboLeg(
                        conId=leg_contract.conId,
                        ratio=leg_data.get('ratio', 1),
                        action=leg_action,
                        exchange=c_data['exchange'],
                    )
                    legs.append(combo_leg)
                contract = Contract(
                    symbol=c_data['symbol'],
                    secType='BAG',
                    exchange=c_data['exchange'],
                    currency=c_data.get('currency', 'USD'),
                    comboLegs=legs,
                )

            else:
                contract = Option(
                    c_data['symbol'],
                    c_data['lastTradeDateOrContractMonth'],
                    c_data['strike'],
                    c_data['right'],
                    c_data['exchange'],
                    currency=c_data['currency'],
                )
                ib.qualifyContracts(contract)

            action = proposal['action']
            if sec_type == 'BAG':
                leg_descs = [f"{l['action']} {l['strike']}{l['right']}" for l in c_data['legs']]
                contract_desc = f"{c_data['symbol']} COMBO [{' / '.join(leg_descs)}]"
            else:
                contract_desc = f"{contract.symbol} {getattr(contract, 'strike', '')}{getattr(contract, 'right', '')}".strip()

            if 'tranches' in proposal:
                print(f"Executing tranched order for {contract_desc}")
                for i, t_data in enumerate(proposal['tranches']):
                    qty = t_data['quantity']
                    lmt_price = t_data['lmtPrice']
                    tif = proposal.get('tif', t_data.get('tif', 'DAY'))
                    
                    currency = c_data.get('currency', 'USD')
                    assert_price_units(c_data['symbol'], currency, lmt_price, t_data.get('tranche'))
                    order = LimitOrder(action, qty, lmt_price)
                    t_payload = dict(proposal)
                    t_payload.update(t_data)
                    t_payload['tif'] = tif
                    # Pass note as orderRef so it's visible in TWS/Gateway
                    if 'note' in t_data and 'orderRef' not in t_data:
                        t_payload['orderRef'] = t_data['note'][:40]
                    order = _apply_order_fields(order, t_payload, outside_rth)
                    
                    print(
                        f" Tranche {i+1}: {action} {qty} @ {lmt_price} tif={tif}"
                        f" goodAfterTime={getattr(order, 'goodAfterTime', '') or 'n/a'}"
                    )
                    
                    trade = ib.placeOrder(contract, order)
                    ib.sleep(2) # Give it a moment to transmit
                    print(f"  Status: {trade.orderStatus.status}")
            else:
                qty = proposal.get('quantity', 1)
                order_type = proposal.get('order_type', 'MKT')
                tif = proposal.get('tif', 'DAY')
                if order_type == 'MKT':
                    order = MarketOrder(action, qty)
                    proposal['tif'] = tif
                    order = _apply_order_fields(order, proposal, outside_rth)
                    print(f"Executing {order_type} order for {contract_desc}: {action} {qty} tif={tif}")
                    trade = ib.placeOrder(contract, order)
                    ib.sleep(2)
                    print(f"  Status: {trade.orderStatus.status}")
                elif order_type == 'LMT' and 'lmtPrice' in proposal:
                    lmt_price = proposal['lmtPrice']
                    currency = c_data.get('currency', 'USD')
                    assert_price_units(c_data['symbol'], currency, lmt_price)
                    order = LimitOrder(action, qty, lmt_price)
                    proposal['tif'] = tif
                    order = _apply_order_fields(order, proposal, outside_rth)
                    print(
                        f"Executing {order_type} order for {contract.symbol} {contract.strike}{contract.right}: "
                        f"{action} {qty} @ {lmt_price} tif={tif} "
                        f"goodAfterTime={getattr(order, 'goodAfterTime', '') or 'n/a'}"
                    )
                    trade = ib.placeOrder(contract, order)
                    ib.sleep(2)
                    print(f"  Status: {trade.orderStatus.status}")
                else:
                    print(f"Unsupported order type or missing parameters in proposal for {contract_desc}")

    except Exception as e:
        print(f"Execution Error: {e}")
    finally:
        if ib.isConnected():
            ib.disconnect()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Path to the JSON proposal", default="trade_proposal.json")
    args = parser.parse_args()
    execute_trade(args.file)
