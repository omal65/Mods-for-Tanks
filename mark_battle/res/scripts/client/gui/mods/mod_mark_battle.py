# -*- coding: utf-8 -*-
#
# MarkBattle v0.1 - точка входа мода.
#
# Лоадер клиента вызывает init() при старте.
#
MOD_VERSION = '{{VERSION}}'

from .mark_battle import app


def init():
    app.init(MOD_VERSION)