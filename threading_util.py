import threading as _threading
from functools import wraps as _wraps

_glb_lock = _threading.Lock()

def requires_lock(func):
	@_wraps(func)
	def wrapped(*args, **kwargs):
		with _glb_lock:
			return func(*args, **kwargs)
	return wrapped

