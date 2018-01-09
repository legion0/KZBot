import requests

def get_price(fsym, tsym, e):
	r = requests.get('https://min-api.cryptocompare.com/data/price', params={
		'fsym': fsym,
		'tsyms': tsym,
		'e': e,
	})
	if r.status_code != 200:
		raise Exception('Invalid status code: %s' % r.status_code)
	j = r.json()
	if 'Response' in j and j['Response'] == 'Error':
		raise Exception('Error: %s' % j['Message'])
	return r.json()[tsym]

