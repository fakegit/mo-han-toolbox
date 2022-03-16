#!/bin/sh

pyclean .
cp -rp mylib ~/bin/
cp -rp ezpykit ~/bin/
cp -rp ezpykitext ~/bin/
cp -rp websites ~/bin/
cp -rp i18n ~/bin/
install -p -m 755 mykits/mykit.py ~/bin/mykit
install -p -m 755 mykits/my_tg_bot.py ~/bin/my_tg_bot
