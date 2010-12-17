"""

Mount point
Maximum file size

http://someproxy.example.org/mount_point?url=url_encoded&sheet=1&range=A1:K3&doc=no&indent=4&format=jsonp



Response format:

header 
    url = http://...file.xls
    option = 'row=5&row=7&row_range=10:100000:5000',
response
    sheet = 'Sheet 1',
    data = [
        [...],
        [...],
        [...],
    ]




	
44	* Downloading the entire spreadsheet
45	* Downloading a single sheet (add ``sheet=1`` to the URL)
46	* Downloading a range in a single sheet (add ``range=A1:K3`` to the URL) [a bit nasty for CSV files but will do I think]
47	* Choosing a limited set of rows within the sheet (add ``row=5&row=7&row_range=10:100000:5000`` - rowrange format would be give me a row between 10 and 100000 every 5000 rows)
48	



81	Hurdles
82	-------
83	
84	* Some data sets are not in text-based formats => Don't handle them at this stage
85	* Excel spreadhseets have formatting and different types => Ignore it, turn everything into a string for now
86	* Some data sets are huge => don't proxy more than 100K of data - up to the user to filter it down if needed
87	* We don't want to re-download data sets => Need a way to cache data -> storage API
88	* Some applications might be wildly popular and put strain on the system -> perhaps API keys and rate limiting are needed so that individual apps/feeds can be disabled. How can we have read API keys on data.gov.uk? 



"""
import urlparse
import csv
import httplib
import logging
import urllib2
from cgi import FieldStorage
from StringIO import StringIO
try:
    import json
except ImportError:
    import simplejson as json
import xlrd
from bn import AttributeDict

log = logging.getLogger(__name__)

def get_length(server, path):
    conn = httplib.HTTPConnection(server)
    conn.request("HEAD", path)
    res = conn.getresponse()
    #print res.status, res.reason
    headers = res.getheaders()
    length = None
    for k, v in headers:
        if k.lower() == 'content-length':
            length = v
            break
    if not length:
        raise Exception('No content-length returned for % server %r path'%(server, path))
    return int(length)

def render(**vars):
    return ["""
    <html>
    <head>
        <title>%(title)s</title>
    </head>
    <body>
    <h1>%(title)s</h1>
    
    <p>%(msg)s</p>
    
    </body>
    </html>
    """%vars
]

def error(**vars):
    return json.dumps(dict(error=vars), indent=4)

class HTTPResponseMarble(object):
    def __init__(self, *k, **p):
        self.__dict__['status'] = u'200 OK'
        self.__dict__['status_format'] = u'unicode'
        self.__dict__['header_list'] = [dict(name=u'Content-Type', value=u'text/html; charset=utf8')]
        self.__dict__['header_list_format'] = u'unicode'
        self.__dict__['body'] = []
        self.__dict__['body_format'] = u'unicode'

    def __setattr__(self, name, value):
        if name not in self.__dict__:
            raise AttributeError('No such attribute %s'%name)
        self.__dict__[name] = value

class JsonpDataProxy(object):

    def __init__(self, max_length):
        self.max_length = int(max_length)

    def __call__(self, environ, start_response):
        # This is effectively the WSGI app.
        # Fake a pipestack setup so we cna port this code eventually
        flow = AttributeDict()
        flow['app'] = AttributeDict()
        flow['app']['config'] = AttributeDict()
        flow['app']['config']['proxy'] = AttributeDict(max_length=int(self.max_length))
        flow['environ'] = environ
        flow['http_response'] = HTTPResponseMarble()
        flow.http_response.header_list = [dict(name='Content-Type', value='application/javascript')]
        flow['query'] = FieldStorage(environ=flow.environ)
        self.index(flow)
        start_response(
            str(flow.http_response.status),
            [tuple([item['name'], item['value']]) for item in flow.http_response.header_list],
        )
        resp  = ''.join([x.encode('utf-8') for x in flow.http_response.body])
        format = None
        if flow.query.has_key('format'):
            format = flow.query.getfirst('format')
        if not format or format == 'jsonp':
            callback = 'callback'
            if flow.query.has_key('callback'):
                callback = flow.query.getfirst('callback')
            return [callback+'('+resp+')']
        elif format == 'json':
            return [resp]
        else:
            raise Exception('Unknown format %s'%format)

    def index(self, flow):
        if not flow.query.has_key('url'):
            title = 'No ?url= found'
            msg = 'Please read the API format docs'
            flow.http_response.status = '200 Error %s'%title 
            flow.http_response.body = error(title=title, msg=msg)
        else:
            url = flow.query.getfirst('url')
            parts = url.split('.')
            if not len(parts) > 1:
                title = 'Could not determine the file type'
                msg = 'Please ensure URLs have a .csv or .xls extension'
                flow.http_response.status = '200 Error %s'%title 
                flow.http_response.body = error(title=title, msg=msg)
            else:
                extension = parts[-1].lower()
                if not extension in ['csv', 'xls']:
                    title = 'Unsupported file type'
                    msg = 'Please ensure URLs have a .csv or .xls extension'
                    flow.http_response.status = '200 Error %s'%title 
                    flow.http_response.body = error(title=title, msg=msg)
                else:
                    urlparts = urlparse.urlparse(url)
                    if urlparts.scheme != 'http':
                        title = 'Only http is allowed'
                        msg = 'We do not support %s URLs'%urlparts.scheme
                        flow.http_response.status = '200 Error %s'%title 
                        flow.http_response.body = error(title=title, msg=msg)
                    else:
                        try:
                            length = get_length(urlparts.netloc, urlparts.path)
                        except:
                            title = 'Could not fetch file'
                            msg = 'Is the URL correct? Does the server exist?'
                            flow.http_response.status = '200 Error %s'%title 
                            flow.http_response.body = error(title=title, msg=msg)
                        else:
                            log.debug('The file at %s has length %s', url, length)
                            if length is None:
                                title = 'The server hosting the file would not tell us its size'
                                msg = 'We will not proxy this file because we don\'t know its length'
                                flow.http_response.status = '200 Error %s'%title 
                                flow.http_response.body = error(title=title, msg=msg)
                            elif length > flow.app.config.proxy.max_length:
                                title = 'The requested file is too big to proxy'
                                msg = 'Sorry, but your file is %s bytes, over our %s byte limit. If we proxy large files we\'ll use up all our bandwidth'%(
                                    length, 
                                    flow.app.config.proxy.max_length,
                                )
                                flow.http_response.status = '200 Error %s'%title 
                                flow.http_response.body = error(title=title, msg=msg)
                            else:
                                fp = urllib2.urlopen(url)
                                raw = fp.read()
                                fp.close()
                                sheet_name = ''
                                if flow.query.has_key('sheet'):
                                    sheet_number = int(flow.query.getfirst('sheet'))
                                else:
                                    sheet_number = 0
                                if extension == 'xls':
                                    book = xlrd.open_workbook('file', file_contents=raw, verbosity=0)
                                    names = []
                                    for sheet_name in book.sheet_names():
                                        names.append(sheet_name)
                                    rows = []
                                    sheet = book.sheet_by_name(names[sheet_number])
                                    for rownum in range(sheet.nrows):
                                        vals = sheet.row_values(rownum)
                                        rows.append(vals)
                                else:
                                    raise Exception('Not supoprted yet')
                                indent=None
                                if flow.query.has_key('indent'):
                                    indent=int(flow.query.getfirst('indent'))
                                flow.http_response.body = json.dumps(
                                    dict(
                                        header=dict(
                                            url=url,
                                            length=length,
                                            sheet_name=sheet_name,
                                            sheet_number=sheet_number,
                                        ),
                                        response=rows,
                                    ),
                                    indent=indent,
                                )

if __name__ == '__main__':
    from wsgiref.util import setup_testing_defaults
    from wsgiref.simple_server import make_server

    logging.basicConfig(level=logging.DEBUG)
    httpd = make_server('', 8000, JsonpDataProxy(100000))
    print "Serving on port 8000..."
    httpd.serve_forever()

