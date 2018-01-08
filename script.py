#!/usr/bin/env python2.7

import requests
from functools import wraps
import traceback
import logging
import shelve
from collections import namedtuple
import yaml
import json
import threading
import time
import datetime

import telegram
from telegram.ext import Updater
from telegram.ext import MessageHandler, Filters
from telegram.ext import CommandHandler
from telegram.error import (TelegramError, Unauthorized, BadRequest, 
														TimedOut, ChatMigrated, NetworkError)

from binance.client import Client
from binance.exceptions import BinanceAPIException

kRunInterval = 10
kMaxRunInterval = 60

glb_lock = threading.Lock()


def requires_lock(func):
	@wraps(func)
	def wrapped(bot, update, *args, **kwargs):
		global glb_lock
		with glb_lock:
			return func(bot, update, *args, **kwargs)
	return wrapped

#		return json.dumps(self.record)
#		return yaml.dump(self.record, default_flow_style=False)


class TRADE_TYPE:
	BUY_BELOW_AT_MARKET = 'BUY_BELOW_AT_MARKET'
	SELL_ABOVE_AT_MARKET = 'SELL_ABOVE_AT_MARKET'
	SELL_BELOW_AT_MARKET = 'SELL_BELOW_AT_MARKET'
	ALERT_ABOVE = 'ALERT_ABOVE'
	ALERT_BELOW = 'ALERT_BELOW'

open_trades = None
config = None
updater = None
loop_runner = None
client = None
def init_client(config):
	global client
	if client is None:
		client = Client(config['api_key'], config['secret'])
	return client

@requires_lock
def start_handler(bot, update, args):
	global config
	logging.debug("Responding to /start: %s" % args)
	if len(args) != 2:
		text = 'Wrong Usage'
		bot.send_message(chat_id=update.message.chat_id, text=text)
		return

	config['chat_id'] = update.message.chat_id
	config['api_key'] = str(args[0])
	config['secret'] = str(args[1])
	config.sync()

	bot.send_message(chat_id=update.message.chat_id, text="ack!")

def build_status_msg(open_trades, prices, balances, use_repr=False):
	text = ['Status:', format_trades(open_trades.itervalues(), use_repr, prices)]
	text.append('\nPrices:\n%s' % format_prices(prices))
	text.append('\nBalances:\n%s' % format_balances(balances))

	return '\n'.join(text)

@requires_lock
def status_handler(bot, update, args):
	global open_trades, config
	logging.debug("Responding to /status: %s." % args)
	client = init_client(config)
	use_repr = (len(args) and args[0] == 'repr')
	text = build_status_msg(open_trades, get_prices(client, open_trades), get_balances(open_trades, client), use_repr=use_repr)
	bot.send_message(chat_id=update.message.chat_id, text=text)

def ping_handler(bot, update):
	global loop_runner
	logging.debug("Responding to /ping.")

	if loop_runner.last_run is None:
		text = "Oh noes :("
	else:
		time_since_run = (datetime.datetime.now() - loop_runner.last_run).total_seconds()
		if time_since_run < 2 * kRunInterval:
			text = "OK!"
		else:
			text = "Something is wrong ..."
	bot.send_message(chat_id=update.message.chat_id, text=text)

@requires_lock
def remove_handler(bot, update, args):
	global open_trades
	logging.debug("Responding to /remove: args=%r." % args)
	text = []

	for arg in args:
		key = str(int(arg))

		if key in open_trades:
			text.append('Trade removed: %s' % open_trades[key])
			del open_trades[key]
		else:
			text.append('key %r not found!' % key)

	bot.send_message(chat_id=update.message.chat_id, text='\n\n'.join(text))

def price_handler(bot, update, args):
	logging.debug("Responding to /price: args=%r." % args)
	text = ""

	try:
		client = init_client(config)
		price = get_price(args[0], args[1], client)
		text =  format_scientific(price)
	except Exception as e:
		text = 'Got %s: %s at:\n%s' % (type(e), e, traceback.format_exc())

	bot.send_message(chat_id=update.message.chat_id, text=text)

def create_trades(config, args):
	pair = (str(args[0]).upper(), str(args[1]).upper())
	trades = []
	for i in xrange(2, len(args), 3):
		next_id = config['next_id'] if 'next_id' in config else 0
		trade = {
			'id': next_id,
			'pair': list(pair),
			'quantity': float(args[i]),
			'type': str(args[i+1]).upper(),
			'threshold': float(args[i+2]),
		}
		trades.append(trade)
		config['next_id'] = next_id + 1
	config.sync()
	return trades

def create_alert(config, args):
	next_id = config['next_id'] if 'next_id' in config else 0

	trade = {
		'id': next_id,
		'pair': [str(args[0]).upper(), str(args[1]).upper()],
		'threshold': float(args[2]),
	}

	config['next_id'] = next_id + 1
	config.sync()
	return trade

@requires_lock
def trade_handler(bot, update, args):
	global open_trades, config
	logging.debug("Responding to /trade: args=%r." % args)

	trades = create_trades(config, args)
	for trade in trades:
		open_trades[str(trade['id'])] = trade
	open_trades.sync()

	text = [str(trades), '\nack!']

	bot.send_message(chat_id=update.message.chat_id, text='\n'.join(text))

@requires_lock
def alert_handler(bot, update, args):
	global open_trades, config
	logging.debug("Responding to /alert: args=%r." % args)

	trade = create_alert(config, args)

	client = init_client(config)
	prices = get_prices(client)
	current_price = prices[''.join(trade['pair'])]

	if trade['threshold'] > current_price:
		trade['type'] = TRADE_TYPE.ALERT_ABOVE
	else:
		trade['type'] = TRADE_TYPE.ALERT_BELOW


	open_trades[str(trade['id'])] = trade
	open_trades.sync()

	text = [str(trade), '\nack!']

	bot.send_message(chat_id=update.message.chat_id, text='\n'.join(text))

def help_handler(bot, update):
	logging.debug("Responding to /help.")
	bot.send_message(chat_id=update.message.chat_id, text="""/start <API_KEY> <SECRET>
/trade <COIN> <MARKET> <QUANTITY> <TYPE> [PRICE?]
/trade LTC BTC 1 BUY_BELOW_AT_MARKET 0.22 # Buy Zone
/trade LTC BTC 1 SELL_ABOVE_AT_MARKET 0.24 # Profit
/trade LTC BTC 1 SELL_BELOW_AT_MARKET 0.2 # Stop loss
/price LTC BTC
/alert LTC BTC 0.23
/status - get current status of open trades.
/remove <TRADE_ID>
""")


logging.basicConfig(filename='log.txt', format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)

#bot = telegram.Bot(token='483544796:AAHuhbEYsLWZJ5EdbzXDfwJM4ZvpE1N2J50')
#print(bot.get_me())

with open('telegram.bot.token') as f:
	updater = Updater(token=f.read().strip())
dispatcher = updater.dispatcher

dispatcher.add_handler(CommandHandler('start', start_handler, pass_args=True))
dispatcher.add_handler(CommandHandler('trade', trade_handler, pass_args=True))
dispatcher.add_handler(CommandHandler('alert', alert_handler, pass_args=True))
dispatcher.add_handler(CommandHandler('price', price_handler, pass_args=True))
dispatcher.add_handler(CommandHandler('remove', remove_handler, pass_args=True))
dispatcher.add_handler(CommandHandler('status', status_handler, pass_args=True))
dispatcher.add_handler(CommandHandler('ping', ping_handler))
dispatcher.add_handler(CommandHandler('help', help_handler))


def error_callback(bot, update, error):
		logging.debug("Got error: %s %s", type(error), error)
		try:
				raise error
		except Unauthorized:
				# remove update.message.chat_id from conversation list
				pass
		except BadRequest:
				# handle malformed requests - read more below!
				pass
		except TimedOut:
				# handle slow connection problems
				pass
		except NetworkError:
				# handle other connection problems
				pass
		except ChatMigrated as e:
				# the chat_id of a group has changed, use e.new_chat_id instead
				pass
		except TelegramError:
				# handle all other telegram related errors
				pass

dispatcher.add_error_handler(error_callback)

def start():
	global q, open_trades, config, loop_runner
	if loop_runner is not None:
		stop()
	q = updater.start_polling()
	open_trades = shelve.open('data/open_trades.shelve')
	config = shelve.open('data/config.shelve')
	print q
	loop_runner = LoopRunner()
	loop_runner.start()
	logging.info("Up!")

def stop():
	global open_trades, config, updater, loop_runner
	updater.stop()
	loop_runner.shutdown_event.set()
	logging.debug('Waiting for loop thread shutdown...')
	loop_runner.join()
	open_trades.close()
	config.close()
	logging.info("Down!")
	loop_runner = None

#start()

def notify_user(text, when=0):
	global updater
	updater.job_queue.run_once(notify_user_callback, when, {'chat_id': config['chat_id'], 'text': text})

def get_prices(client, open_trades=None):
	prices = {x['symbol']: float(x['price']) for x in client.get_all_tickers()}
	if open_trades:
		relevant_keys = set([("%s%s" % (trade['pair'][0], trade['pair'][1])) for trade in open_trades.itervalues() if isinstance(trade, dict)])
		prices = {x:y for x,y in prices.iteritems() if x in relevant_keys}
	return prices

def get_balances(open_trades, client):
	account_info = client.get_account()
	balances = {x['asset']: {'free': float(x['free']), 'locked': float(x['locked'])} for x in account_info['balances']}
	relevant_keys = [x['pair'] for x in open_trades.itervalues() if isinstance(x, dict)]
	relevant_keys = set([symbol for pair in relevant_keys for symbol in pair])
	balances = {x:y for x,y in balances.iteritems() if x in relevant_keys}
	return balances

def notify_user_callback(bot, job):
	context = job.context
	chat_id = context['chat_id']
	text = context['text']
	bot.send_message(chat_id=chat_id, text=text)


def find_exp(value):
	if value >= 1e9:
		return 9
	elif value >= 1e6:
		return 6
	elif value >= 1e3:
		return 3
	elif value >= 1e0:
		return 0
	elif value >= 1e-3:
		return -3
	elif value >= 1e-6:
		return -6
	elif value >= 1e-9:
		return -9
	return 0

def format_scientific(value, exp=None):
	if value == 0:
		return 0
	if exp is None:
		exp = find_exp(value)
	if exp == 0:
		return "%.2f" % value
	return "%.2fe%d" % (value / 10**exp, exp)

def format_prices(prices):
	return '\n'.join(['%s: %s' % (x[0], format_scientific(x[1])) for x in prices.iteritems()])

def format_balances(balances):
	return '\n'.join(['%s: %s' % (x, format_scientific(y['free'] + y['locked'])) for x, y in balances.iteritems()])

def format_trades(trades, use_repr, prices):
	trades = sorted(trades, key=lambda trade: (trade['pair'][0], trade['pair'][1], trade['threshold']))
	last_pair = ""
	lines = []
	for trade in trades:
		if use_repr:
			lines.append(repr(trade))
			continue
		pair = "%s%s" % (trade['pair'][0], trade['pair'][1])
		if pair != last_pair:
			last_pair = pair
			lines.append("%s:" % pair)
		exp = find_exp(prices[pair])
		if trade['type'] == TRADE_TYPE.ALERT_BELOW or trade['type'] == TRADE_TYPE.ALERT_ABOVE:
			lines.append("%s %s (id=%d)" % (format_scientific(trade['threshold'], exp), trade['type'], trade['id']))
		else:
			lines.append("%s %s %s (id=%d)" % (format_scientific(trade['threshold'], exp), trade['type'], trade['quantity'], trade['id']))
	return '\n'.join(lines)

class LoopRunner(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self)
		self.shutdown_event = threading.Event()
		self.last_run = None
		self._last_run_error = False


	def run(self):
		global open_trades, config
		client = init_client(config)
		sleep_time = kRunInterval
		while not self.shutdown_event.is_set():
			logging.debug('loop')
			try:
				self._run_loop(open_trades, client)
				sleep_time = kRunInterval
				if self._last_run_error:
					self._last_run_error = False
					notify_user("Completed successful run.")
			except Exception as e:
				self._last_run_error = True
				if isinstance(e, BinanceAPIException) and e.code == -1000:
					error_str = e.message
				elif isinstance(e, requests.exceptions.ReadTimeout):
					error_str = e.message
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

	def _run_loop(self, open_trades, client):
		with glb_lock:
			self.last_run = datetime.datetime.now()
			balances = get_balances(open_trades, client)
			prices = get_prices(client, open_trades)
			server_time = client.get_server_time()['serverTime']

			deletes = []
			for key, trade in open_trades.iteritems():
				if not isinstance(trade, dict):
					continue
				current_price = prices[''.join(trade['pair'])]
				recent_price = get_recent_price(trade['pair'], server_time, client) or current_price
#				balance = balances[trade['pair'][0]]
#				viable_q = min(balance, trade['quantity'])
				if trade['type'] == TRADE_TYPE.ALERT_ABOVE:
						if current_price > trade['threshold']:
							notify_user('Alert %s is above %s at %s.' % ('/'.join(trade['pair']), trade['threshold'], current_price))
							deletes.append(key)
				elif trade['type'] == TRADE_TYPE.ALERT_BELOW:
						if current_price < trade['threshold']:
							notify_user('Alert %s is below %s at %s.' % ('/'.join(trade['pair']), trade['threshold'], current_price))
							deletes.append(key)
				elif trade['type'] == TRADE_TYPE.BUY_BELOW_AT_MARKET:
					if recent_price < trade['threshold']:
						notify_user('Buying %s of %s at %s, price is below %s.' % (trade['quantity'], '/'.join(trade['pair']), current_price, trade['threshold']))
						deletes.append(key)
				elif trade['type'] == TRADE_TYPE.SELL_ABOVE_AT_MARKET:
					if recent_price > trade['threshold']:
						notify_user('Selling %s of %s at %s, price is above %s.' % (trade['quantity'], '/'.join(trade['pair']), current_price, trade['threshold']))
						deletes.append(key)
				elif trade['type'] == TRADE_TYPE.SELL_BELOW_AT_MARKET:
					if recent_price < trade['threshold']:
						notify_user('Selling %s of %s at %s, price is below %s.' % (trade['quantity'], '/'.join(trade['pair']), current_price, trade['threshold']))
						deletes.append(key)
				else:
					notify_user("Urecognized trade type: %s" % trade['type'])

			for key in deletes:
				del open_trades[key]
			open_trades.sync()

def cryptocompare_get_price(fsym, tsym, e):
	params = {
		'fsym': fsym,
		'tsyms': tsym,
		'e': e,
	}
	r = requests.get('https://min-api.cryptocompare.com/data/price', params=params)
	if r.status_code != 200:
		raise Exception('Invalid status code: %s' % r.status_code)
	j = r.json()
	if 'Response' in j and j['Response'] == 'Error':
		raise Exception('Error: %s' % j['Message'])
	return r.json()[tsym]

def get_price(fsym, tsym, client):
	global config

	if tsym == 'USD':
		current_price = cryptocompare_get_price(fsym, tsym, 'Coinbase')
	else:
		prices = get_prices(client)
		current_price = prices["%s%s" % (fsym, tsym)]
	return current_price

def get_recent_price(pair, server_time, client):
	symbol = ''.join(pair)
	start_time = server_time - 2 * kRunInterval * 1000
	end_time = server_time
	trades = client.get_aggregate_trades(symbol=symbol, startTime=start_time, endTime=end_time)
	if len(trades) == 0:
#		logging.debug('No trades for %s', pair)
		return None
	recent_price = max([float(trade['p']) for trade in trades])
#	logging.debug('Recent price for %s is %s', pair, recent_price)
	return recent_price

