
from telegram import CommandHandler

from constants import kRunInterval
from threading_util import requires_lock
from telegram_util import bot_msg_exception
from dal import config, trades_db, get_flat_symbols
from format import build_status_msg, format_scientific
from binance_util import BinanceClient
from my_worker import get_instance as get_worker
import cryptocompare_util as cryptocompare

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
		key = str(int(arg))

		if key in trades_db:
			text.append('Trade removed: %s' % trades_db[key])
			del trades_db[key]
		else:
			text.append('key %r not found!' % key)
	trades_db.sync()

	bot.send_message(chat_id=update.message.chat_id, text='\n\n'.join(text))

@requires_lock
@bot_msg_exception
def price_handler(bot, update, args):
	logging.debug("Responding to /price: args=%r." % args)
	client = BinanceClient(config['api_key'], config['secret'])
	price = get_price(args[0], args[1], client)
	prices = client.get_prices((args,))
	current_price = prices[args[0] + args[1]]
	text =	format_scientific(price)
	bot.send_message(chat_id=update.message.chat_id, text=text)

#def get_price(fsym, tsym, client):
#	if tsym == 'USD':
#		current_price = cryptocompare.get_price(fsym, tsym, 'Coinbase')
#	else:
#		prices = client.get_prices(((fsym, tsym),))
#		current_price = prices[fsym + tsym]
#	return current_price

def register_handlers(dispatcher):
	dispatcher.add_handler(CommandHandler('start', start_handler, pass_args=True))
	dispatcher.add_handler(CommandHandler('trade', trade_handler, pass_args=True))
	dispatcher.add_handler(CommandHandler('alert', alert_handler, pass_args=True))
	dispatcher.add_handler(CommandHandler('price', price_handler, pass_args=True))
	dispatcher.add_handler(CommandHandler('remove', remove_handler, pass_args=True))
	dispatcher.add_handler(CommandHandler('status', status_handler, pass_args=True))
	dispatcher.add_handler(CommandHandler('ping', ping_handler))
	dispatcher.add_handler(CommandHandler('help', help_handler))

