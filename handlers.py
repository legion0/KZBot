
import datetime
import dal
import logging

from telegram.ext import CommandHandler
from telegram.error import (TelegramError, Unauthorized, BadRequest, TimedOut, ChatMigrated, NetworkError)

from constants import kRunInterval
from threading_util import requires_lock
from telegram_util import bot_msg_exception, verify_owner
from dal import config, trades_db, get_flat_symbols, find_trades_by_pair
from format import build_status_msg, format_scientific, format_trades, find_exp
from binance_util import BinanceClient
from my_worker import get_instance as get_worker
import cryptocompare_util as cryptocompare

_USAGE = """
/start <API_KEY> <API_SECRET>
/trade <COIN> <MARKET> <QUANTITY> <TYPE> <THRESHOLD>
/trade LTC BTC 1 BUY_BELOW_AT_MARKET 0.22 # Buy Zone
1 SELL_ABOVE_AT_MARKET 0.24 # Profit
1 SELL_BELOW_AT_MARKET 0.2 # Stop loss
1 TRAILING_STOP_LOSS 0.1 # 10% trailing stop loss
/info LTC BTC
/alert LTC BTC 0.23
/status - get current status of open trades.
/remove <TRADE_ID>
"""

@requires_lock
@bot_msg_exception
@verify_owner
def start_handler(bot, update, args):
	logging.debug("Responding to /start: %s" % args)
	if len(args) != 2:
		text = 'Wrong Usage'
		bot.send_message(chat_id=update.message.chat_id, text=text)
		return

	config['chat_id'] = update.message.chat_id
	config['owner_id'] = update.message.from_user.id
	config['api_key'] = str(args[0])
	config['secret'] = str(args[1])
	config.sync()

	bot.send_message(chat_id=update.message.chat_id, text="ack!")

@requires_lock
@bot_msg_exception
@verify_owner
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
@verify_owner
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
@verify_owner
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

_INFO_TEMPLATE = """
price: %s
min_q: %s
q_step: %s
min_price: %s
price_step: %s
""".strip()

@requires_lock
@bot_msg_exception
@verify_owner
def info_handler(bot, update, args):
	logging.debug("Responding to /info: args=%r." % args)
	pair = (str(args[0]).upper(), str(args[1]).upper())

	client = BinanceClient(config['api_key'], config['secret'])
	prices = client.get_prices((pair,))
	current_price = prices[pair[0] + pair[1]]

	symbol_info = client.get_symbol_info(pair)
	lot_size_step = client.get_lot_size_step(symbol_info)
	exp = find_exp(current_price)
	lot_exp = find_exp(lot_size_step)
	text = _INFO_TEMPLATE % (
		format_scientific(current_price, exp),
		format_scientific(client.get_min_lot_size(symbol_info), lot_exp),
		format_scientific(lot_size_step, lot_exp),
		format_scientific(client.get_min_price(symbol_info), exp),
		format_scientific(client.get_price_step(symbol_info), exp),
	)
	bot.send_message(chat_id=update.message.chat_id, text=text)

def reverse_price(price):
	if price is None:
		return price
	return 1 / price

@requires_lock
@bot_msg_exception
@verify_owner
def convert_handler(bot, update, args):
	logging.debug("Responding to /convert: args=%r." % args)
	quantity = float(args[0])
	pair = (str(args[1]).upper(), str(args[2]).upper())

	client = BinanceClient(config['api_key'], config['secret'])
	prices = client.get_prices()
	current_price = prices.get(pair[0] + pair[1], None) or reverse_price(prices.get(pair[1] + pair[0], None))
	bridge_price_1 = prices.get(pair[0] + 'BTC', None) or reverse_price(prices.get('BTC' + pair[0], None))
	bridge_price_2 = prices.get('BTC' + pair[1], None) or reverse_price(prices.get(pair[1] + 'BTC', None))


	if current_price is not None:
		#exp = find_exp(current_price)
		text = format_scientific(quantity * current_price)
	elif bridge_price_1 is not None and bridge_price_2 is not None:
		text = format_scientific(quantity * bridge_price_1 * bridge_price_2)
	else:
		text = 'Cannot find price for %s' % (pair,)

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
@verify_owner
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
@verify_owner
def alert_handler(bot, update, args):
	global open_trades, config
	logging.debug("Responding to /alert: args=%r." % args)

	client = BinanceClient(config['api_key'], config['secret'])
	alert = create_alert(client, args)

	dal.save_alert(alert)

	text = [str(trade), '\nack!']

	bot.send_message(chat_id=update.message.chat_id, text='\n'.join(text))

@requires_lock
@bot_msg_exception
@verify_owner
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
	dispatcher.add_handler(CommandHandler('info', info_handler, pass_args=True))
	dispatcher.add_handler(CommandHandler('convert', convert_handler, pass_args=True))
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

