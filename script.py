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
	BUY_STOP_MARKET = 'BUY_STOP_MARKET'
	SELL_STOP_MARKET = 'SELL_STOP_MARKET'
	ALERT = 'ALERT'

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
	text = ['Status:']
	for trade in open_trades.itervalues():
		if not isinstance(trade, dict):
			continue
		pos_str = repr(trade) if use_repr else str(trade)
		text.append(pos_str)
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

	key = str(int(args[0]))

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
		text = ("%f" % price)
	except Exception as e:
		text = 'Got %s: %s at:\n%s' % (type(e), e, traceback.format_exc())

	bot.send_message(chat_id=update.message.chat_id, text=text)

def create_trade(config, args):
	next_id = config['next_id'] if 'next_id' in config else 0

	trade = {
		'id': next_id,
		'pair': [str(args[0]).upper(), str(args[1]).upper()],
		'quantity': float(args[2]),
		'type': str(args[3]).upper(),
		'threshold': float(args[4]),
	}

	config['next_id'] = next_id + 1
	config.sync()
	return trade

def create_alert(config, args):
	next_id = config['next_id'] if 'next_id' in config else 0

	trade = {
		'id': next_id,
		'pair': [str(args[0]).upper(), str(args[1]).upper()],
		'price': float(args[2]),
		'type': TRADE_TYPE.ALERT,

	}

	config['next_id'] = next_id + 1
	config.sync()
	return trade

@requires_lock
def trade_handler(bot, update, args):
	global open_trades, config
	logging.debug("Responding to /trade: args=%r." % args)

	trade = create_trade(config, args)
	open_trades[str(trade['id'])] = trade
	open_trades.sync()

	text = [str(trade), '\nack!']

	bot.send_message(chat_id=update.message.chat_id, text='\n'.join(text))

@requires_lock
def alert_handler(bot, update, args):
	global open_trades, config
	logging.debug("Responding to /alert: args=%r." % args)

	trade = create_alert(config, args)

	client = init_client(config)
	prices = get_prices(client)
	current_price = prices[''.join(trade['pair'])]

	if trade['price'] > current_price:
		trade['pmin'] = trade['price']
	else:
		trade['pmax'] = trade['price']
	del trade['price']


	open_trades[str(trade['id'])] = trade
	open_trades.sync()

	text = [str(trade), '\nack!']

	bot.send_message(chat_id=update.message.chat_id, text='\n'.join(text))

def help_handler(bot, update):
	logging.debug("Responding to /help.")
	bot.send_message(chat_id=update.message.chat_id, text="""/start <API_KEY> <SECRET>
/trade <COIN> <MARKET> <QUANTITY> <TYPE> [PRICE?]
/trade LTC BTC 1 BUY_STOP_MARKET 0.22
/trade LTC BTC 1 SELL_STOP_MARKET 0.24
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
	relevant_keys = set([x['pair'][0] for x in open_trades.itervalues() if isinstance(x, dict)])
	balances = {x:y for x,y in balances.iteritems() if x in relevant_keys}
	return balances

def notify_user_callback(bot, job):
	context = job.context
	chat_id = context['chat_id']
	text = context['text']
	bot.send_message(chat_id=chat_id, text=text)

def format_prices(prices):
	return '\n'.join(['%s: %f' % x for x in prices.iteritems()])

def format_balances(balances):
	return '\n'.join(['%s: %f' % (x, y['free'] + y['locked']) for x, y in balances.iteritems()])

class LoopRunner(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self)
		self.shutdown_event = threading.Event()
		self.last_run = None

	def run(self):
		global open_trades, config
		client = init_client(config)
		sleep_time = kRunInterval
		while not self.shutdown_event.is_set():
			logging.debug('loop')
			try:
				self._run_loop(open_trades, client)
				sleep_time = kRunInterval
			except Exception as e:
				if isinstance(e, BinanceAPIException) and e.code == -1000:
					msg = e.message
				else:
					msg = 'Got %s: %s at:\n%s' % (type(e), e, traceback.format_exc())
				logging.error(msg)
				notify_user(msg)
				sleep_time *= 2
				if sleep_time > kMaxRunInterval:
					sleep_time = kMaxRunInterval
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
				if trade['type'] == TRADE_TYPE.ALERT:
					if 'pmin' in trade:
						if current_price > trade['pmin']:
							notify_user('Alert %s is at %s.' % ('/'.join(trade['pair']), current_price))
							deletes.append(key)
					elif 'pmax' in trade:
						if current_price < trade['pmax']:
							notify_user('Alert %s is at %s.' % ('/'.join(trade['pair']), current_price))
							deletes.append(key)
					else:
						notify_user("Urecognized alert: %s" % trade)

				elif trade['type'] == TRADE_TYPE.BUY_STOP_MARKET:
					if recent_price < trade['threshold']:
						notify_user('Buying %s of %s at %s.' % (trade['quantity'], '/'.join(trade['pair']), current_price))
						deletes.append(key)
				elif trade['type'] == TRADE_TYPE.SELL_STOP_MARKET:
					if recent_price > trade['threshold']:
						notify_user('Selling %s of %s at %s.' % (trade['quantity'], '/'.join(trade['pair']), current_price))
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

