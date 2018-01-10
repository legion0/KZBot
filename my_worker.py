import logging
import threading
import datetime

from binance_util import BinanceClient
from dal import config, trades_db, get_flat_symbols
from constants import kRunInterval, kMaxRunInterval
from telegram_util import notify_user
from threading_util import requires_lock

from binance.exceptions import BinanceAPIException
from requests.exceptions import ReadTimeout

import traceback

from format import format_scientific, find_exp

from constants import TRADE_TYPE

class MyWorker(object):
	def __init__(self, client):
		self._thread = threading.Thread(target=self._run)
		self._c = client
		self.shutdown_event = threading.Event()
		self.last_run = None
		self._last_run_error = False

	def start(self):
		self.last_run = None
		self._last_run_error = False
		self.shutdown_event.clear()
		self._thread = threading.Thread(target=self._run)
		self._thread.start()

	def stop(self):
		self.shutdown_event.set()
		self._thread.join()

	def _run(self):
		notify_user("Up!")
		sleep_time = kRunInterval
		while not self.shutdown_event.is_set():
			logging.debug('loop')
			try:
				self._run_loop()
				sleep_time = kRunInterval
				if self._last_run_error:
					self._last_run_error = False
					notify_user("Completed successful run.")
			except Exception as e:
				self._last_run_error = True
				if isinstance(e, BinanceAPIException) and e.code == -1000:
					error_str = str(e.message)
				elif isinstance(e, ReadTimeout):
					error_str = str(e.message)
				else:
					error_str = 'Got %s: %s at:\n%s' % (type(e), e, traceback.format_exc())
				logging.error(error_str)
				sleep_time *= 2
				if sleep_time > kMaxRunInterval:
					sleep_time = kMaxRunInterval
				error_str += ('\n\nsleep_time: %s' % sleep_time)
				notify_user(error_str)
			finally:
				self.shutdown_event.wait(sleep_time)

	@requires_lock
	def _run_loop(self):
		self.last_run = datetime.datetime.now()
		balances = self._c.get_balances(get_flat_symbols(trades_db))
		prices = self._c.get_prices([trade['pair'] for trade in trades_db.itervalues()])
		server_time = self._c.get_server_time()

		deletes = []
		for key, trade in trades_db.iteritems():
			if not isinstance(trade, dict):
				continue
			pair_str = '/'.join(trade['pair'])
			pair_key = ''.join(trade['pair'])
			current_price = prices[pair_key]
			recent_price = self._c.get_recent_price(trade['pair'], server_time, 2 * kRunInterval) or current_price
			exp = find_exp(recent_price)
			balance = balances[trade['pair'][0]]
			symbol_info = self._c.get_symbol_info(trade['pair'])
			min_q = self._c.get_min_lot_size(symbol_info)
			#viable_q = min(min_q, trade['quantity'])
			viable_q = min(balance['free'], trade['quantity'])
			if trade['type'] == TRADE_TYPE.ALERT_ABOVE:
					if current_price > trade['threshold']:
						notify_user('Alert %s is above %s at %s.' % (pair_str, trade['threshold'], format_scientific(trade['threshold'], exp)))
						deletes.append(key)
			elif trade['type'] == TRADE_TYPE.ALERT_BELOW:
					if current_price < trade['threshold']:
						notify_user('Alert %s is below %s at %s.' % (pair_str, trade['threshold'], format_scientific(trade['threshold'], exp)))
						deletes.append(key)
			elif trade['type'] == TRADE_TYPE.BUY_BELOW_AT_MARKET:
				if recent_price < trade['threshold']:
					notify_user('Buying %s of %s at %s, price is below %s.' % (trade['quantity'], pair_str, format_scientific(current_price, exp), format_scientific(trade['threshold'], exp)))
#order = client.order_market_buy(
#		symbol='BNBBTC',
#		quantity=100)
#
#order = client.order_market_sell(
#		symbol='BNBBTC',
#		quantity=100)
					order = self._c.create_order(
						pair=trade['pair'],
						side=BinanceClient.SIDE_BUY,
						type=BinanceClient.ORDER_TYPE_MARKET,
						quantity=trade['quantity'])
					deletes.append(key)
					notify_user('done!')
			elif trade['type'] == TRADE_TYPE.SELL_ABOVE_AT_MARKET:
				if recent_price > trade['threshold'] and viable_q > min_q:
					notify_user('Selling %s of %s at %s, price is above %s.' % (viable_q, pair_str, format_scientific(current_price, exp), format_scientific(trade['threshold'], exp)))
					order = self._c.create_order(
						pair=trade['pair'],
						side=BinanceClient.SIDE_SELL,
						type=BinanceClient.ORDER_TYPE_MARKET,
						quantity=viable_q)
					deletes.append(key)
					notify_user('done!')
			elif trade['type'] == TRADE_TYPE.SELL_BELOW_AT_MARKET:
				if recent_price < trade['threshold'] and viable_q > min_q:
					notify_user('Selling %s of %s at %s, price is below %s.' % (viable_q, pair_str, format_scientific(current_price, exp), format_scientific(trade['threshold'], exp)))
					order = self._c.create_order(
						pair=trade['pair'],
						side=BinanceClient.SIDE_SELL,
						type=BinanceClient.ORDER_TYPE_MARKET,
						quantity=viable_q)
					deletes.append(key)
					notify_user('done!')
			else:
				notify_user("Urecognized trade type: %s" % trade['type'])

		for key in deletes:
			del trades_db[key]
		trades_db.sync()

_glb_instance = None

def get_instance():
	global _glb_instance
	if _glb_instance is not None:
		return _glb_instance

	if 'api_key' not in config:
		raise Exception('can\'t find api key')

	client = BinanceClient(config['api_key'], config['secret'])
	_glb_instance = MyWorker(client)
	return _glb_instance

