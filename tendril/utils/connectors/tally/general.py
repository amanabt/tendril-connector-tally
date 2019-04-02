#!/usr/bin/env python
# encoding: utf-8

# Copyright (C) 2019 Chintalagiri Shashank
#
# This file is part of tendril-connector-tally.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


from . import TallyElement
from .utils import yesorno


class TallyUnit(TallyElement):
    elements = {
        'name': ('name', str, True),
        'originalname': ('originalname', str, False),
        'decimalplaces': ('decimalplaces', int, True),
        'issimpleunit': ('issimpleunit', yesorno, True),
        'additionalunits': ('additionalunits', str, False),
        'conversion': ('conversion', float, False)
    }

    def __repr__(self):
        return "<TallyUnit {0}>".format(self.name)
