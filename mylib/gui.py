#!/usr/bin/env python3
# encoding=utf8
import os
import re
import shutil

import PySimpleGUIQt as PySimpleGUI

from .tricks import remove_from_list, dedup_list
from .util import ensure_sigint_signal, real_join_path, write_json_file, read_json_file

SPECIAL_KEYS = {
    'special 16777216': 'esc',
    'special 16777249': 'ctrl',
    'special 16777248': 'shift',
    'special 16777250': 'win',
    'special 16777301': 'menu',
    'special 16777217': 'tab',
    'special 16777251': 'alt',
    'special 16777223': 'delete',
    'special 16777232': 'home',
    'special 16777233': 'end',
    'special 16777238': 'pageup',
    'special 16777239': 'pagedown',
    'special 16777222': 'insert',
    'special 16777253': 'numlock',
    'special 16777220': 'enter',
    'special 16777219': 'backspace',
    'special 16777235': 'up',
    'special 16777237': 'down',
    'special 16777234': 'left',
    'special 16777236': 'right',
}


def rename_dialog(src: str):
    sg = PySimpleGUI
    conf_file = real_join_path('~', '.config/rename_dialog.json')
    root = 'root'
    fname = 'fname'
    ext = 'ext'
    new_root = 'new_root'
    new_base = 'new_base'
    ok = 'OK'
    cancel = 'Cancel'
    pattern = 'pattern'
    replace = 'replace'
    save_replace = 'save_replace'
    save_pattern = 'save_pattern'
    title = 'Rename - {}'.format(src)
    h = .7

    conf = read_json_file(conf_file, default={pattern: [''], replace: ['']})
    tmp_pl = conf[pattern]
    tmp_rl = conf[replace]
    old_root, old_base = os.path.split(src)
    old_fn, old_ext = os.path.splitext(old_base)

    layout = [
        [sg.T(src, key='src')],
        [sg.HorizontalSeparator()],
        [sg.I(old_root, key=root),
         sg.FolderBrowse('...', target=root, initial_folder=old_root, size=(6, h))],
        [sg.I(old_fn, key=fname, focus=True),
         sg.I(old_ext, key=ext, size=(6, h))],
        [sg.HorizontalSeparator()],
        [sg.T('Regular Expression Substitution Pattern & Replacement')],
        [sg.T(size=(0, h)),
         sg.Drop(tmp_pl, key=pattern, enable_events=True, text_color='blue'),
         sg.CB('', default=True, key=save_pattern, enable_events=True, size=(2, h)),
         sg.Drop(tmp_rl, key=replace, enable_events=True, text_color='blue'),
         sg.CB('', default=True, key=save_replace, enable_events=True, size=(2, h))],
        [sg.HorizontalSeparator()],
        [sg.I(old_root, key=new_root)],
        [sg.I(old_fn + old_ext, key=new_base)],
        [sg.Submit(ok, size=(10, 1)),
         sg.Stretch(),
         sg.Cancel(cancel, size=(10, 1))]]

    ensure_sigint_signal()
    window = sg.Window(title, return_keyboard_events=True).layout(layout).finalize()
    window.bring_to_front()

    loop = True
    data = {fname: old_fn, ext: old_ext, pattern: tmp_pl[0], replace: tmp_rl[0], root: old_root}
    while loop:
        try:
            tmp_fname = data[fname] + data[ext]
            if data[pattern]:
                # noinspection PyBroadException
                try:
                    tmp_fname = re.sub(data[pattern], data[replace], tmp_fname)
                except Exception:
                    pass
            dst = os.path.realpath(os.path.join(data[root], tmp_fname))
        except TypeError:
            dst = src
        np, nb = os.path.split(dst)
        window[new_root].update(np)
        window[new_base].update(nb)

        event, data = window.read()
        window[new_root].update(text_color=None)
        window[new_base].update(text_color=None)
        cur_p = data[pattern]
        cur_r = data[replace]

        if event in SPECIAL_KEYS and SPECIAL_KEYS[event] == 'esc':
            loop = False
        elif event == save_pattern:
            if data[save_pattern]:
                conf[pattern].insert(0, cur_p)
                conf[pattern] = dedup_list(conf[pattern])
            elif cur_p:
                conf[pattern] = remove_from_list(conf[pattern], [cur_p])
        elif event == save_replace:
            if data[save_replace]:
                conf[replace].insert(0, cur_r)
                conf[replace] = dedup_list(conf[replace])
            elif cur_r:
                conf[replace] = remove_from_list(conf[replace], [cur_r])
        elif event == pattern:
            window[save_pattern].update(value=cur_p in conf[pattern])
        elif event == replace:
            window[save_replace].update(value=cur_r in conf[replace])
        elif event == ok:
            try:
                shutil.move(src, dst)
                loop = False
            except (FileNotFoundError, FileExistsError) as e:
                window[new_root].update(text_color='red')
                window[new_base].update(text_color='red')
        elif event in (None, cancel):
            loop = False
        else:
            ...
    else:
        write_json_file(conf_file, conf, indent=0)

    window.close()
