If you do not yet have a Binance account please use my referal link: https://www.binance.com/?ref=12559326

1. Get a VPS, https://console.cloud.google.com has a free micro instance that is sufficient for running this bot.

2. Get a telegram bot token from https://telegram.me/botfather and write it down somewhere.

3. ssh into the machine.
	1. make sure you have all deps installed: `sudo apt-get update && sudo apt-get install git ipython python2.7 virtualenv python-dev tmux`.
	2. clone this repo.

## setup python env
1. cd into the project directory.
2. create a python virtual env with `virtualenv .pyenv`
3. start the env using the helper scipt with `. pyenv.sh`
4. install the requirments with `pip install -r requirments.txt`
5. write your token into `telegram.bot.token` with `echo <TOKEN> > telegram.bot.token`
6. `mkdir data`

## Running the bot
1. cd into the project directory.
2. start tmux with `tmux`.
3. start the env using the helper scipt with `. pyenv.sh`
4. open ipython with `ipython`
5. load the script with `%run script.py`
6. run the script with `main()`

If you want to disconnect then detach from tmux with `Ctrl+b d`.
To reattach use `tmux a`

To monitor the logs run `tail -f log.txt` in a separate tmux pane/window/session/terminal/planet/galaxy.

## Keys setup
1. text your bot: `/start <API_KEY> <API_SECRET>` to register your keys.

## TODO:
* Add instructions on how to run the script on boot in case the machine restarts.
* Do this guide on a fresh machine to make sure i did not forget any steps.


## Making money off this ? Please donate me a cup of coffe/beer:
LTC: LRvSzKF9qi8uSz5K8nqCiKiLaCNmuFNEKo

ETH: 0x1A6B538A2D53212Dd1FDEd06bE746101C746b7B6

BTC: 13RiGBZDhyHKWMfd6CVny1ViykEsyJshau
