#!/usr/bin/env python
# encoding: utf-8

# Copyright (C) 2017 Chintalagiri Shashank
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

"""
Docstring for __init__.py
"""

import inspect
import requests
from decimal import Decimal
from copy import copy
from six import iteritems
from lxml import etree
from six import StringIO
from collections import namedtuple
from bs4 import BeautifulSoup
from requests.exceptions import ConnectionError
from requests.structures import CaseInsensitiveDict
from decimal import InvalidOperation
from .utils import get_date_range
from .cache import cachefs

try:
    from tendril.config import TALLY_HOST
    from tendril.config import TALLY_PORT
except ImportError:
    TALLY_HOST = 'localhost'
    TALLY_PORT = 9002


TallyQueryParameters = namedtuple('TallyQueryParameters',
                                  'header body')

TallyRequestHeader = namedtuple('TallyRequestHeader',
                                'version tallyrequest type id')


class TallyNotAvailable(ConnectionError):
    pass


class TallyObject(object):
    def __init__(self, soup):
        self._soup = soup


class TallyElement(TallyObject):
    def __init__(self, soup, ctx=None):
        super(TallyElement, self).__init__(soup)
        self._ctx = ctx
        self._populate()

    elements = {}
    descendent_elements = {}
    attrs = {}
    lists = {}
    multilines = {}

    @property
    def company_name(self):
        return self._ctx.company_name

    @property
    def company_masters(self):
        import masters
        return masters.get_master(self.company_name)

    def _process_elements(self):
        for k, v in iteritems(self.elements):
            try:
                candidates = self._soup.findChildren(v[0], recursive=False)
                if v[1] == str:
                    val = ':'.join([v[1](c.text) for c in candidates])
                else:
                    if len(candidates) == 0:
                        pass
                    if len(candidates) > 1:
                        raise NameError(k, v, candidates)
                    if inspect.isclass(v[1]) and issubclass(v[1], TallyElement):
                        val = v[1](candidates[0].text, self._ctx)
                    elif v[1] == Decimal and not candidates[0].text.strip():
                        val = Decimal("0")
                    else:
                        val = v[1](candidates[0].text)
            except (TypeError, AttributeError, IndexError, NameError, InvalidOperation):
                if not v[2]:
                    val = None
                else:
                    raise
            except ValueError:
                raise
            setattr(self, k, val)

    def _process_descendent_elements(self):
        for k, v in iteritems(self.descendent_elements):
            try:
                candidates = self._soup.findChildren(v[0])
                if v[1] == str:
                    val = ':'.join([v[1](c.text) for c in candidates])
                else:
                    if len(candidates) == 0:
                        pass
                    if len(candidates) > 1:
                        raise NameError(k, v, candidates)
                    if inspect.isclass(v[1]) and issubclass(v[1], TallyElement):
                        val = v[1](candidates[0].text, self._ctx)
                    else:
                        val = v[1](candidates[0].text)
            except (TypeError, AttributeError, IndexError, NameError, InvalidOperation):
                if not v[2]:
                    val = None
                else:
                    raise
            except ValueError:
                raise
            setattr(self, k, val)

    def _process_attrs(self):
        for k, v in iteritems(self.attrs):
            try:
                val = v[1](self._soup.attrs[v[0]])
            except:
                if not v[2]:
                    val = None
                else:
                    raise
            setattr(self, k, val)

    def _process_lists(self):
        for k, v in iteritems(self.lists):
            candidates = self._soup.findChildren(v[0] + '.list')
            if inspect.isclass(v[1]) and issubclass(v[1], TallyElement):
                val = [v[1](c, self._ctx) for c in candidates]
            else:
                val = [v[1](c) for c in candidates]
            setattr(self, k, val)

    def _process_multilines(self):
        for k, v in iteritems(self.multilines):
            try:
                candidates = self._soup.findChildren(v[0] + '.list')
                if len(candidates) == 0:
                    val = ''
                elif len(candidates) > 1:
                    raise Exception(k, v, candidates)
                else:
                    lines = [v[1](l.text.strip())
                             for l in candidates[0].findChildren(v[0])]
                    if len(lines) == 1:
                        val = lines[0]
                    elif len(lines) == 0:
                        val = ''
                    else:
                        val = '\n'.join(lines)
            except (TypeError, AttributeError, IndexError):
                if not v[2]:
                    val = None
                else:
                    raise
            except ValueError:
                raise
            setattr(self, k, val)

    def _populate(self):
        self._process_attrs()
        self._process_elements()
        self._process_lists()
        self._process_multilines()
        self._process_descendent_elements()


class TallyReport(object):
    _header = 'Export Data'
    _container = None
    _cachename = None
    _content = {}

    def __init__(self, company_name):
        self._xion = None
        self._soup = None
        self._company_name = company_name

    @property
    def company_name(self):
        return self._company_name

    @property
    def cachename(self):
        if not self._cachename:
            return None
        company_name = copy(self.company_name)
        company_name = company_name.replace(' ', '_')
        company_name = company_name.replace('.', '')
        company_name = company_name.replace('-', '')
        return "{0}.{1}".format(self._cachename, company_name)

    @staticmethod
    def _build_fetchlist(parent, fetchlist):
        for item in fetchlist:
            f = etree.SubElement(parent, 'FETCH')
            f.text = item

    def _set_request_date(self, svnode, dt=None, end_dt=None):
        (start, end), current = get_date_range(dt, end_dt)
        svfd = etree.SubElement(svnode, 'SVFROMDATE', TYPE='Date')
        svfd.text = start.strftime("%d-%m-%Y")
        svtd = etree.SubElement(svnode, 'SVTODATE', TYPE='Date')
        svtd.text = end.strftime("%d-%m-%Y")
        svcd = etree.SubElement(svnode, 'SVCURRENTDATE', TYPE='Date')
        svcd.text = current.strftime("%d-%m-%Y")

    def _set_request_staticvariables(self, svnode):
        svef = etree.SubElement(svnode, 'SVEXPORTFORMAT')
        svef.text = '$$SysName:XML'
        svec = etree.SubElement(svnode, 'ENCODINGTYPE')
        svec.text = 'UNICODE'
        if self.company_name:
            svcc = etree.SubElement(svnode, 'SVCURRENTCOMPANY', TYPE="String")
            svcc.text = self.company_name

    def _build_request_body(self):
        raise NotImplementedError

    def _build_request_header(self):
        # TODO Move into the engine?
        h = etree.Element('HEADER')
        if isinstance(self._header, str):
            tr = etree.SubElement(h, 'TALLYREQUEST')
            tr.text = self._header
        elif isinstance(self._header, TallyRequestHeader):
            v = etree.SubElement(h, 'VERSION')
            v.text = str(self._header.version)
            tr = etree.SubElement(h, 'TALLYREQUEST')
            tr.text = self._header.tallyrequest
            ty = etree.SubElement(h, 'TYPE')
            ty.text = self._header.type
            rid = etree.SubElement(h, 'ID')
            rid.text = self._header.id
        return etree.ElementTree(h)

    def _acquire_raw_response(self):
        self._xion = TallyXMLEngine()
        query = TallyQueryParameters(self._build_request_header(),
                                     self._build_request_body())
        self._soup = self._xion.execute(query, cachename=self.cachename)

    def _acquire_cached_raw_response(self):
        try:
            with cachefs.open(self.cachename + '.xml', 'rb') as f:
                content = f.read()
            self._soup = BeautifulSoup(content.decode('utf-8', 'ignore'), 'lxml')
        except:
            raise TallyNotAvailable

    @property
    def soup(self):
        if not self._soup:
            try:
                self._acquire_raw_response()
            except TallyNotAvailable:
                if cachefs and self.cachename:
                    print("Trying to return cached response for {0} from {1}"
                          "".format(self.cachename, cachefs))
                    self._acquire_cached_raw_response()
                else:
                    raise
        return self._soup

    def __getattr__(self, item):
        if item not in self._content.keys():
            raise AttributeError(item)
        soup = self.soup
        if self._container:
            soup = soup.find(self._container)
        val = CaseInsensitiveDict()
        for y in [self._content[item][1](x, self)
                  for x in soup.findAll(self._content[item][0])]:
            val[y.name] = y
        self.__setattr__(item, val)
        return val


class TallyXMLEngine(object):
    """
    Very bare-bones architecture. Could do with more structure.  
    """
    def __init__(self):
        self._query = None
        self._response = None

    def execute(self, query, cachename=None):
        self.query = query
        headers = {'Content-Type': 'application/xml'}
        uri = 'http://{0}:{1}'.format(TALLY_HOST, TALLY_PORT)
        xmlstring = StringIO()
        self.query.write(xmlstring)
        try:
            print("Sending Tally request to {0}".format(uri))
            r = requests.post(uri, data=xmlstring.getvalue(), headers=headers)
        except ConnectionError as e:
            print("Got Exception")
            print(e)
            raise TallyNotAvailable
        if cachefs and cachename:
            with cachefs.open(cachename + '.xml', 'wb') as f:
                f.write(r.content)
        self._response = BeautifulSoup(r.content.decode('utf-8', 'ignore'), 'lxml')
        return self._response

    @staticmethod
    def _query_base():
        root = etree.Element('ENVELOPE')
        query = etree.ElementTree(root)
        return query

    @property
    def query(self):
        return self._query

    @query.setter
    def query(self, params):
        q = self._query_base()
        q.getroot().append(params.header.getroot())
        body = etree.SubElement(q.getroot(), 'BODY')
        body.append(params.body.getroot())
        self._query = q

    @property
    def response(self):
        return self._response

    def print_query(self):
        s = StringIO()
        self.query.write(s)
        print(s.getvalue())
