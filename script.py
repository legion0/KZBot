#!/usr/bin/env python2.7

def create_trades(config, client, args):
	pair = (str(args[0]).upper(), str(args[1]).upper())

	trades = []
	for i in xrange(2, len(args), 3):
		next_id = config['next_id'] if 'next_id' in config else 0
		trade = {
			'id': next_id,
			'pair': pair,
			'quantity': float(args[i]),
			'type': str(args[i+1]).upper(),
			'threshold': float(args[i+2]),
		}
		order = client.create_test_order(
			pair=pair,
			side=Client.SIDE_BUY,
			type=Client.ORDER_TYPE_MARKET,
			quantity=trade['quantity'])
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
@bot_msg_exception
def trade_handler(bot, update, args):
	global open_trades, config
	logging.debug("Responding to /trade: args=%r." % args)
	client = BinanceClient(config)

	trades = create_trades(config, client, args)
	for trade in trades:
		open_trades[str(trade['id'])] = trade
	open_trades.sync()

	text = [str(trades), '\nack!']

	bot.send_message(chat_id=update.message.chat_id, text='\n'.join(text))

@requires_lock
@bot_msg_exception
def alert_handler(bot, update, args):
	global open_trades, config
	logging.debug("Responding to /alert: args=%r." % args)

	trade = create_alert(config, args)

	client = BinanceClient(config)
	prices = client.get_prices((trade['pair'],))
	current_price = prices[trade['pair'][0] + trade['pair'][1]]

	if trade['threshold'] > current_price:
		trade['type'] = TRADE_TYPE.ALERT_ABOVE
	else:
		trade['type'] = TRADE_TYPE.ALERT_BELOW


	open_trades[str(trade['id'])] = trade
	open_trades.sync()

	text = [str(trade), '\nack!']

	bot.send_message(chat_id=update.message.chat_id, text='\n'.join(text))

@bot_msg_exception
def help_handler(bot, update):
	logging.debug("Responding to /help.")
	bot.send_message(chat_id=update.message.chat_id, text="""/start <API_KEY> <SECRET>
/trade <COIN> <MARKET> <QUANTITY> <TYPE> <THRESHOLD>
/trade LTC BTC 1 BUY_BELOW_AT_MARKET 0.22 # Buy Zone
1 SELL_ABOVE_AT_MARKET 0.24 # Profit
1 SELL_BELOW_AT_MARKET 0.2 # Stop loss
/price LTC BTC
/alert LTC BTC 0.23
/status - get current status of open trades.
/remove <TRADE_ID>
""")


logging.basicConfig(filename='log.txt', format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)

#bot = telegram.Bot(token='483544796:AAHuhbEYsLWZJ5EdbzXDfwJM4ZvpE1N2J50')
#print(bot.get_me())

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
	loop_runner = MyWorker()
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

def notify_user_callback(bot, job):
	context = job.context
	chat_id = context['chat_id']
	text = context['text']
	bot.send_message(chat_id=chat_id, text=text)



