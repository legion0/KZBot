#!/usr/bin/env python2.7

import logging
from telegram_util import get_updater
from handlers import register_handlers
from my_worker import get_instance as get_worker
from dal import trades_db, config

def main():
	logging.basicConfig(filename='log.txt', format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
	register_handlers(get_updater().dispatcher)
	get_worker().start()
	get_updater().start_polling()

	logging.info("Up!")

def stop():
	get_worker().stop()
	get_updater().stop()

	trades_db.sync()
	config.sync()
	logging.info("Down!")





