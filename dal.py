
import shelve as _shelve
from binance_util import BinanceClient
from constants import TRADE_TYPE
#from binance.exceptions import BinanceAPIException


config = _shelve.open('data/config.shelve')

trades_db = _shelve.open('data/open_trades.shelve')

def get_flat_symbols(trades_db):
	pairs = [x['pair'] for x in trades_db.itervalues()]
	return set([symbol for pair in pairs for symbol in pair])

def create_trade(client, pair, quantity, type, threshold):
	# Create test order to make sure it passes sanity checks

	if type not in TRADE_TYPE.ALL:
		raise Exception('Invalid type: %s' % type)
	client.create_test_order(
		pair=pair,
		side=BinanceClient.SIDE_BUY,
		type=BinanceClient.ORDER_TYPE_MARKET,
		quantity=quantity)

	trade = {
		'pair': pair,
		'quantity': quantity,
		'type': type,
		'threshold': threshold,
	}

	if type == TRADE_TYPE.TRAILING_STOP_LOSS:
		trade['delta'] = threshold
		trade['threshold'] = client.get_prices((pair,))[pair[0] + pair[1]] * (1 - threshold)

	return trade

def save_trades(trades):
	for trade in trades:
		next_id = config['next_id'] if 'next_id' in config else 0
		trade['id'] = next_id

		trades_db[str(next_id)] = trade
		config['next_id'] = next_id + 1

	trades_db.sync()
	config.sync()

def create_alert(client, pair, threshold):
	prices = client.get_prices((pair,))
	current_price = prices[pair[0] + pair[1]]

	alert = {
		'pair': pair,
		'threshold': threshold,
	}

	if threshold > current_price:
		alert['type'] = TRADE_TYPE.ALERT_ABOVE
	else:
		alert['type'] = TRADE_TYPE.ALERT_BELOW

	return alert


def save_alert(alert):
	return save_trades([alert])

def find_trades_by_pair(pair_str):
	trade_ids = set()
	for key, trade in trades_db.iteritems():
		if ("%s%s" % trade['pair']) == pair_str:
			trade_ids.add(key)
	return trade_ids

