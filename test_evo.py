"""

▉▊▋▌▍▎▏MANIFOLD FINANCE ▎▍▌▋▊▉

EVO Protocol firesale pytest

Manifold Finance

Usage:
    ls test_evo 
    cd ./test && pytest
   evo_trade must be symlinked to ../evo-trade (parent) repository.

"""
from evo_trade.contract import ContractProvider
from evo_trade.simulation import Simulation
from evo_trade.config import get_config


def _fastforward(days=26, minutes=1):
    """Fast forward Ganache time."""
    provider = ContractProvider.get_contract_provider()
    provider.fastforward_time(days=days, minutes=1)


def _bootstrap_sim():
    """Bootstrap basic simulation instance with alphabetic agents."""
    config = get_config("pytest")
    config['num_of_agents'] = 26
    sim = Simulation("pytestsim", config)
    sim.init_agents()
    sim.alice = sim.agents[0]
    sim.bob = sim.agents[1]
    sim.zip = sim.agents[25]
    sim.configure_logs()
    return sim


sim = _bootstrap_sim()


def _get_interest_event(tx_hash):
    provider = ContractProvider.get_contract_provider()
    # Look for events
    tx_receipt = provider.w3.eth.getTransactionReceipt(tx_hash)
    interests = provider.contract.events.InterestOnEvo().processReceipt(tx_receipt)
    assert len(interests) == 1
    return interests[0]["args"]


def test_contract_ping():
    """Ping contract by calling rpc methods."""
    sim.check_contract()


def test_theta():
    """Test the ownership ratio in discounted interest."""
    interests = list()
    small_buy = int(10e18)
    bigger_stake = int(100e18)
    sim.zip.buy(20 * bigger_stake)  # distribute the ownership
    notandre = sim.notandre
    _fastforward(days=26)  # clean tracking

    # sim.notandre.buy(bigger_stake)
    for i in range(20):
        notandre.buy(small_buy)
        interest = notandre._get_interest_percentage(notandre.account, notandre.token_bought)
        interests.append(interest)

    _fastforward()  # + 25 days and let someone else share the rate
    sim.zip.buy(20 * bigger_stake)  # distribute the ownership

    notandre.buy(small_buy)
    interest = notandre._get_interest_percentage(notandre.account, notandre.token_bought)
    interests.append(interest)

    # last small buy has strictly smaller interest due to shared rate
    last_buy = interests.pop(-1)
    assert last_buy < interests[-1]

    # interest gets reduced as theta grows
    for i in range(len(interests) - 1):
        assert interests[i + 1] <= interests[i]


def test_zero_interest():
    """Waiting is the basic interest free strategy."""
    greater_stake = int(100e18)
    notandre = sim.notandre
    zip = sim.zip
    _fastforward(days=26)  # clean tracking

    # There must be a sustainable transfer rate for 25 days
    for d in range(25):
        _fastforward(days=1)
        zip.buy(greater_stake)  # share rate

    zero_part = int(zip.token_bought * 0.02)
    print("============================================")
    print("zip was contentiously buying: %s" % zip.token_bought)
    print("zero-interest part of it is: %s" % zero_part)
    print("============================================")

    pr = sim.market._get_price_range(notandre.account, zero_part, normalized=False)
    eth_amount = int(pr[1])  # pick the max price
    tx_hash = notandre.deposit_eth(eth_amount)
    event_args = _get_interest_event(tx_hash)
    assert event_args['interest'] == 0


def test_market_dump():
    """Every agent sells but notandre keeps the rest."""
    # Note, run this test also on newly deployed contract
    amount = int(4e18)
    notandre = sim.notandre
    _fastforward(days=26)  # clean tracking

    # notandre has invested in Evo..
    notandre.deposit_eth(amount)
    # Then everyone pumps..
    for agent in sim.agents[:24]:
        agent.deposit_eth(amount)
    # before dump
    b = dict()
    b['evo_supply'] = notandre._get_evo_supply()
    b['eth_deposit'] = notandre._get_eth_deposit()
    b['one_evo_price'] = notandre._get_token_price(normalized=False)
    # and dumps, except notandre
    for agent in sim.agents[:24]:
        while agent._get_token_balance(agent.account) / 1e18 > 0.05:
            # Note that some tokens still remains after first withdraw
            agent_tokens = agent._get_token_balance(agent.account)
            agent.withdraw_eth(agent_tokens)
    # after pump'n'dump
    a = dict()
    a['evo_supply'] = notandre._get_evo_supply()
    a['eth_deposit'] = notandre._get_eth_deposit()
    a['one_evo_price'] = notandre._get_token_price(normalized=False)

    assert b['one_evo_price'] < a['one_evo_price']
    assert b['evo_supply'] > a['evo_supply']
    assert b['eth_deposit'] > a['eth_deposit']
    assert b['evo_supply'] < b['eth_deposit']
    assert a['evo_supply'] < a['eth_deposit']
    assert a['eth_deposit'] > amount

    # .. so there should be not more than 24 * 0.05 = 1.2 Evo distributed around
    notandre_tokens = notandre._get_token_balance(notandre.account)
    rest_evo_supply = a['evo_supply'] - notandre_tokens
    rest_evo_supply / 1e18 <= 1.2

    print(("Now notandre has %f Evo and can exchange it for %f ETH "
           "(%f of which was his initial investment).") %
          (notandre_tokens / 1e18, a['eth_deposit'] / 1e18, amount / 1e18))
    print("Evo price is: %f (ETH). ETH deposit was reduced to %f%% after dump." %
          (a['one_evo_price'] / 1e18, a['eth_deposit'] * 100 / b['eth_deposit']))
    # According to the dump-resistance mechanism ..
    assert (a['one_evo_price'] / 1e18) * (a['eth_deposit'] * 100 / b['eth_deposit']) >= 18
