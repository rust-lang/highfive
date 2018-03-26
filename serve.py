"""A simple CGI HTTP server for Highfive.

This script should be run from the repository root (i.e., the same
directory this file resides in). Provide the repository root path in
PYTHONPATH. Example:

    $ PYTHONPATH=$PYTHONPATH:$PWD python serve.py
"""

import BaseHTTPServer
import CGIHTTPServer
import highfive

PORT = 8000

server = BaseHTTPServer.HTTPServer
handler = CGIHTTPServer.CGIHTTPRequestHandler
server_address = ('', PORT)
handler.cgi_directories = ['/highfive']

httpd = server(server_address, handler)
print "Serving at port", PORT
httpd.serve_forever()
