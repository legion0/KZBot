1. Get a VPS, https://console.cloud.google.com has a free micro instance that is sufficient for running this bot.

2. Get a telegram bot token from https://telegram.me/botfather and write it down somewhere.

3. ssh into the machine.
	1. make sure you have all deps installed: `sudo apt-get update && sudo apt-get install git ipython python2.7 virtualenv`.
	2. clone this repo.

## setup python env
1. cd into the project directory.
2. create a python virtual env with `virtualenv .pyenv`
3. start the env using the helper scipt with `. pyenv.sh`
4. install the requirments with `pip install -r requirments.txt`
5. write your token into `telegram.bot.token` with `echo <TOKEN> > telegram.bot.token`

## Running the bot
1. cd into the project directory.
2. start the env using the helper scipt with `. pyenv.sh`
3. open ipython with `ipython`
4. load the script with `%run script.py`
5. run the script with `main()`

## Keys setup
1. text your bot: `/start <API_KEY> <API_SECRET>` to register your keys.

## TODO:
* Add instructions on how to run the script on boot in case the machine restarts.
* Do this guide on a fresh machine to make sure i did not forget any steps.

