from binance.client import Client as _Client
#from binance.exceptions import BinanceAPIException

class BinanceClient(object):
	def __init__(self, api_key, api_secret):
		self._c = _Client(api_key, api_secret)

	def get_symbol_info(self, pair):
		info = self._c.get_symbol_info(''.join(pair))
		info['filters'] = {x['filterType']: x for x in info['filters']}
		return info

	def get_balances(self, symbols):
		"""
		symbols: set of symbols to get balances for, e.g. {'BTC', 'LTC'}.
		"""
		account_info = self._c.get_account()
		return {x['asset']: {'free': float(x['free']), 'locked': float(x['locked'])} for x in account_info['balances'] if x['asset'] in symbols}

	def get_prices(self, pairs):
		"""
		pairs: list of pairs to get balances for, e.g. (('LTC', 'BTC'), ('BTC', 'USDT')).
		"""
		pairs = set([pair[0] + pair[1] for pair in pairs])
		return {x['symbol']: float(x['price']) for x in self._c.get_all_tickers() if x['symbol'] in pairs}

	def get_server_time(self):
		return self._c.get_server_time()['serverTime']

	def get_recent_price(self, pair, server_time, window):
		symbol = pair[0] + pair[1]
		start_time = server_time - window * 1000
		end_time = server_time
		trades = self._c.get_aggregate_trades(symbol=symbol, startTime=start_time, endTime=end_time)
		if len(trades) == 0:
	#		logging.debug('No trades for %s', pair)
			return None
		recent_price = max([float(trade['p']) for trade in trades])
	#	logging.debug('Recent price for %s is %s', pair, recent_price)
		return recent_price

	def create_test_order(self, pair, side, type, quantity):
		return self._c.create_test_order(
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
