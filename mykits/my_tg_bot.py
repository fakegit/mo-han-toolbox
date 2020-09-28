#!/usr/bin/env python3
# encoding=utf8
import argparse
import os
import re
from pprint import pformat

from mylib.log import get_logger
from mylib.os_util import read_json_file, ensure_sigint_signal
from mylib.tricks import ArgParseCompactHelpFormatter

ap = argparse.ArgumentParser(formatter_class=ArgParseCompactHelpFormatter)
ap.add_argument('-c', '--config-file', metavar='path', required=True)
ap.add_argument('-v', '--verbose', action='store_true')
ap.add_argument('-T', '--timeout', type=float)
args = ap.parse_args()


def main():
    from telegram.ext import MessageHandler, Filters
    from mylib.bilibili import find_bilibili_vid
    from mylib.tg_bot import SimpleBot, meta_deco_handler_method, CommandHandler

    class MyAssistantBot(SimpleBot):
        @meta_deco_handler_method(MessageHandler, filters=Filters.regex(
            re.compile(r'BV[\da-zA-Z]{10}|av\d+|bilibili|b23\.tv')))
        def bilibili_video(self, update, context):
            program = 'bldl'
            vid = find_bilibili_vid(update.message.text)
            cmd = f'{program} {vid}'
            update.message.reply_text(f'+ {vid}')
            os.system(cmd)
            update.message.reply_text(f'* {vid}')

        @meta_deco_handler_method(CommandHandler)
        def _secret(self, update, context):
            self.__typing__(update)
            for name in ('effective_message', 'effective_user'):
                update.message.reply_text(name)
                update.message.reply_text(pformat(getattr(update, name).to_dict()))
            update.message.reply_text('bot.get_me()')
            update.message.reply_text(pformat(self.bot.get_me().to_dict()))

    config_file = args.config_file
    if args.verbose:
        log_lvl = 'DEBUG'
    else:
        log_lvl = 'INFO'
    get_logger('telegram').setLevel(log_lvl)
    config = read_json_file(config_file)
    token = config['token']
    MyAssistantBot(token, user_whitelist=config.get('user_whitelist'), timeout=args.timeout)


if __name__ == '__main__':
    ensure_sigint_signal()
    main()