from functools import wraps as wraps
from dal import config
from telegram.ext import Updater

import traceback

def bot_msg_exception(func):
	@wraps(func)
	def wrapped(bot, update, *args, **kwargs):
		try:
			return func(bot, update, *args, **kwargs)
		except Exception as e:
			error_str = 'Got %s: %s at:\n%s' % (type(e), e, traceback.format_exc())
			bot.send_message(chat_id=update.message.chat_id, text=error_str)
	return wrapped

def notify_user(text, when=0):
	get_updater().job_queue.run_once(notify_user_callback, when, {'chat_id': config['chat_id'], 'text': text})

_glb_updater = None
def get_updater():
	global _glb_updater
	if _glb_updater is not None:
		return _glb_updater

	with open('telegram.bot.token') as f:
		_glb_updater = Updater(token=f.read().strip())
	return _glb_updater

def notify_user(text, when=0):
		get_updater().job_queue.run_once(_notify_user_callback, when, {'chat_id': config['chat_id'], 'text': text})

def _notify_user_callback(bot, job):
    context = job.context
    chat_id = context['chat_id']
    text = context['text']
    bot.send_message(chat_id=chat_id, text=text)


