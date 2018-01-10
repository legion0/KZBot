
import datetime
import dal
import logging

from telegram.ext import CommandHandler
from telegram.error import (TelegramError, Unauthorized, BadRequest, TimedOut, ChatMigrated, NetworkError)

from constants import kRunInterval
from threading_util import requires_lock
from telegram_util import bot_msg_exception
from dal import config, trades_db, get_flat_symbols, find_trades_by_pair
from format import build_status_msg, format_scientific, format_trades
from binance_util import BinanceClient
from my_worker import get_instance as get_worker
import cryptocompare_util as cryptocompare

_USAGE = """
/trade <COIN> <MARKET> <QUANTITY> <TYPE> <THRESHOLD>
/trade LTC BTC 1 BUY_BELOW_AT_MARKET 0.22 # Buy Zone
1 SELL_ABOVE_AT_MARKET 0.24 # Profit
1 SELL_BELOW_AT_MARKET 0.2 # Stop loss
/price LTC BTC
/alert LTC BTC 0.23
/status - get current status of open trades.
/remove <TRADE_ID>
"""

@requires_lock
@bot_msg_exception
def start_handler(bot, update, args):
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

@requires_lock
@bot_msg_exception
def status_handler(bot, update, args):
	logging.debug("Responding to /status: %s." % args)
	client = BinanceClient(config['api_key'], config['secret'])
	use_repr = (len(args) and args[0] == 'repr')

	balances = client.get_balances(get_flat_symbols(trades_db))
	prices = client.get_prices([trade['pair'] for trade in trades_db.itervalues()])
	text = build_status_msg(trades_db, prices, balances, use_repr=use_repr)
	bot.send_message(chat_id=update.message.chat_id, text=text)

@requires_lock
@bot_msg_exception
def ping_handler(bot, update):
	logging.debug("Responding to /ping.")

	time_since_run = (datetime.datetime.now() - get_worker().last_run).total_seconds()
	if time_since_run < 2 * kRunInterval:
		text = "OK!"
	else:
		text = "Something is wrong ..."
	bot.send_message(chat_id=update.message.chat_id, text=text)

@requires_lock
@bot_msg_exception
def remove_handler(bot, update, args):
	logging.debug("Responding to /remove: args=%r." % args)
	text = []

	for arg in args:
		try:
			arg = str(int(arg))
		except ValueError:
			arg = str(arg).upper()

		if arg in trades_db:
			key = arg
			text.append('Trade removed: %s' % trades_db[key])
			del trades_db[key]
			continue
		keys = find_trades_by_pair(arg)
		if len(keys):
			for key in keys:
				text.append('Trade removed: %s' % trades_db[key])
				del trades_db[key]
			continue
		text.append('key %r not found!' % arg)

	trades_db.sync()

	bot.send_message(chat_id=update.message.chat_id, text='\n\n'.join(text))

@requires_lock
@bot_msg_exception
def price_handler(bot, update, args):
	logging.debug("Responding to /price: args=%r." % args)
	pair = (str(args[0]).upper(), str(args[1]).upper())

	client = BinanceClient(config['api_key'], config['secret'])
	prices = client.get_prices((pair,))
	current_price = prices[pair[0] + pair[1]]
	text =	format_scientific(current_price)
	bot.send_message(chat_id=update.message.chat_id, text=text)

#def get_price(fsym, tsym, client):
#	if tsym == 'USD':
#		current_price = cryptocompare.get_price(fsym, tsym, 'Coinbase')
#	else:
#		prices = client.get_prices(((fsym, tsym),))
#		current_price = prices[fsym + tsym]
#	return current_price

@requires_lock
@bot_msg_exception
def trade_handler(bot, update, args):
	global open_trades, config
	logging.debug("Responding to /trade: args=%r." % args)
	client = BinanceClient(config['api_key'], config['secret'])

	trades = create_trades(client, args)
	dal.save_trades(trades)
	prices = client.get_prices((trades[0]['pair'],))
	
	text = [format_trades(trades, True, prices), '\nack!']

	bot.send_message(chat_id=update.message.chat_id, text='\n'.join(text))

@requires_lock
@bot_msg_exception
def alert_handler(bot, update, args):
	global open_trades, config
	logging.debug("Responding to /alert: args=%r." % args)

	client = BinanceClient(config['api_key'], config['secret'])
	alert = create_alert(client, args)

	dal.save_alert(alert)

	text = [str(trade), '\nack!']

	bot.send_message(chat_id=update.message.chat_id, text='\n'.join(text))

@bot_msg_exception
def help_handler(bot, update):
	logging.debug("Responding to /help.")
	bot.send_message(chat_id=update.message.chat_id, text=_USAGE.strip())

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

def register_handlers(dispatcher):
	dispatcher.add_handler(CommandHandler('start', start_handler, pass_args=True))
	dispatcher.add_handler(CommandHandler('trade', trade_handler, pass_args=True))
	dispatcher.add_handler(CommandHandler('alert', alert_handler, pass_args=True))
	dispatcher.add_handler(CommandHandler('price', price_handler, pass_args=True))
	dispatcher.add_handler(CommandHandler('remove', remove_handler, pass_args=True))
	dispatcher.add_handler(CommandHandler('status', status_handler, pass_args=True))
	dispatcher.add_handler(CommandHandler('ping', ping_handler))
	dispatcher.add_handler(CommandHandler('help', help_handler))
	dispatcher.add_error_handler(error_callback)

def create_trades(client, args):
	pair = (str(args[0]).upper(), str(args[1]).upper())

	trades = []
	for i in xrange(2, len(args), 3):
		trade = dal.create_trade(client, pair, float(args[i]), str(args[i+1]).upper(), float(args[i+2]))
		trades.append(trade)

	return trades

def create_alert(client, args):
	pair = (str(args[0]).upper(), str(args[1]).upper())
	return dal.create_alert(client, pair, float(args[2]))

