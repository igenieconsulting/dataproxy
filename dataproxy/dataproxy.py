#from google.appengine.ext.webapp.util import run_wsgi_app
import os
from app import JsonpDataProxy
import webapp2

application = JsonpDataProxy(3000000)

def main():
    from paste import httpserver
    httpserver.serve(application, host='127.0.0.1', port='8000')

if __name__ == "__main__":
    main()
