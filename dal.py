
import shelve as _shelve

config = _shelve.open('data/config.shelve')

trades_db = _shelve.open('data/open_trades.shelve')

def get_flat_symbols(trades_db):
	pairs = [x['pair'] for x in trades_db.itervalues()]
	return set([symbol for pair in pairs for symbol in pair])

