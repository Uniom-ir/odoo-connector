# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
from . import controllers
from . import models
from . import wizards


def post_init_hook(env):
    """Link shipped fa/ar templates to their language records.

    Language records only exist once a language has been activated in the
    instance; languages loaded via --load-language appear *after* this hook,
    so the heavy lifting lives in uniom.template._link_language_templates()
    and can be re-run any time.
    """
    env["uniom.template"]._link_language_templates()
