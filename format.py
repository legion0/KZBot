
from constants import TRADE_TYPE as _TRADE_TYPE

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
		pair = "%s%s" % trade['pair']
		if pair != last_pair:
			last_pair = pair
			lines.append("%s:" % pair)
		exp = find_exp(prices[pair])
		if trade['type'] == _TRADE_TYPE.ALERT_BELOW or trade['type'] == _TRADE_TYPE.ALERT_ABOVE:
			lines.append("%s %s (id=%d)" % (format_scientific(trade['threshold'], exp), trade['type'], trade['id']))
		else:
			lines.append("%s %s %s (id=%d)" % (format_scientific(trade['threshold'], exp), trade['type'], trade['quantity'], trade['id']))
	return '\n'.join(lines)

def build_status_msg(trades, prices, balances, use_repr=False):
	text = ['Status:', format_trades(trades.itervalues(), use_repr, prices)]
	text.append('\nPrices:\n%s' % format_prices(prices))
	text.append('\nBalances:\n%s' % format_balances(balances))

	return '\n'.join(text)

