from binance.client import Client as _Client
import math
from numpy import median

class BinanceClient(_Client):
	def __init__(self, api_key, api_secret):
		_Client.__init__(self, api_key, api_secret)

	def get_symbol_info(self, pair):
		info = _Client.get_symbol_info(self, ''.join(pair))
		info['filters'] = {x['filterType']: x for x in info['filters']}
		return info

	def get_balances(self, symbols):
		"""
		symbols: set of symbols to get balances for, e.g. {'BTC', 'LTC'}.
		"""
		account_info = _Client.get_account(self)
		return {x['asset']: {'free': float(x['free']), 'locked': float(x['locked'])} for x in account_info['balances'] if x['asset'] in symbols}

	def get_prices(self, pairs=None):
		"""
		pairs: list of pairs to get balances for, e.g. (('LTC', 'BTC'), ('BTC', 'USDT')).
		"""
		prices = {x['symbol']: float(x['price']) for x in self.get_all_tickers() if x['symbol']}
		if pairs:
			pairs = set([pair[0] + pair[1] for pair in pairs])
			prices = {x: y for x, y in prices.iteritems() if x in pairs}
		return prices

	def get_server_time(self):
		return _Client.get_server_time(self)['serverTime']

	def get_recent_price(self, pair, server_time, window, do_max=True, filter_threshold=1.0):
		# TODO: move filtering to util function, not part of binance API
		symbol = pair[0] + pair[1]
		start_time = server_time - window * 1000
		end_time = server_time
		trades = self.get_aggregate_trades(symbol=symbol, startTime=start_time, endTime=end_time)
		if len(trades) == 0:
	#		logging.debug('No trades for %s', pair)
			return None
		prices = [float(trade['p']) for trade in trades]
		# Filter out outliers
		if filter_threshold < 1.0:
			prices = filter_prices(prices, filter_threshold)
		if do_max:
			recent_price = max(prices)
		else:
			recent_price = min(prices)

	#	logging.debug('Recent price for %s is %s', pair, recent_price)
		return recent_price

	def create_order(self, pair, side, type, quantity):
		return _Client.create_order(
			self,
			symbol=pair[0] + pair[1],
			side=side,
			type=type,
			quantity=quantity)

	def create_test_order(self, pair, side, type, quantity):
		return _Client.create_test_order(
			self,
			symbol=pair[0] + pair[1],
			side=side,
			type=type,
			quantity=quantity)

	@staticmethod
	def get_min_lot_size(symbol_info):
		return float(symbol_info['filters']['LOT_SIZE']['minQty'])
	@staticmethod
	def get_max_lot_size(symbol_info):
		return float(symbol_info['filters']['LOT_SIZE']['maxQty'])
	@staticmethod
	def get_lot_size_step(symbol_info):
		return float(symbol_info['filters']['LOT_SIZE']['stepSize'])
	@staticmethod
	def get_max_price(symbol_info):
		return float(symbol_info['filters']['PRICE_FILTER']['maxPrice'])
	@staticmethod
	def get_min_price(symbol_info):
		return float(symbol_info['filters']['PRICE_FILTER']['minPrice'])
	@staticmethod
	def get_price_step(symbol_info):
		return float(symbol_info['filters']['PRICE_FILTER']['tickSize'])

def filter_prices(prices, threshold):
	""" Keep threshold percent of the prices based on distance from the median.
	"""
	m = median(prices)
	num_keep = int(math.ceil(threshold * len(prices)))
	return sorted(prices, key=lambda price: abs(price - m))[:num_keep]

